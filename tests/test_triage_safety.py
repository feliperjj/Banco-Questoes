from contextlib import contextmanager
from threading import Event

import pytest

from src.db.database import db, init_db
from src.models import ia_triage as triage, questoes_repo as repo
from src.models.provenance_service import create_source, create_question_version, add_evidence
from tests.helpers import write_test_pdf


class Engine:
    def __init__(self): self.batches = 0
    @contextmanager
    def batch(self):
        self.batches += 1
        yield self


def case(tmp_path, monkeypatch, status='manter', diagnostics=None):
    init_db(str(tmp_path / 'triage.db'))
    path = write_test_pdf(tmp_path / 'source.pdf')
    source = create_source(path, tipo='pdf')
    qid = repo.criar_questao({'numero_oficial': 1, 'enunciado': 'Texto completo.',
        'tipo': 'multipla_escolha', 'gabarito': 'A',
        'alternativas': [{'letra': a, 'texto': 'Texto ' + a} for a in 'AB']})
    version = create_question_version(qid, source_id=source)
    add_evidence(version, source, part='conteudo', page=1, bounds=(0, 0, 200, 100),
        coordinate_system='pdf-point; origem superior esquerda', page_size=(612, 792), rotation=0,
        scope={'prova': 'fixture', 'cargo': 'fixture', 'codigo': '1', 'versao': '1'})
    source_hash = triage.DocumentoFonte.get_by_id(source).sha256
    seen = []
    monkeypatch.setattr(triage, 'assess_version', lambda _: {'liberada': False, 'pendencias': diagnostics or []})
    def prepare(*args, **kwargs):
        seen.append(kwargs['letter'])
        return {'page': 1, 'bounds': [10, 20, 100, 40], 'source_sha256': source_hash,
                'image_bytes': b'', 'letter': kwargs['letter']}
    monkeypatch.setattr(triage, 'prepare_evidence', prepare)
    monkeypatch.setattr(triage, 'analyze_evidence', lambda evidence, current, **kwargs:
        {'status': status, 'proposal': 'Corrigida' if status == 'proposta' else None,
         'reason': 'Conferir original.', 'readings': {'pdf': current}, 'region': evidence})
    return qid, version, source, path, seen


def test_lote_nao_grava_e_nao_esconde_pendencia_gabarito(tmp_path, monkeypatch):
    q, version, source, _, seen = case(tmp_path, monkeypatch, diagnostics=[{'codigo': 'gabarito_nao_confirmado'}])
    before = list(db.connection().iterdump())
    runtime, reader, progress = Engine(), Engine(), []
    result = triage.triage_questions([q, q, 999999], runtime=runtime, reader=reader,
                                   progress=lambda n, total: progress.append((n, total)))
    assert list(db.connection().iterdump()) == before
    assert runtime.batches == reader.batches == 1
    assert seen == ['A', 'B'] and progress == [(1, 2), (2, 2)]
    assert result['counts']['conferir'] == 2 and result['counts']['revisao'] == 1
    assert any(r['field'] == 'gabarito' and r['categoria'] == 'revisao' for r in result['rows'])
    assert result['rows'][0]['region']['bounds'] == [10, 20, 100, 40]


@pytest.mark.parametrize('released,diagnostics', [(True, []), (False, [{'codigo': 'gabarito_preliminar'}])])
def test_liberadas_e_preliminares_nao_acionam_ia(tmp_path, monkeypatch, released, diagnostics):
    q, _, _, _, seen = case(tmp_path, monkeypatch)
    monkeypatch.setattr(triage, 'assess_version', lambda _: {'liberada': released, 'pendencias': diagnostics})
    result = triage.triage_questions([q], runtime=Engine(), reader=Engine())
    assert seen == []
    assert result['rows'][0]['categoria'] == ('liberada' if released else 'bloqueada')


def test_abstencao_nao_some_da_fila_e_fonte_alterada_invalida_proposta(tmp_path, monkeypatch):
    q, _, _, path, _ = case(tmp_path, monkeypatch, status='abster')
    result = triage.triage_questions([q], runtime=Engine(), reader=Engine())
    assert all(r['categoria'] == 'revisao' for r in result['rows'])
    def mutate(evidence, current, **kwargs):
        path.write_bytes(path.read_bytes() + b'changed')
        return {'status': 'proposta', 'proposal': 'Não aplicar', 'region': evidence}
    monkeypatch.setattr(triage, 'analyze_evidence', mutate)
    result = triage.triage_questions([q], runtime=Engine(), reader=Engine())
    assert all(r['proposal'] is None and r['analysis'] is None for r in result['rows'])
    assert result['counts']['proposta'] == 0


def test_cancelamento_preserva_parcial_mas_rejeita_versao_concorrente(tmp_path, monkeypatch):
    q, _, _, _, _ = case(tmp_path, monkeypatch, status='proposta')
    event = Event()
    def mutate(evidence, current, **kwargs):
        repo.atualizar_questao(q, {'enunciado': 'Atualizado concorrentemente.'})
        event.set()
        return {'status': 'proposta', 'proposal': 'Antiga', 'region': evidence}
    monkeypatch.setattr(triage, 'analyze_evidence', mutate)
    result = triage.triage_questions([q], runtime=Engine(), reader=Engine(), cancel_event=event)
    assert result['cancelled'] and result['rows']
    assert result['rows'][0]['proposal'] is None and result['rows'][0]['analysis'] is None
    assert result['rows'][0]['categoria'] == 'revisao'
    with pytest.raises(ValueError): triage.validate_triage_row(result['rows'][0])


def test_preliminar_nao_oculta_contexto_ou_recurso_visual(tmp_path, monkeypatch):
    q, _, _, _, seen = case(tmp_path, monkeypatch, diagnostics=[
        {'codigo': 'gabarito_preliminar', 'parte': 'gabarito'},
        {'codigo': 'contexto_ausente', 'parte': 'contexto'},
        {'codigo': 'imagem_pendente', 'parte': 'recurso_visual'}])
    result = triage.triage_questions([q], runtime=Engine(), reader=Engine())
    assert seen == []
    assert {row['field'] for row in result['rows']} == {'gabarito', 'texto_apoio', 'recurso_visual'}
    assert 'gabarito_preliminar' in result['rows'][0]['reason']
