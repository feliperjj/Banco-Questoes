from pathlib import Path
from threading import Event
from time import monotonic
from time import sleep

import pytest
from PySide6.QtCore import Qt, QEventLoop, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from src.db.database import db, init_db
from src.db.models import Questao
from src.models import questoes_repo as repo
from src.models.importacao_session import ImportacaoSession, EstadoImportacao
from src.ui.background import BackgroundTask
from src.ui.components.question_editor import QuestionEditor
from src.ui.main_window import MainWindow
from src.ui.pages.importacao import ImportacaoPage


@pytest.fixture
def app(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(Path('src/ui/styles.qss').read_text(encoding='utf-8'))
    init_db(str(tmp_path / 'reforma.db'))
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.Yes)
    yield application
    db.close()


def questao(numero=1):
    return dict(numero=numero, enunciado=f'Enunciado {numero}', tipo='certo_errado',
                gabarito='Certo', cargo='Analista', comentario='Preservar')


def pagina():
    page = ImportacaoPage()
    page.caminho_questoes_pendente = 'original.pdf'
    page._finalizar_importacao_questoes([questao(1), questao(3)])
    page.steps.setCurrentIndex(2)
    return page


def aguardar_salvamento(page):
    if not page.ocupada:
        return
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    page.task.idle.connect(loop.quit)
    timer.timeout.connect(loop.quit)
    timer.start(10000)
    loop.exec()
    page.task.idle.disconnect(loop.quit)
    assert not page.ocupada, "O salvamento em segundo plano não terminou no prazo."


def test_rascunho_sobrevive_navegacao_e_filtro(app):
    page = pagina()
    page.editor.enunciado_input.setPlainText('Texto corrigido')
    page.lista_questoes.setCurrentRow(1)
    page.filtro.setCurrentIndex(2)
    page.filtro.setCurrentIndex(0)
    page.steps.setCurrentIndex(1)
    page.steps.setCurrentIndex(2)
    page.lista_questoes.setCurrentRow(0)
    assert page.editor.data()['enunciado'] == 'Texto corrigido'
    assert page.editor.data()['comentario'] == 'Preservar'


def test_caderno_catalogado_preenche_cargo_e_tipo_confirmados(app):
    page = ImportacaoPage()
    page.caminho_questoes_pendente = str(Path(__file__).resolve().parents[1] / 'samples' / 'administrador-fgv.pdf')
    page._finalizar_importacao_questoes([questao()])

    assert page.cargo_gabarito_input.text() == 'ADMINISTRADOR'
    assert page.codigo_gabarito_input.text() == 'PROVA TIPO 1'


def test_salvar_individual_e_lote_nao_duplica(app):
    page = pagina()
    page.salvar_questao()
    aguardar_salvamento(page)
    assert len(page.session.pendentes) == 1
    assert not page.editor.isEnabled()
    assert page.steps.currentIndex() == 2
    page.salvar_todas()
    aguardar_salvamento(page)
    page.salvar_todas()
    assert Questao.select().count() == 2, page.feedback.text()
    assert page.session.estado == EstadoImportacao.CONCLUIDO


def test_falha_persistencia_permite_tentar_novamente(app, monkeypatch):
    page = pagina()
    salvar = repo.criar_questoes_em_lote
    def falhar(dados):
        raise RuntimeError('Banco indisponível')
    monkeypatch.setattr(repo, 'criar_questoes_em_lote', falhar)
    page.salvar_todas()
    aguardar_salvamento(page)
    assert page.session.pendentes == [0, 1]
    assert Questao.select().count() == 0
    monkeypatch.setattr(repo, 'criar_questoes_em_lote', salvar)
    page.salvar_todas()
    aguardar_salvamento(page)
    assert Questao.select().count() == 2, page.feedback.text()


def test_cancelar_leitura_preserva_revisao_anterior(app):
    page = pagina()
    page.editor.enunciado_input.setPlainText("Alteração recuperável")
    page.session.editar(0, page.editor.data())
    page._start(lambda: sleep(0.2), "Lendo arquivo de teste.")
    page._cancelar_operacao()
    aguardar_salvamento(page)

    assert page.session.questoes[0]["enunciado"] == "Alteração recuperável"
    assert page.session.pendentes == [0, 1]
    assert "cancelada" in page.feedback.text().lower()


@pytest.mark.parametrize('falha', [True, False])
def test_reimportacao_invalida_preserva_revisao(app, falha):
    page = pagina()
    page.caminho_questoes_pendente = 'outro.pdf'
    if falha:
        page._falha('Arquivo inválido')
    else:
        page._finalizar_importacao_questoes([])
    assert page.caminho_questoes == 'original.pdf'
    assert len(page.questoes_extraidas) == 2
    assert not page.ocupada


def test_classificacao_respeita_numero_oficial_e_itens_salvos():
    session = ImportacaoSession()
    session.carregar([questao(1), questao(10), questao(11)], 'a.pdf')
    session.marcar_salvas([1], [100])
    assert session.classificar(10, 11, 'Direito', 'Constituição') == 1
    assert 'disciplina' not in session.questoes[1]
    assert session.questoes[2]['disciplina'] == 'Direito'


def test_sequencia_nao_desloca_gabarito_em_lacunas(app):
    page = pagina()
    page.gabarito_lote_input.setText('ERRADO ERRADO')
    page.aplicar_gabarito_lote()
    assert [q['gabarito'] for q in page.questoes_extraidas] == ['Certo', 'Certo']
    assert page.feedback.property('error')


def test_editor_nao_apaga_resposta_legada_invalida(app):
    editor = QuestionEditor()
    editor.load(dict(questao(), gabarito='X'))
    assert editor.data()['gabarito'] == 'X'
    with pytest.raises(ValueError):
        editor.data(validate=True)


def test_worker_impede_concorrencia_e_recupera_apos_erro(app):
    task = BackgroundTask()
    released = Event()
    resultados, erros = [], []
    task.result.connect(resultados.append)
    task.error.connect(erros.append)
    def aguardar():
        released.wait(2)
        return 42
    assert task.start(aguardar)
    assert not task.start(lambda: 99)
    released.set()
    def esperar():
        prazo = monotonic() + 5
        while task.running and monotonic() < prazo:
            QTest.qWait(10)
        assert not task.running
    esperar()
    assert resultados == [42]
    def falhar():
        raise ValueError('Falha esperada')
    assert task.start(falhar)
    esperar()
    assert erros == ['Falha esperada']


def test_navegacao_e_rodape_na_janela_minima(app, monkeypatch):
    window = MainWindow()
    window.resize(960, 640)
    window.show()
    window.pages.setCurrentIndex(2)
    page = window.pages.widget(2)
    page._finalizar_importacao_questoes([questao()])
    page.nome_prova_input.setText("Prova de teste")
    page.steps.setCurrentIndex(2)
    app.processEvents()
    assert window.menu.currentRow() == 2
    assert window.width() == 960
    assert window.menu.horizontalScrollBar().maximum() == 0
    for button in (page.btn_salvar_questao, page.btn_salvar_todas):
        assert button.isVisible()
        assert page.rect().contains(button.geometry())
    QTest.mouseClick(page.btn_salvar_questao, Qt.LeftButton)
    aguardar_salvamento(page)
    assert Questao.select().count() == 1, page.feedback.text()
    avisos = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: avisos.append(a))
    page.session.estado = EstadoImportacao.LENDO
    assert not window.close()
    assert avisos
    page.session.restaurar_estado()
    assert window.close()


def test_importacao_reabre_rascunho_salvo_com_fonte_integra(app, tmp_path, monkeypatch):
    import src.models.importacao_rascunho as rascunho

    source = tmp_path / "caderno.pdf"
    source.write_bytes(b"fonte de teste")
    monkeypatch.setattr(rascunho, "RASCUNHO_PATH", tmp_path / "importacao.json")
    window = MainWindow()
    page = window.pages.widget(2)
    page.session.carregar([questao()], str(source))
    page.nome_prova_input.setText("Prova retomada")
    page._refresh_list()
    assert window.close()

    resumed_window = MainWindow()
    resumed = resumed_window.pages.widget(2)
    assert resumed.session.caminho == str(source)
    assert resumed.session.questoes[0]["enunciado"] == questao()["enunciado"]
    assert resumed.nome_prova_input.text() == "Prova retomada"
    assert "recuperado" in resumed.feedback.text().casefold()
    resumed._draft_timer.stop()
    resumed_window.close()
