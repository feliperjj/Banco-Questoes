import json
from contextlib import contextmanager

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from src.db.database import db, init_db
from src.db.models import Questao, QuestaoVersao, RevisaoConteudo, RevisaoGabarito
from src.models import eligibility_read, questoes_repo as repo
from src.models.provenance_service import assess_version, create_source
from src.models.review_workflow import apply_field_correction, read_source_region, render_source_region
from src.ui.components.question_source_review import QuestionSourceReviewDialog
from src.ui.components.field_correction import FieldCorrectionDialog


@pytest.fixture(scope='module', autouse=True)
def restore_database_after_module():
    previous = db.database
    yield
    # Os testes seguintes podem usar DB_PATH explicitamente; devolve a conexão
    # após a limpeza dos widgets e workers feita pelas fixtures de cada caso.
    init_db(previous)


def _question(number=1, **changes):
    return repo.criar_questao(dict(
        numero_oficial=number, enunciado='Enunciado completo para conferência.',
        texto_apoio='Contexto preservado.', tipo='multipla_escolha', gabarito='A',
        alternativas=[{'letra': a, 'texto': f'Opção {a}'} for a in 'ABCDE'], **changes))


def _pdf(path):
    stream = b'BT /F1 12 Tf 20 750 Td (Texto relido somente desta pagina.) Tj ET'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
        f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    output, offsets = bytearray(b'%PDF-1.4\n'), [0]
    for n, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f'{n} 0 obj\n'.encode() + body + b'\nendobj\n')
    xref = len(output)
    output.extend(f'xref\n0 {len(objects) + 1}\n'.encode() + b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    path.write_bytes(output)
    return path


def test_fila_so_inclui_pendentes_da_selecao_sem_gravar(tmp_path):
    from helpers import approve_with_evidence
    init_db(str(tmp_path / 'queue.db'))
    first, approved, outside = [_question(n) for n in (1, 2, 3)]
    approve_with_evidence(approved, tmp_path / 'original.pdf', 'A')
    before = list(db.connection().iterdump())
    result = repo.diagnosticar_fila([approved, first, first])
    assert [q['id'] for q in result] == [first]
    assert outside not in [q['id'] for q in result]
    assert result[0]['assessment']['decisoes_humanas_necessarias']
    assert list(db.connection().iterdump()) == before


def test_prefetch_limitado_mantem_fallback_e_descarta_snapshot(tmp_path):
    from helpers import approve_with_evidence
    init_db(str(tmp_path / 'scoped.db'))
    ids = [_question(n) for n in (1, 2)]
    for n, ident in enumerate(ids):
        approve_with_evidence(ident, tmp_path / f'original-{n}.pdf', 'A')
    versions = [repo.ultima_versao(q).id for q in ids]
    expected = [assess_version(v) for v in versions]
    with eligibility_read.eligibility_read([ids[0]]):
        assert set(eligibility_read._snapshot.get()[Questao]) == {ids[0]}
        assert [assess_version(v) for v in versions] == expected
    assert eligibility_read._snapshot.get() is None
    with eligibility_read.eligibility_read([]):
        assert eligibility_read._snapshot.get()[Questao] == {}
        assert assess_version(versions[1]) == expected[1]


def test_contagem_precarrega_apenas_candidatos_dos_filtros(tmp_path, monkeypatch):
    init_db(str(tmp_path / 'filtered.db'))
    selected = _question(1, disciplina='Informática')
    _question(2, disciplina='Português')
    snapshots = []
    original = eligibility_read.eligibility_read
    @contextmanager
    def record(ids=None):
        with original(ids):
            snapshots.append(set(eligibility_read._snapshot.get()[Questao]))
            yield
    monkeypatch.setattr(eligibility_read, 'eligibility_read', record)
    assert repo.contar_questoes_elegiveis({'disciplina': 'Informática'}) == 0
    assert snapshots == [{selected}]


def test_correcao_isolada_preserva_historico_e_exige_nova_conferencia(tmp_path):
    from helpers import approve_with_evidence
    init_db(str(tmp_path / 'correction.db'))
    ident = _question()
    old = approve_with_evidence(ident, tmp_path / 'original.pdf', 'A')
    proof = repo.criar_prova('Histórico anterior à correção', {}, 1, 0)
    attempt = repo.iniciar_tentativa(proof)
    snapshot = QuestaoVersao.get_by_id(old).conteudo_json
    before = repo.obter_questao(ident)
    reviews = (RevisaoConteudo.select().count(), RevisaoGabarito.select().count())
    new = apply_field_correction(old, 'enunciado', 'Enunciado corrigido a partir do original.')
    after = repo.obter_questao(ident)
    assert new != old
    assert {k: v for k, v in before.items() if k != 'enunciado'} == {k: v for k, v in after.items() if k != 'enunciado'}
    assert QuestaoVersao.get_by_id(old).conteudo_json == snapshot
    assert (RevisaoConteudo.select().count(), RevisaoGabarito.select().count()) == reviews
    assert not assess_version(new)['liberada']
    assert repo.buscar_questoes_da_prova(proof)[0]['enunciado'] == before['enunciado']
    assert repo.finalizar_tentativa(attempt, {ident: 'A'}, 5)['acertos'] == 1
    assert apply_field_correction(new, 'enunciado', after['enunciado']) == new
    with pytest.raises(ValueError, match='mudou'):
        apply_field_correction(old, 'gabarito', 'B')


@pytest.mark.parametrize('field,value', [
    ('numero_oficial', 0), ('numero_oficial', True), ('gabarito', 'F'),
    ('alternativas', [{'letra': 'B', 'texto': 'Fora de sequência'}]),
    ('enunciado', ''), ('tipo', 'certo_errado'),
])
def test_correcao_invalida_nao_muda_questao_ou_versao(tmp_path, field, value):
    init_db(str(tmp_path / 'invalid.db'))
    ident = _question()
    version = repo.ultima_versao(ident).id
    before = repo.obter_questao(ident)
    with pytest.raises(ValueError):
        apply_field_correction(version, field, value)
    assert repo.obter_questao(ident) == before
    assert repo.ultima_versao(ident).id == version


def test_releitura_de_recorte_nao_salva_e_recusa_fonte_alterada(tmp_path):
    init_db(str(tmp_path / 'region.db'))
    ident = _question()
    version = repo.ultima_versao(ident).id
    pdf = _pdf(tmp_path / 'original.pdf')
    source = create_source(pdf, tipo='pdf')
    before = list(db.connection().iterdump())
    region = read_source_region(source, 1, (0, 0, 595, 100))
    assert 'Texto relido' in region['text']
    assert list(db.connection().iterdump()) == before
    new = apply_field_correction(version, 'enunciado', region['text'], region=region)
    extraction = QuestaoVersao.get_by_id(new).execucao_extracao
    assert extraction.extrator == 'releitura_parcial_assistida'
    assert json.loads(extraction.parametros_json)['campo'] == 'enunciado'
    assert repo.obter_questao(ident)['gabarito'] == 'A'
    pdf.write_bytes(pdf.read_bytes() + b'alterado')
    with pytest.raises(ValueError, match='fonte'):
        read_source_region(source, 1, (0, 0, 595, 100))
    with pytest.raises(ValueError, match='fonte'):
        apply_field_correction(new, 'texto_apoio', 'Novo contexto', region=region)
    assert repo.ultima_versao(ident).id == new


def test_botao_da_fila_reavalia_a_lista_e_atualiza_apos_correcao(tmp_path, monkeypatch):
    from src.ui.pages.questoes import QuestoesPage
    from tests.ui_wait import wait_ui_jobs
    init_db(str(tmp_path / 'queue-action.db'))
    first, second = [_question(n) for n in (1, 2)]
    opened = []
    def review(dialog):
        opened.append(dialog.queue_ids)
        apply_field_correction(dialog.version_id, 'enunciado', 'Texto corrigido durante a fila.')
        return 1
    monkeypatch.setattr(QuestionSourceReviewDialog, 'exec', review)
    page = QuestoesPage()
    page.review_queue_button.click()
    wait_ui_jobs()
    assert opened == [[first, second]]
    assert page.review_queue_button.isEnabled()
    assert page.tabela.item(0, 0).data(Qt.UserRole)['enunciado'] == 'Texto corrigido durante a fila.'


def test_fila_ui_nao_transfere_decisoes_entre_questoes_e_mostra_acao(tmp_path):
    from helpers import approve_with_evidence
    init_db(str(tmp_path / 'guided.db'))
    first, second = [_question(n) for n in (1, 2)]
    approve_with_evidence(first, tmp_path / 'original.pdf', 'A')
    dialog = QuestionSourceReviewDialog(first, question_ids=[first, second])
    dialog.rationale.setPlainText('Justificativa da primeira questão')
    assert dialog.content_decision.currentData() == 'conferido'
    dialog.queue_next.click()
    assert dialog.question_id == second
    assert dialog.content_decision.currentData() == 'pendente'
    assert dialog.answer_decision.currentData() == 'desconhecido'
    assert dialog.rationale.toPlainText() == ''
    assert dialog.question_pdf.source_id is None
    assert dialog.pending_selector.count() > 0
    assert dialog.pending_action.text()
    assert 'Enunciado completo' in dialog.comparison_text.toPlainText()
    dialog.queue_previous.click()
    assert dialog.question_id == first
    assert dialog.content_decision.currentData() == 'conferido'


def test_recorte_sem_texto_tem_previa_visual_e_nao_inventa_extracao(tmp_path):
    from helpers import write_test_pdf
    init_db(str(tmp_path / 'scan.db'))
    path = write_test_pdf(tmp_path / 'pagina-sem-texto.pdf')
    source = create_source(path, tipo='pdf')
    with pytest.raises(ValueError, match='não contém texto'):
        read_source_region(source, 1, (0, 0, 200, 100))
    image = QImage.fromData(render_source_region(source, 1, (0, 0, 200, 100)))
    assert not image.isNull()
    assert image.width() == 300 and image.height() == 150
    path.write_bytes(path.read_bytes() + b'alterado')
    with pytest.raises(ValueError, match='alterada'):
        render_source_region(source, 1, (0, 0, 200, 100))


def test_correcao_historica_desabilitada_e_proposta_reiniciada(tmp_path):
    init_db(str(tmp_path / 'historical.db'))
    ident = _question()
    original = repo.ultima_versao(ident).id
    apply_field_correction(original, 'enunciado', 'Enunciado de uma nova versão.')
    dialog = QuestionSourceReviewDialog(ident)
    correction = FieldCorrectionDialog(dialog.version_id, 'enunciado', dialog.question_pdf, dialog)
    correction.proposal.setPlainText('Proposta que pertence ao enunciado')
    correction.field.setCurrentIndex(correction.field.findData('gabarito'))
    assert correction.proposal.toPlainText() == 'A'
    assert correction.source_pane is dialog.answer_pdf
    dialog.version_selector.setCurrentIndex(0)
    assert not dialog.correct_button.isEnabled()
    dialog.show()
    for width, height in ((960, 640), (1240, 800)):
        dialog.resize(width, height)
        QApplication.instance().processEvents()
        assert dialog.width() == width and dialog.height() == height
        for widget in (dialog.queue_next, dialog.pending_selector, dialog.correct_button,
                       dialog.content_button, dialog.answer_button):
            point = widget.mapTo(dialog, widget.rect().bottomRight())
            assert dialog.rect().contains(point)
