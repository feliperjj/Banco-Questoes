from PySide6.QtWidgets import QApplication

from src.db.database import init_db
from src.models import questoes_repo as repo
from tests.ui_wait import wait_ui_jobs


def test_triagem_usa_ids_da_lista_e_inicia_sem_segunda_confirmacao(tmp_path, monkeypatch):
    init_db(str(tmp_path / 'entry.db'))
    ids = [repo.criar_questao({'enunciado': text, 'tipo': 'certo_errado', 'gabarito': 'Certo'})
           for text in ('Questão selecionada.', 'Outra questão.')]
    from src.ui.pages.questoes import QuestoesPage
    from src.ui.components import triage_review
    calls = []
    class Dialog:
        def __init__(self, selected, parent): calls.append(list(selected))
        def start_analysis(self): calls.append('started')
        def exec(self): QApplication.processEvents(); return 0
    monkeypatch.setattr(triage_review, 'TriageReviewDialog', Dialog)
    page = QuestoesPage()
    wait_ui_jobs()
    # Simula a lista filtrada: o serviço não recebe IDs fora desta lista.
    page.tabela.removeRow(1)
    selected = page.tabela.item(0, 0).data(256)['id']
    page.triage_button.click()
    wait_ui_jobs()
    assert calls == [[selected], 'started']
