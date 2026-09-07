import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem

from src.db.database import db, init_db
from src.db.models import Questao, Resposta, ProgressoTentativa
from src.models import questoes_repo as repo
from src.ui.pages.questoes import QuestaoDialog
from src.ui.pages.execucao_prova import ExecucaoProvaPage
from src.ui.pages.gerador_prova import GeradorProvaPage


@pytest.fixture
def banco(tmp_path):
    init_db(str(tmp_path / 'melhorias.db'))
    yield
    db.close()


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('gabarito', [None, 'Anulada', 'B'])
def test_edicao_preserva_gabarito_e_metadados(banco, app, gabarito):
    qid = repo.criar_questao({'enunciado': 'Original', 'tipo': 'multipla_escolha',
        'gabarito': gabarito, 'cargo': 'Analista', 'orgao': 'Órgão', 'comentario': 'Explicação',
        'alternativas': [{'letra': 'A', 'texto': 'Uma'}, {'letra': 'B', 'texto': 'Outra'}]})
    dialog = QuestaoDialog(repo.buscar_questoes()[0])
    dialog.enunciado_input.setPlainText('Editado')
    dialog.salvar()
    q = Questao.get_by_id(qid)
    assert (q.enunciado, q.gabarito, q.cargo, q.orgao, q.comentario) == (
        'Editado', gabarito, 'Analista', 'Órgão', 'Explicação')
    assert q.alternativas.count() == 2


def test_editor_cadastra_alternativas_e_troca_tipo(banco, app):
    dialog = QuestaoDialog()
    dialog.enunciado_input.setPlainText('Escolha uma resposta')
    for row, texto in enumerate(['Primeira', 'Segunda']):
        dialog.alternativas_input.setItem(row, 0, QTableWidgetItem(texto))
    dialog.gabarito_input.setCurrentIndex(dialog.gabarito_input.findData('B'))
    dialog.salvar()
    dados = repo.buscar_questoes()[0]
    assert dados['alternativas'] == [{'letra': 'A', 'texto': 'Primeira'}, {'letra': 'B', 'texto': 'Segunda'}]
    dialog = QuestaoDialog(dados)
    dialog.tipo_combo.setCurrentText('certo_errado')
    dialog.gabarito_input.setCurrentIndex(dialog.gabarito_input.findData('Certo'))
    dialog.salvar()
    q = Questao.get_by_id(dados['id'])
    assert q.gabarito == 'Certo'
    assert q.alternativas.count() == 0


def test_editor_rejeita_alternativa_correta_ausente(banco, app, monkeypatch):
    avisos = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: avisos.append(args))
    dialog = QuestaoDialog()
    dialog.enunciado_input.setPlainText('Teste')
    for row in range(2):
        dialog.alternativas_input.setItem(row, 0, QTableWidgetItem('Texto'))
    dialog.gabarito_input.setCurrentIndex(dialog.gabarito_input.findData('E'))
    dialog.salvar()
    assert avisos and Questao.select().count() == 0


def test_disponibilidade_igual_a_selecao(banco, app):
    for resposta in [None, 'Anulada', 'Certo']:
        repo.criar_questao({'enunciado': 'Teste', 'tipo': 'certo_errado', 'gabarito': resposta})
    assert repo.contar_questoes_elegiveis() == 1
    pagina = GeradorProvaPage()
    assert pagina.lbl_disponiveis.text().startswith('1 ')
    prova = repo.criar_prova('Teste', {}, 10, 0)
    assert len(repo.buscar_questoes_da_prova(prova)) == 1


def test_retomada_preserva_respostas_posicao_tempo_e_finaliza(banco, app, monkeypatch):
    for _ in range(2):
        repo.criar_questao({'enunciado': 'Teste', 'tipo': 'certo_errado', 'gabarito': 'Certo'})
    prova = repo.criar_prova('Retomada', {}, 2, 1)
    pagina = ExecucaoProvaPage()
    pagina.iniciar(prova, 'Retomada')
    qid = pagina.questoes[0]['id']
    pagina.salvar_resposta_temp(True, qid, 'Certo')
    pagina.proxima_questao()
    pagina.atualizar_tempo()
    tentativa = pagina.tentativa_id
    pagina.timer.stop()
    pagina.deleteLater()
    db.close()
    assert repo.resumo_dashboard()['total_respostas'] == 0
    assert repo.listar_provas()[0]['em_andamento']
    retomada = ExecucaoProvaPage()
    retomada.iniciar(prova, 'Retomada')
    assert retomada.tentativa_id == tentativa
    assert retomada.respostas_memoria == {qid: 'Certo'}
    assert retomada.idx_atual == 1 and retomada.tempo_gasto == 1
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: QMessageBox.Ok)
    retomada.tempo_limite_seg = 2
    retomada.atualizar_tempo()
    assert not retomada.em_andamento
    assert Resposta.select().count() == 1
    assert ProgressoTentativa.select().count() == 0
    with pytest.raises(ValueError, match='finalizada'):
        repo.salvar_progresso(tentativa, {}, 0, 0)


def test_progresso_rejeita_questao_de_outra_prova(banco):
    qid = repo.criar_questao({'enunciado': 'Teste', 'tipo': 'certo_errado', 'gabarito': 'Certo'})
    prova = repo.criar_prova('Teste', {}, 1, 0)
    tentativa = repo.iniciar_tentativa(prova)
    with pytest.raises(ValueError, match='pertence'):
        repo.salvar_progresso(tentativa, {qid + 1: 'Certo'}, 0, 0)
