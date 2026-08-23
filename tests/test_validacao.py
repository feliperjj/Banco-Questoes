from src.importador.templates import (
    TEMPLATE_CEBRASPE, TEMPLATE_MULTIPROVAS, TEMPLATE_TABELA_HORIZONTAL,
    TEMPLATE_TABELA_VERTICAL, selecionar_template,
)
from src.importador.validacao import validar_gabarito


def test_seleciona_template_cebraspe_por_layout_do_sample():
    assert selecionar_template("gabarito_definitivo.pdf-CEBRASPE.pdf").nome == TEMPLATE_CEBRASPE.nome


def test_seleciona_templates_por_evidencia_explicita():
    assert selecionar_template("gab.pdf", "PROVA 1 PROVA 2").nome == TEMPLATE_MULTIPROVAS.nome
    assert selecionar_template("gab.pdf", "Item 1 Certo Errado").nome == TEMPLATE_TABELA_VERTICAL.nome
    assert selecionar_template("gab.pdf", "Gabarito Resposta").nome == TEMPLATE_TABELA_HORIZONTAL.nome


def test_validacao_identifica_faltantes_extras_e_numeros():
    questoes = [{"numero": 1}, {"numero": 2}, {"numero": 2}]
    resultado = validar_gabarito(questoes, {1: "A", 4: "B"})
    assert resultado["revisao_manual"]
    assert resultado["faltantes"] == [2]
    assert resultado["extras"] == [4]
    assert resultado["duplicados"] == [2]
