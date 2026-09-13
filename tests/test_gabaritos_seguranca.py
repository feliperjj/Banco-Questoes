"""Regressões de associação entre formatos, contextos e fontes de gabarito."""
import sys
from types import SimpleNamespace

import pytest

from src.importador import extrator
from src.importador.perfis.gabaritos_contexto import FiltroContexto
from src.importador.perfis.gabaritos_grades import _extrair_gabaritos_tabelas, _extrair_grade_identificada
from src.importador.perfis.gabaritos_resultado import MapaGabarito
from src.importador.perfis.gabaritos_texto import ExtratorPadrao
from src.importador.validacao import associar_gabaritos


@pytest.mark.parametrize('linhas,esperado', [
    (['Item 1 2', 'Gabarito V F', 'Item 3 4', 'Gabarito F V'],
     {1: 'Certo', 2: 'Errado', 3: 'Errado', 4: 'Certo'}),
    (['1 A 2 B', '3 4', 'C D', '5', 'E', 'QUESTÃO 6: ANULADA'],
     {1: 'A', 2: 'B', 3: 'C', 4: 'D', 5: 'E', 6: 'Anulada'}),
    (['Item 1 2 3', 'Gabarito C ? E'], {1: 'C', 3: 'E'}),
    (['1 2', '3 4', 'A B'], {3: 'A', 4: 'B'}),
    (['1 2', 'A', 'B C'], {}),
    (['1 2', 'Gabarito', 'A B'], {1: 'A', 2: 'B'}),
    (['1 2', 'Confira A e B no documento'], {}),
    (['O item 1 errado foi retificado no documento.'], {}),
])
def test_blocos_completos_sem_roubar_respostas(linhas, esperado):
    assert ExtratorPadrao('', '').extrair(linhas) == esperado


@pytest.mark.parametrize('linhas', [
    ['1 2', 'A B', '1 2', 'C B'],
    ['1 Certo', '1 Errado', '2 Certo'],
    ['1', 'A', '1', 'C', '2', 'B'],
    ['Item 1 2', 'V F', 'Item 1 2', 'F F'],
])
def test_todos_os_perfis_preservam_conflitos(linhas):
    resultado = ExtratorPadrao('', '').extrair(linhas)
    assert set(resultado) == {2}
    assert resultado.conflitos == {1}
    assert associar_gabaritos([{'numero': 1}, {'numero': 2}], resultado)['conflitos'] == [1]


def test_tipo_selecionado_no_mesmo_cargo_e_pagina():
    texto = 'ADMINISTRADOR – PROVA TIPO 1\n1 A\nADMINISTRADOR – PROVA TIPO 2\n1 B'
    contexto = FiltroContexto('TIPO 2', 'ADMINISTRADOR')
    assert contexto.pagina_relevante(texto)
    assert ExtratorPadrao('', '').extrair(contexto.linhas_do_cargo(texto.splitlines())) == {1: 'B'}


def test_tipo_sem_cargo_tambem_filtra_linhas():
    linhas = ['PROVA TIPO 1', '1 A', 'PROVA TIPO 2', '1 B']
    assert FiltroContexto('TIPO 2').linhas_do_cargo(linhas) == linhas[2:]


def test_bloco_horizontal_com_codigo_completo_ja_filtrado():
    assert ExtratorPadrao('094_pf_cb2_01', '').extrair(['094_PF_CB2_01', 'Item 21 23', 'Gabarito C E']) == {21: 'C', 23: 'E'}


def test_codigo_numerico_nao_seleciona_por_substring():
    linhas = ['Código: 123', '1 2', 'A B', 'Código: 234', '1 2', 'C D']
    assert ExtratorPadrao('234', '').extrair(linhas) == {1: 'C', 2: 'D'}
    assert ExtratorPadrao('1234', '').extrair(linhas) == {}


def test_multiprova_textual_exige_linha_completa_e_respeita_ordem():
    from src.importador.perfis.gabaritos_texto import ExtratorMultiprova
    linhas = ['PROVA 2 PROVA 1', '1 A 2 B 1 C 2 D', '3 A 3 B 4 C']
    assert ExtratorMultiprova('PROVA 1').extrair(linhas) == {1: 'C', 2: 'D'}


def test_grade_tipos_nao_mistura_cargos():
    texto = 'Cargo: ALVO\nQst T1 T2 T3 T4\n1 A B C D\nCargo: OUTRO\nQst T1 T2 T3 T4\n1 E D C B'
    assert _extrair_grade_identificada(None, texto, 'T2', 'ALVO') == {1: 'B'}


def test_tabela_nao_atravessa_numero_ou_token_ilegivel():
    pagina = SimpleNamespace(extract_tables=lambda: [[['1', '2', 'B'], ['3', '?', 'C'], ['4', '', 'D']]])
    assert _extrair_gabaritos_tabelas(pagina) == {2: 'B', 4: 'D'}


def test_conflito_em_tabelas_complementares():
    pagina = SimpleNamespace(extract_tables=lambda: [[['1', 'A'], ['1', 'B'], ['2', 'C']]])
    resultado = _extrair_gabaritos_tabelas(pagina)
    assert resultado == {2: 'C'} and resultado.conflitos == {1}
    mapa = MapaGabarito()
    mapa.complementar(resultado)
    mapa.complementar({1: 'D'})
    assert mapa == {2: 'C'} and mapa.conflitos == {1}


@pytest.mark.parametrize('questao,resposta', [
    ({'tipo': 'certo_errado'}, 'A'),
    ({'tipo': 'certo_errado'}, 'D'),
    ({'tipo': 'multipla_escolha'}, 'Certo'),
    ({'tipo': 'multipla_escolha', 'alternativas': [{'letra': 'A', 'texto': 'Uma'}, {'letra': 'B', 'texto': 'Outra'}]}, 'E'),
])
def test_resposta_incompativel_nao_e_vinculada(questao, resposta):
    questao['numero'] = 1
    resultado = associar_gabaritos([questao], {1: resposta})
    assert resultado['vinculados'] == 0 and resultado['revisao_manual']
    assert resultado['incompativeis'] == [1] and resultado['faltantes'] == [1]
    assert not questao.get('gabarito')


class Pdf:
    def __init__(self, paginas):
        self.pages = paginas

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_complemento_de_tabela_nao_reintroduz_outro_cargo(monkeypatch):
    pagina = SimpleNamespace(
        extract_text=lambda: 'Cargo: ALVO\n1 A\nCargo: OUTRO\n1 B 2 C',
        extract_tables=lambda: [[['1', 'A'], ['1', 'B'], ['2', 'C']]],
    )
    monkeypatch.setattr(extrator.pdfplumber, 'open', lambda _: Pdf([pagina]))
    resultado = extrator.extrair_gabaritos_pdf('gab.pdf', cargo='ALVO', usar_ocr=False)
    assert resultado == {1: 'A'}


def test_pagina_escaneada_chega_ao_ocr_com_selecao(monkeypatch):
    pagina = SimpleNamespace(extract_text=lambda: '')
    monkeypatch.setattr(extrator.pdfplumber, 'open', lambda _: Pdf([pagina]))
    chamadas = []
    def ocr(caminho, **kwargs):
        chamadas.append(kwargs)
        return {1: 'B'}
    monkeypatch.setattr(extrator, '_extrair_gabaritos_ocr', ocr)
    assert extrator.extrair_gabaritos_pdf('gab.pdf', 'TIPO 2', 'ALVO') == {1: 'B'}
    assert chamadas == [dict(cargo='ALVO', codigo_prova='TIPO 2', indices_paginas=[0])]


def test_ocr_respeita_cargo_tipo_e_numeracao_oficial(monkeypatch):
    import numpy as np
    from src.importador.perfis.gabaritos_ocr import _extrair_gabaritos_ocr
    linhas = ['ALVO – PROVA TIPO 1', '21 A 23 B', 'ALVO – PROVA TIPO 2', '21 D 23 E']
    deteccoes = [([[0, i * 30], [400, i * 30], [400, i * 30 + 10], [0, i * 30 + 10]], l, .99)
                 for i, l in enumerate(linhas)]
    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime', SimpleNamespace(RapidOCR=lambda: lambda _: (deteccoes, None)))
    pagina = SimpleNamespace(extract_text=lambda: '', to_image=lambda **_: SimpleNamespace(
        original=SimpleNamespace(convert=lambda _: np.zeros((10, 10, 3), dtype=np.uint8))))
    monkeypatch.setattr(extrator.pdfplumber, 'open', lambda _: Pdf([pagina]))
    assert _extrair_gabaritos_ocr('cebraspe.pdf', cargo='ALVO', codigo_prova='TIPO 2') == {21: 'D', 23: 'E'}


def test_prova_gerada_exclui_gabarito_de_outro_tipo(tmp_path):
    from src.db.database import init_db
    from src.models import questoes_repo as repo
    init_db(str(tmp_path / 'tipos.db'))
    for resposta in ('A', 'B', 'D'):
        repo.criar_questao(dict(enunciado='Julgue a afirmação.', tipo='certo_errado', gabarito=resposta))
    valido = repo.criar_questao(dict(enunciado='Afirmação válida.', tipo='certo_errado', gabarito='Certo'))
    prova = repo.criar_prova('Sem respostas incompatíveis', {}, 10, 0)
    assert [q['id'] for q in repo.buscar_questoes_da_prova(prova)] == [valido]


def test_diagnostico_nao_conta_incompativel_como_cobertura():
    from src.importador.diagnostico import diagnosticar_caderno
    questoes = [{'numero': 1, 'tipo': 'certo_errado'}]
    relatorio = diagnosticar_caderno('prova.pdf', questoes, {1: 'A'})
    assert relatorio['cobertura_final'] == 0 and relatorio['revisao_manual']
    assert 'gabaritos_incompativeis' in relatorio['motivos']
    assert 'gabarito' not in questoes[0]


def test_diagnostico_preserva_conflito_quando_mapa_fica_vazio():
    from src.importador.diagnostico import diagnosticar_caderno
    mapa = MapaGabarito()
    mapa.incorporar({1: 'A'})
    mapa.incorporar({1: 'B'})
    relatorio = diagnosticar_caderno('prova.pdf', [{'numero': 1}], mapa)
    assert 'gabaritos_conflitantes' in relatorio['motivos']
