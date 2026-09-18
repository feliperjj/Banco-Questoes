from pathlib import Path

import pytest

from src.importador.extrator import _extrair_grade_identificada, extrair_gabaritos_pdf, extrair_texto
from src.importador.parser import parsear_questoes


def test_coluna_tipo_explicita_sem_fallback_para_t1():
    texto = 'Cargo: Analista de Sistemas\nQst T1 T2 T3 T4\n1 D B D A\n2 B C A D'
    assert _extrair_grade_identificada(None, texto, 'T2', 'Analista de Sistemas') == {1: 'B', 2: 'C'}
    assert _extrair_grade_identificada(None, texto, '', 'Analista de Sistemas') == {}
    assert _extrair_grade_identificada(None, texto, 'T1', 'Outro cargo') == {}


def test_cabecalho_cargo_numerado_nao_e_grade_horizontal():
    assert _extrair_grade_identificada(None, 'CARGO 1: ANALISTA\nItem 1 2 3', '', 'CARGO 1') is None


def test_grade_cargo_usa_numeros_das_celulas_e_nao_posicao():
    class Pagina:
        def extract_tables(self):
            return [[['CARGO', '.0\n1', '.0\n3', '.0\n4'], ['ALVO', 'B', 'X', 'C'], ['OUTRO', 'D', 'A', 'B']]]
    assert _extrair_grade_identificada(Pagina(), 'CARGO 1 3 4', '', 'ALVO') == {1: 'B', 3: 'X', 4: 'C'}
    assert _extrair_grade_identificada(Pagina(), 'CARGO 1 3 4', '', 'AL') == {}


def test_enumeracoes_e_palavra_justificativas_nao_dividem_questao():
    texto = '''IESES
1. Analise as justificativas e definições: 1. Elegância; 2. Postura; 3. Apuro.
a) Primeira opção
b) Segunda opção
2. O modelo contém
32 áreas de processo. Analise os itens.
a) Primeira opção
b) Segunda opção
3. Assinale a definição correta para o problema.
a) Primeira opção
b) Segunda opção
Prova Discursiva
1. Redija um texto sobre as alternativas.
a) Critério de avaliação
b) Outro critério
'''
    questoes = parsear_questoes(texto)
    assert [q['numero'] for q in questoes] == [1, 2, 3]
    assert '3. Apuro' in questoes[0]['enunciado']
    assert '32 áreas' in questoes[1]['enunciado']


@pytest.mark.parametrize('nome,cargo,tipo,esperado', [
    ('gabaritos.pdf', 'Analista de Sistemas', 'T1', 'D B A D B A B A A D A B C B A C C B C B C B A B B C C A D A D A B C D B D D D C'),
    ('gabarito-4.pdf', 'AGENTE ADMINISTRATIVO I', '', 'C C D C B D B A B C D D C B A B C C B D B B B X D C C A B D'),
])
def test_gabaritos_reais_conferidos_visualmente(nome, cargo, tipo, esperado):
    caminho = Path(__file__).parents[1] / 'samples' / 'lote_2026_08_22' / nome
    if not caminho.exists():
        pytest.skip('PDF local não distribuído no Git')
    assert extrair_gabaritos_pdf(str(caminho), tipo, cargo, usar_ocr=False) == dict(enumerate(esperado.split(), 1))


def test_crea_recupera_quarenta_numeros_sem_duplicar():
    caminho = Path(__file__).parents[1] / 'samples/lote_2026_08_22/agente_nivel_superior_analista_de_sistemas.pdf'
    if not caminho.exists():
        pytest.skip('PDF local não distribuído no Git')
    questoes = parsear_questoes(extrair_texto(str(caminho)), str(caminho))
    assert [q['numero'] for q in questoes] == list(range(1, 41))
    assert all(len(q['alternativas']) == 4 for q in questoes)


def test_mpo_bloco_comum_conferido_na_pagina_nove():
    caminho = Path(__file__).parents[1] / 'samples/gabarito_definitivo.pdf-CEBRASPE.pdf'
    if not caminho.exists():
        pytest.skip('PDF local não distribuído no Git')
    esperado = '''C E E E X C C E E E C E E C E C C E E C
X E E C C E C E C C E C E C E E C C E C
C E C E E E C E C C C E C E E C X C E C
C E C E E E C E C E X E C C C C E E C C
C E C C C E E C E C C C E E C C E E C X'''
    resultado = extrair_gabaritos_pdf(str(caminho), cargo='CONHECIMENTOS GERAIS COMUNS A TODAS AS ESPECIALIDADES', usar_ocr=False)
    assert {n: resultado[n] for n in range(1, 101)} == dict(enumerate(esperado.split(), 1))
