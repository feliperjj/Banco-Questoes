"""Regressões de desempenho preservando as decisões de elegibilidade."""
from pathlib import Path

import pytest
from PIL import Image, features
from PySide6.QtGui import QImage

from src.db.database import db, init_db
from src.models import questoes_repo as repo
from src.models.provenance_service import (
    begin_source_verification_batch, consistent_source_read, create_source,
    end_source_verification_batch, verify_source,
)


@pytest.fixture(scope='module', autouse=True)
def restore_database():
    previous = db.database
    yield
    init_db(previous)


def test_listagem_e_contagem_otimizadas_preservam_as_decisoes(tmp_path):
    from helpers import approve_with_evidence
    init_db(str(tmp_path / 'equivalence.db'))
    source_id = repo.criar_prova_cadastrada('Prova de comparação', [
        {'numero_oficial': n, 'enunciado': f'Afirmação completa número {n}.',
         'tipo': 'certo_errado', 'gabarito': 'Certo'} for n in (1, 2, 3)])
    questions = repo.consultar_questoes_importadas(source_id)
    approve_with_evidence(questions[0]['id'], tmp_path / 'original.pdf', 'Certo')
    # Ignora somente os decorators de cache; a regra de domínio é a mesma.
    expected_list = repo.listar_provas_cadastradas.__wrapped__.__wrapped__()
    expected_count = repo.contar_questoes_elegiveis.__wrapped__.__wrapped__()
    assert repo.listar_provas_cadastradas() == expected_list
    assert repo.contar_questoes_elegiveis() == expected_count == 1
    assert repo.listar_provas_cadastradas()[0]['qtd_avaliaveis'] == 1


@pytest.mark.parametrize('change', ['modify', 'delete', 'create'])
def test_snapshot_recusa_resultado_se_arquivo_muda_durante_leitura(tmp_path, change):
    from helpers import write_test_pdf
    init_db(str(tmp_path / 'changing.db'))
    path = write_test_pdf(tmp_path / 'original.pdf')
    source = create_source(path, tipo='pdf')
    original = path.read_bytes()
    if change == 'create':
        path.unlink()
    token = begin_source_verification_batch()
    try:
        with pytest.raises(ValueError, match='mudou durante'):
            with consistent_source_read():
                assert verify_source(source)['integro'] is (change != 'create')
                if change == 'delete':
                    path.unlink()
                else:
                    path.write_bytes(original + b'alterado')
    finally:
        end_source_verification_batch(token)
    assert not verify_source(source)['integro']


def test_cache_nao_atravessa_operacoes_nem_ignora_imagem_modificada(tmp_path):
    from helpers import approve_with_evidence
    init_db(str(tmp_path / 'fresh-read.db'))
    image = tmp_path / 'original.png'
    Image.new('RGB', (80, 40), 'white').save(image)
    ident = repo.criar_questao({'numero_oficial': 1, 'enunciado': 'Afirmação completa.',
                              'tipo': 'certo_errado', 'gabarito': 'Certo', 'imagem_path': str(image)})
    approve_with_evidence(ident, tmp_path / 'source.pdf', 'Certo')
    assert repo.contar_questoes_elegiveis() == 1
    Image.new('RGB', (80, 40), 'black').save(image)
    assert repo.contar_questoes_elegiveis() == 0
    assert repo.criar_prova('Não pode usar a contagem anterior', {}, 1, 0) == 0


def test_lote_sem_provas_legadas_nao_carrega_imagens_do_acervo(tmp_path, monkeypatch):
    import src.models.provenance_service as provenance
    init_db(str(tmp_path / 'empty-legacy.db'))
    repo.criar_prova_cadastrada('Prova já cadastrada', [
        {'numero_oficial': 1, 'enunciado': 'Afirmação completa.', 'tipo': 'certo_errado', 'gabarito': 'Certo'}])
    def unexpected(*args, **kwargs):
        raise AssertionError('Sem lotes legados, não deve conferir imagens ou versões.')
    monkeypatch.setattr(provenance, 'prefetch_integrity_files', unexpected)
    assert repo.listar_lotes_importados_sem_prova() == []


def test_listagem_precarrega_so_questoes_das_provas_exibidas(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from src.models import eligibility_read
    init_db(str(tmp_path / 'linked-only.db'))
    proof = repo.criar_prova_cadastrada('Prova ativa', [
        {'numero_oficial': 1, 'enunciado': 'Afirmação vinculada.', 'tipo': 'certo_errado', 'gabarito': 'Certo'}])
    linked = repo.consultar_questoes_importadas(proof)[0]['id']
    repo.criar_questao({'numero_oficial': 2, 'enunciado': 'Afirmação fora da lista.', 'tipo': 'certo_errado', 'gabarito': 'Certo'})
    scopes = []
    original = eligibility_read.eligibility_read
    @contextmanager
    def scoped(ids=None):
        scopes.append(set(ids) if ids is not None else None)
        with original(scopes[-1]):
            yield
    monkeypatch.setattr(eligibility_read, 'eligibility_read', scoped)
    assert repo.listar_provas_cadastradas()[0]['qtd_questoes'] == 1
    assert scopes == [{linked}]


def test_contagem_e_sorteio_compartilham_criterios_com_filtros(tmp_path):
    from helpers import approve_with_evidence
    init_db(str(tmp_path / 'filters.db'))
    for number, discipline, board in ((1, 'Informática', 'FGV'), (2, 'Português', 'FGV'),
                                      (3, 'Informática', 'Outra')):
        ident = repo.criar_questao({'numero_oficial': number, 'enunciado': 'Afirmação completa.',
            'tipo': 'certo_errado', 'gabarito': 'Certo', 'disciplina': discipline, 'banca': board})
        approve_with_evidence(ident, tmp_path / f'original-{number}.pdf', 'Certo')
    for filters, expected in (({}, 3), ({'disciplina': 'Informática'}, 2),
            ({'disciplina': 'Informática', 'banca': 'FGV'}, 1), ({'banca': 'Ausente'}, 0)):
        assert repo.contar_questoes_elegiveis(filters) == repo._questoes_elegiveis(filters).count() == expected


def test_metadados_compartilhados_sao_lidos_uma_vez_e_reconferidos(tmp_path, monkeypatch):
    import src.models.provenance_service as provenance
    from helpers import write_test_pdf
    init_db(str(tmp_path / 'shared.db'))
    path = write_test_pdf(tmp_path / 'shared.pdf')
    source = create_source(path, tipo='pdf')
    calls = []
    original = provenance._read_file_stat
    def counted(value):
        calls.append(value)
        return original(value)
    monkeypatch.setattr(provenance, '_read_file_stat', counted)
    token = begin_source_verification_batch()
    try:
        with consistent_source_read():
            for _ in range(100):
                assert verify_source(source)['integro']
    finally:
        end_source_verification_batch(token)
    assert calls.count(path) == 2  # observação inicial e conferência ao terminar


def test_webp_novo_preserva_pixels_e_png_antigo_permanece_inalterado(tmp_path):
    from src.importador.pdf_fonte import _render_asset
    from src.importador.pdf_render import render_region
    from helpers import write_test_pdf
    if not features.check('webp'):
        pytest.skip('Pillow sem codificador WebP; a aplicação usa PNG como fallback.')
    path = write_test_pdf(tmp_path / 'source.pdf')
    assets = tmp_path / 'assets'
    rendered = _render_asset(path, 'fixture-hash', 1, (0, 0, 100, 80), assets)
    assert rendered is not None and Path(rendered['path']).suffix == '.webp'
    png = tmp_path / 'comparison.png'
    render_region(path, 1, (0, 0, 100, 80), output=png)
    with Image.open(rendered['path']) as webp_image, Image.open(png) as png_image:
        assert webp_image.convert('RGB').tobytes() == png_image.convert('RGB').tobytes()
    assert not QImage(rendered['path']).isNull()
    legacy = Path(rendered['path']).with_suffix('.png')
    legacy.write_bytes(png.read_bytes())
    before = legacy.read_bytes()
    again = _render_asset(path, 'fixture-hash', 1, (0, 0, 100, 80), assets)
    assert again['path'] == str(legacy)
    assert legacy.read_bytes() == before
