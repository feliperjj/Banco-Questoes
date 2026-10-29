from threading import Event
import time
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from src.db.database import init_db
from src.models import ia_triage
from src.ui.components.triage_review import TriageReviewDialog
from tests.ui_wait import wait_ui_jobs


def test_cancelar_preserva_resultado_parcial_e_reabilita_inicio(tmp_path, monkeypatch):
    init_db(str(tmp_path / 'cancel.db'))
    started = Event()
    def fake(ids, *, cancel_event, progress):
        progress(1, 2); started.set(); cancel_event.wait(3)
        return {'rows': [{'questao_id': 1, 'categoria': 'revisao', 'status': 'abster'}],
                'counts': {'revisao': 1}, 'cancelled': True}
    monkeypatch.setattr(ia_triage, 'triage_questions', fake)
    dialog = TriageReviewDialog([1, 2]); dialog.start_analysis()
    for _ in range(200):
        QApplication.processEvents()
        if started.is_set(): break
        time.sleep(.005)
    assert started.is_set()
    dialog.cancel_analysis(); wait_ui_jobs()
    assert len(dialog.rows) == 1 and dialog.start_button.isEnabled()
    assert 'cancelada' in dialog.status_label.text()
    dialog.reject()
    dialog._analysis_done({'rows': []})
    assert len(dialog.rows) == 1


def test_sem_diferencas_ocultas_e_divergencias_visiveis():
    dialog = TriageReviewDialog([])
    dialog.rows = [{'questao_id': 1, 'categoria': 'conferir', 'status': 'manter'},
                   {'questao_id': 2, 'categoria': 'revisao', 'status': 'abster'}]
    dialog._refresh_table()
    assert dialog.table.rowCount() == 1
    dialog.filter.setCurrentText('Divergências')
    assert dialog.table.rowCount() == 1
    dialog.close()


def test_salvar_sem_mudanca_nao_remove_pendencias_e_mudanca_atualiza_so_questao(tmp_path, monkeypatch):
    from src.ui.components import field_correction
    init_db(str(tmp_path / 'noop.db'))
    row = {'questao_id': 1, 'version_id': 10, 'field': 'alternativas', 'letter': 'E',
           'categoria': 'proposta', 'status': 'proposta', 'proposal': 'Texto',
           'region': {'source_id': 1, 'page': 1, 'bounds': [0, 0, 100, 100]}}
    dialog = TriageReviewDialog([1, 2])
    dialog.rows = [row, {'questao_id': 1, 'version_id': 10, 'field': 'gabarito', 'categoria': 'revisao'},
                   {'questao_id': 2, 'version_id': 20, 'categoria': 'revisao'}]
    monkeypatch.setattr(ia_triage, 'validate_triage_row', lambda _: True)
    class Correction:
        result_version_id = 10
        def __init__(self, *args): self.proposal = SimpleNamespace(setPlainText=lambda _: None)
        def exec(self): return 1
    monkeypatch.setattr(field_correction, 'FieldCorrectionDialog', Correction)
    dialog._refresh_table(); dialog.table.selectRow(0)
    dialog._review_selected()
    assert len(dialog.rows) == 3 and 'Nenhuma' in dialog.status_label.text()
    Correction.result_version_id = 11
    monkeypatch.setattr(ia_triage, 'triage_questions', lambda ids, **kwargs:
        {'rows': [{'questao_id': ids[0], 'version_id': 11, 'field': 'gabarito', 'categoria': 'revisao'}]})
    dialog._review_selected(); wait_ui_jobs()
    assert any(r['questao_id'] == 2 for r in dialog.rows)
    assert any(r['questao_id'] == 1 and r['field'] == 'gabarito' for r in dialog.rows)
    assert all(r.get('categoria') != 'liberada' for r in dialog.rows)
    dialog.close()
