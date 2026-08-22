from src.importador.extrator import _tem_duas_colunas


def _palavras_linha(top, inicio, quantidade, passo=10, largura=8):
    return [
        {"top": top, "x0": inicio + indice * passo, "x1": inicio + indice * passo + largura}
        for indice in range(quantidade)
    ]


def test_nao_trata_linhas_de_largura_total_como_duas_colunas():
    palavras = []
    for topo in range(10, 90, 8):
        palavras.extend(_palavras_linha(topo, 20, 12, passo=35))

    assert not _tem_duas_colunas(palavras, 800)


def test_detecta_duas_colunas_por_linhas_confinadas():
    palavras = []
    for topo in range(10, 90, 8):
        palavras.extend(_palavras_linha(topo, 20, 6, passo=25))
        palavras.extend(_palavras_linha(topo, 430, 6, passo=25))

    assert _tem_duas_colunas(palavras, 800)
