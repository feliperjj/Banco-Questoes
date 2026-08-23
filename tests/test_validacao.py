from src.importador.templates import TEMPLATE_CEBRASPE, selecionar_template
from src.importador.validacao import validar_gabarito


def test_seleciona_template_cebraspe_por_layout_do_sample():
    assert selecionar_template("gabarito_definitivo.pdf-CEBRASPE.pdf").nome == TEMPLATE_CEBRASPE.nome


def test_validacao_identifica_faltantes_extras_e_numeros():
    questoes = [{"numero": 1}, {"numero": 2}, {"numero": 2}]
    resultado = validar_gabarito(questoes, {1: "A", 4: "B"})
    assert resultado["revisao_manual"]
    assert resultado["faltantes"] == [2]
    assert resultado["extras"] == [4]
    assert resultado["duplicados"] == [2]
