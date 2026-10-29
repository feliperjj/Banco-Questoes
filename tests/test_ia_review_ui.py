import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QSpinBox

from src.db.database import db, init_db
from src.db.models import QuestaoVersao
from src.models import questoes_repo as repo
from src.models.provenance_service import create_source, create_question_version
from src.models import review_workflow as workflow
from src.ui.components import field_correction as ui
from tests.helpers import write_test_pdf
from tests.ui_wait import wait_ui_jobs


def setup_case(tmp_path):
    init_db(str(tmp_path / 'ui-local.db'))
    path = write_test_pdf(tmp_path / 'source.pdf')
    source = create_source(path, tipo='pdf')
    q = repo.criar_questao({'numero_oficial': 1, 'enunciado': 'Texto original.',
        'tipo': 'multipla_escolha', 'gabarito': 'A',
        'alternativas': [{'letra': letter, 'texto': 'Original ' + letter} for letter in 'ABCDE']})
    version = create_question_version(q, source_id=source)
    page = QSpinBox(); page.setRange(1, 10); page.setValue(1)
    bounds = {}
    for name, value in zip(('x0', 'y0', 'x1', 'y1'), (0, 0, 200, 100)):
        spin = QDoubleSpinBox(); spin.setRange(0, 1000); spin.setValue(value); bounds[name] = spin
    return q, version, source, SimpleNamespace(source_id=source, page_spin=page, bounds=bounds)


def result_for(version, source):
    return {'version_id': version, 'field': 'alternativas', 'letter': 'E', 'status': 'proposta',
        'proposal': 'Conferida E', 'reason': 'Compare com o original.',
        'readings': {'pdf': 'Conferida E', 'ocr': 'Conferida E', 'ia': ''},
        'evidence': {'image_bytes': b''},
        'region': {'source_id': source, 'sha256': 'x', 'page': 1, 'bounds': [0, 0, 200, 100]}}


def test_analise_ui_so_altera_proposta_e_preserva_demais_edicoes(tmp_path, monkeypatch):
    q, version, source, pane = setup_case(tmp_path)
    dialog = ui.FieldCorrectionDialog(version, 'alternativas', pane)
    dialog.ai_letter.setCurrentText('E')
    dialog.proposal.setPlainText(dialog.proposal.toPlainText().replace('Original B', 'Minha edição B'))
    before = list(db.connection().iterdump())
    calls = []
    def fake(v, field, sid, page, bounds, **kwargs):
        calls.append((v, field, sid, page, bounds))
        return result_for(version, source)
    monkeypatch.setattr(ui, 'suggest_source_region', fake)
    dialog._read_ai()
    pane.page_spin.setValue(2)
    pane.bounds['x1'].setValue(300)
    wait_ui_jobs()
    assert calls[0][-2:] == (1, (0, 0, 200, 100))
    assert 'E) Conferida E' in dialog.proposal.toPlainText()
    assert 'B) Minha edição B' in dialog.proposal.toPlainText()
    assert list(db.connection().iterdump()) == before
    assert repo.ultima_versao(q).id == version
    dialog.resize(680, 600); dialog.show(); QApplication.processEvents()
    assert dialog.height() <= 640
    for widget in (dialog.ai_button, dialog.example_button, dialog.save_button):
        assert dialog.rect().contains(widget.mapTo(dialog, widget.rect().bottomRight()))


def test_mudar_campo_descarta_resultado_ai_e_cancela_tarefa(tmp_path, monkeypatch):
    _, version, source, pane = setup_case(tmp_path)
    dialog = ui.FieldCorrectionDialog(version, 'alternativas', pane)
    callbacks = []
    monkeypatch.setattr(dialog.task, 'submit', lambda fn, success, error: callbacks.append((fn, success)))
    dialog._read_ai()
    event = dialog.ai_cancel
    dialog.field.setCurrentIndex(dialog.field.findData('gabarito'))
    assert event.is_set() and not dialog.ai_button.isEnabled()
    assert dialog.proposal.toPlainText() == 'A' and dialog.ai_result is None
    dialog.done(0)


def test_bridge_revalida_versao_fonte_e_nao_persiste_sugestao(tmp_path, monkeypatch):
    q, version, source, _ = setup_case(tmp_path)
    from src.importador import ia_revisao
    def fake(*args, **kwargs):
        return {'status': 'manter', 'proposal': None, 'readings': {}, 'reason': 'conferir',
            'region': {'page': 1, 'bounds': [0, 0, 200, 100], 'image_bytes': b'',
                       'source_sha256': workflow.DocumentoFonte.get_by_id(source).sha256}}
    monkeypatch.setattr(ia_revisao, 'analyze_region', fake)
    before = list(db.connection().iterdump())
    result = workflow.suggest_source_region(version, 'alternativas', source, 1, (0, 0, 200, 100), letter='E')
    assert result['region']['source_id'] == source
    assert list(db.connection().iterdump()) == before
    with pytest.raises(ValueError, match='gabarito'):
        workflow.suggest_source_region(version, 'gabarito', source, 1, (0, 0, 200, 100))
    other = create_source(write_test_pdf(tmp_path / 'other.pdf', width=500), tipo='pdf')
    with pytest.raises(ValueError, match='fonte'):
        workflow.suggest_source_region(version, 'enunciado', other, 1, (0, 0, 200, 100))
    repo.atualizar_questao(q, {'enunciado': 'Alteração concorrente.'})
    with pytest.raises(ValueError, match='mudou'):
        workflow.suggest_source_region(version, 'enunciado', source, 1, (0, 0, 200, 100))


def test_guardar_exemplo_exige_confirmacao_e_nao_cria_revisao_ou_versao(tmp_path, monkeypatch):
    from src.models import ia_dataset
    from src.importador.ia_revisao import file_hash
    from io import BytesIO
    from PIL import Image
    q, version, source, _ = setup_case(tmp_path)
    image = BytesIO(); Image.new('RGB', (60, 20), 'white').save(image, format='PNG')
    evidence = {'source_id': source, 'source_sha256': file_hash(tmp_path / 'source.pdf'),
                'image_bytes': image.getvalue(), 'page': 1, 'bounds': [0, 0, 200, 100]}
    original = ia_dataset.record_reviewed_example
    monkeypatch.setattr(ia_dataset, 'record_reviewed_example', lambda **kwargs:
        original(**kwargs, dataset_dir=tmp_path / 'labels'))
    before = list(db.connection().iterdump())
    with pytest.raises(ValueError, match='confirmed'):
        workflow.remember_local_example(version, evidence, '(A) texto', 'Pessoa teste', False)
    path = workflow.remember_local_example(version, evidence, '(A) texto', 'Pessoa teste', True)
    assert json.loads(path.read_text(encoding='utf-8'))['origin'] == 'human_confirmed'
    assert list(db.connection().iterdump()) == before and repo.ultima_versao(q).id == version
