from tests.ui_wait import wait_ui_jobs
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QStackedWidget, QWidget

from src.db.database import db, init_db
from src.models.questoes_repo import criar_questao, criar_prova
from src.ui.pages.execucao_prova import ExecucaoProvaPage
from src.ui.pages.importacao import ImportacaoPage
from src.ui.pages.gerador_prova import GeradorProvaPage
import src.ui.pages.execucao_prova as execucao_mod
from src.ui.main_window import MainWindow


def _qapp():
    return QApplication.instance() or QApplication([])


def test_resumo_respostas_acompanha_selecao_e_navegacao(monkeypatch):
    _qapp()
    pagina = ExecucaoProvaPage()
    monkeypatch.setattr(pagina, '_salvar_progresso', lambda: None)
    pagina.questoes = [
        {'id': n, 'enunciado': f'Questão {n}', 'tipo': 'certo_errado'}
        for n in (1, 2)
    ]
    pagina.barra_progresso.setRange(0, 2)
    pagina.mostrar_questao_atual()
    assert pagina.barra_progresso.value() == 0
    pagina.grupo_botoes.buttons()[0].click()
    assert pagina.lbl_resposta.text() == 'Resposta marcada: Certo'
    assert pagina.lbl_respondidas.text() == '1 de 2 respondidas'
    pagina.proxima_questao()
    assert pagina.lbl_resposta.text() == 'Selecione uma resposta'
    assert pagina.barra_progresso.value() == 1
    pagina.questao_anterior()
    assert pagina.grupo_botoes.buttons()[0].isChecked()
    pagina.grupo_botoes.buttons()[1].click()
    assert pagina.lbl_resposta.text() == 'Resposta marcada: Errado'
    assert pagina.barra_progresso.value() == 1
    pagina._mostrar_estado_inicial()
    assert pagina.lbl_resposta.isHidden()
    assert pagina.lbl_respondidas.text() == ''


def test_execucao_limpa_estado_apos_finalizar_prova(tmp_path, monkeypatch):
    _qapp()
    init_db(str(tmp_path / "ui.db"))
    q1 = criar_questao({"enunciado": "Primeira questão do teste", "tipo": "certo_errado", "gabarito": "Certo"})
    q2 = criar_questao({"enunciado": "Segunda questão do teste", "tipo": "certo_errado", "gabarito": "Errado"})
    from tests.test_integridade_gabarito import _aprovar_fixture
    _aprovar_fixture(q1, tmp_path / 'approved-1')
    _aprovar_fixture(q2, tmp_path / 'approved-2', answer='Errado')
    prova_id = criar_prova("Ciclo de regressão", {}, 2, None)

    stack = QStackedWidget()
    for _ in range(4):
        stack.addWidget(QWidget())
    pagina = ExecucaoProvaPage()
    stack.addWidget(pagina)
    pagina.iniciar(prova_id, "Ciclo de regressão")
    wait_ui_jobs()
    pagina.respostas_memoria = {q1: "Certo"}
    monkeypatch.setattr(execucao_mod.QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(execucao_mod.QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    pagina.confirmar_finalizacao()

    assert pagina.em_andamento is False
    assert pagina.timer.isActive() is False
    assert pagina.btn_finalizar.isEnabled() is False
    assert pagina.lbl_enunciado.toPlainText().startswith("Suas questões")
    assert stack.currentIndex() == 3
    db.close()


def test_main_window_inicia_com_dashboard_selecionado():
    _qapp()
    janela = MainWindow()

    assert janela.menu.currentRow() == 0
    assert janela.pages.currentIndex() == 0


def test_botao_iniciar_prova_mantem_altura_legivel(monkeypatch):
    app = _qapp()
    estilo_anterior = app.styleSheet()
    app.setStyleSheet(
        (Path(__file__).parents[1] / "src" / "ui" / "styles.qss").read_text(encoding="utf-8")
    )
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.listar_disciplinas", lambda: [])
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.listar_bancas", lambda: [])
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.listar_topicos", lambda: [])
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.contar_questoes_elegiveis", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        "src.ui.pages.gerador_prova.repo.listar_provas",
        lambda **kwargs: [{"id": 1, "nome": "Simulado", "qtd_questoes": 10, "concluida": False}],
    )
    try:
        pagina = GeradorProvaPage()
        pagina.resize(740, 588)
        pagina.show()
        app.processEvents()

        container = pagina.tabela.cellWidget(0, 4)
        botao = container.findChild(QPushButton, "table-action-button")

        assert pagina.tabela.rowHeight(0) >= 60
        assert botao.height() >= 40
        assert botao.width() >= 132
    finally:
        app.setStyleSheet(estilo_anterior)


def test_gerador_atualiza_bancas_ao_voltar_para_tela(monkeypatch):
    _qapp()
    bancas = [[]]
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.listar_disciplinas", lambda: [])
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.listar_bancas", lambda: bancas[-1])
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.listar_topicos", lambda: [])
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.contar_questoes_elegiveis", lambda *args, **kwargs: 0)
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.listar_fontes_de_prova", lambda: [])
    monkeypatch.setattr("src.ui.pages.gerador_prova.repo.listar_provas", lambda **kwargs: [])

    pagina = GeradorProvaPage()
    bancas.append(["FGV"])
    pagina.showEvent(None)

    assert pagina.banca_input.findText("FGV") >= 0


def test_conferencia_da_fonte_cabe_nas_duas_dimensoes_planejadas(tmp_path):
    from src.models.questoes_repo import atualizar_questao, criar_questao
    from src.ui.components.question_source_review import QuestionSourceReviewDialog

    _qapp()
    init_db(str(tmp_path / "review-ui.db"))
    question_id = criar_questao({
        "enunciado": "Questão sintética para conferir o layout da fonte.",
        "tipo": "multipla_escolha", "gabarito": "A",
        "alternativas": [{"letra": letter, "texto": f"Alternativa {letter}"} for letter in "ABCDE"],
    })
    atualizar_questao(question_id, {"enunciado": "Versão mais recente da questão sintética."})
    dialog = QuestionSourceReviewDialog(question_id)
    assert dialog.version_selector.count() == 2
    dialog.version_selector.setCurrentIndex(0)
    assert not dialog.content_button.isEnabled()
    assert "somente leitura" in dialog.version_label.text()
    dialog.version_selector.setCurrentIndex(1)
    assert dialog.content_button.isEnabled()
    for width, height in ((960, 640), (1240, 800)):
        dialog.resize(width, height)
        dialog.show()
        _qapp().processEvents()
        for widget in (dialog.diagnostic_label, dialog.work_tabs, dialog.resolve_alert_button,
                       dialog.content_button, dialog.answer_button):
            top_left = widget.mapTo(dialog, widget.rect().topLeft())
            assert top_left.x() >= 0 and top_left.y() >= 0
            assert top_left.x() + widget.width() <= dialog.width()
            assert top_left.y() + widget.height() <= dialog.height()
        dialog.work_tabs.setCurrentIndex(0)
        _qapp().processEvents()
        assert dialog.question_pdf.crop_view.isVisible()
        dialog.work_tabs.setCurrentIndex(1)
        _qapp().processEvents()
        assert dialog.extracted.isVisible()


def test_fila_do_funil_filtra_por_etapa_e_expoe_motivos(tmp_path):
    from src.models.questoes_repo import criar_questao
    from src.ui.pages.questoes import QuestoesPage

    _qapp()
    init_db(str(tmp_path / "funnel-queue.db"))
    question_id = criar_questao({"enunciado": "Questão pendente para fila de análise.", "tipo": "certo_errado", "gabarito": "Certo"})
    page = QuestoesPage()
    index = page.filtro_gabarito.findData("funnel:numeracao")
    page.filtro_gabarito.setCurrentIndex(index)
    for _ in range(20):
        _qapp().processEvents()
        if not page.contagem.text().startswith("Analisando"):
            break
    assert page.tabela.rowCount() == 1
    row = page.tabela.item(0, 0).data(Qt.UserRole)
    assert row["id"] == question_id
    assert "numeracao_ausente" in page.tabela.item(0, 6).text()


def test_execucao_finaliza_automaticamente_ao_atingir_limite(tmp_path, monkeypatch):
    _qapp()
    init_db(str(tmp_path / "limite.db"))
    questao = criar_questao({"enunciado": "Questão com tempo limitado", "tipo": "certo_errado", "gabarito": "Certo"})
    from tests.test_integridade_gabarito import _aprovar_fixture
    _aprovar_fixture(questao, tmp_path / 'approved')
    prova_id = criar_prova("Limite", {}, 1, 1)
    stack = QStackedWidget()
    for _ in range(4):
        stack.addWidget(QWidget())
    pagina = ExecucaoProvaPage()
    stack.addWidget(pagina)
    monkeypatch.setattr(execucao_mod.QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    pagina.iniciar(prova_id, "Limite")
    wait_ui_jobs()
    pagina.tempo_limite_seg = 1
    pagina.atualizar_tempo()

    assert pagina.em_andamento is False
    assert pagina.timer.isActive() is False
    db.close()


def test_importacao_assincrona_conclui_sem_perder_caminho(monkeypatch, tmp_path):
    _qapp()
    pagina = ImportacaoPage()
    caminho = str(tmp_path / "prova.pdf")
    pagina.caminho_questoes_pendente = caminho
    monkeypatch.setattr("src.ui.pages.importacao.QMessageBox.warning", lambda *args, **kwargs: QMessageBox.Ok)

    pagina._finalizar_importacao_questoes([])

    assert pagina.caminho_questoes == caminho
    assert pagina.caminho_questoes_pendente == ""
    assert pagina.lbl_arquivo.text() == "prova.pdf"
    assert pagina.btn_selecionar_questoes.isEnabled()
