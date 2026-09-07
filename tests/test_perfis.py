from src.importador.parser import parsear_questoes
from src.importador.perfis.segmentacao import segmentar


def test_marcador_nomeado_tem_prioridade_sobre_numeros_do_texto():
    texto = 'QUESTÃO 1\nAvalie o exemplo apresentado.\n1 Primeiro trecho\n2 Segundo trecho\nA) Uma resposta\nB) Outra resposta'
    questoes = parsear_questoes(texto)
    assert len(questoes) == 1
    assert questoes[0]['perfil_importacao'] == 'questoes_nomeadas_v1'
    assert '2 Segundo trecho' in questoes[0]['enunciado']


def test_formato_desconhecido_exige_revisao():
    resultado = segmentar('Texto sem marcadores reconhecidos', '', '')
    assert resultado.perfil == 'generico_v1'
    assert resultado.aviso
    assert not resultado.candidatos


def test_perfil_sequencial_independe_do_nome_da_banca():
    texto = '1 Esta é uma afirmação suficientemente longa.\n2 Esta é outra afirmação suficientemente longa.'
    for banca in ('', 'Uma banca nova'):
        resultado = segmentar(texto, texto, banca)
        assert resultado.perfil == 'certo_errado_sequencial_v1'
        assert len(resultado.candidatos) == 2
