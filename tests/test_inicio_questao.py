from pathlib import Path

import pytest

from src.importador.extrator import _topo_primeira_secao, extrair_texto_pdf
from src.importador.parser import parsear_questoes
from src.importador.validacao import inicio_suspeito
from src.ui.components.question_editor import QuestionEditor


@pytest.mark.parametrize('texto, esperado', [
    ('demora. Para um Deus', True), ('“árvores são', True),
    ('Leia a afirmação', False), ('“Árvores são', False),
    ('2x + y = 3', False), ('', False),
])
def test_inicio_suspeito(texto, esperado):
    assert inicio_suspeito(texto) is esperado


def palavras(texto):
    return [dict(text=t, top=100, x0=i*10) for i,t in enumerate(texto.split())]


def test_frase_sobre_linguas_nao_vira_cabecalho():
    assert _topo_primeira_secao(palavras('Todas as línguas têm vícios de linguagem. A língua portuguesa também.')) is None
    assert _topo_primeira_secao(palavras('Língua Portuguesa Língua Inglesa')) == 98


def test_parser_alerta_sem_capitalizar_ou_descartar():
    q = parsear_questoes('QUESTÃO 1\ndemora. Para um Deus o automóvel não teria sentido.\nA) Um\nB) Dois\nC) Três\nD) Quatro')[0]
    assert q['enunciado'].startswith('demora.')
    assert q['confianca'] == 'baixa'


def test_editor_alerta_e_remove_aviso_apos_correcao(qt_application):
    editor = QuestionEditor()
    editor.load({'enunciado': 'demora. Texto cortado', 'tipo': 'certo_errado'})
    assert not editor.aviso_inicio.isHidden()
    editor.enunciado_input.setPlainText('Leia o texto completo.')
    assert editor.aviso_inicio.isHidden()


def test_caderno_fgv_recupera_primeira_questao_sem_misturar_colunas():
    caminho = Path('samples/administrador-fgv.pdf')
    if not caminho.exists():
        pytest.skip('Sample local não distribuído no CI')
    questoes = parsear_questoes(extrair_texto_pdf(str(caminho)), str(caminho))
    assert [q['numero'] for q in questoes] == list(range(1, 81))
    q = questoes[0]
    assert q['enunciado'].startswith('Leia a afirmação do escritor Vivaldo Coaracy')
    assert 'Deus' not in q['enunciado']
    assert [a['letra'] for a in q['alternativas']] == list('ABCDE')
    assert all('religiosa' not in a['texto'] for a in q['alternativas'])
