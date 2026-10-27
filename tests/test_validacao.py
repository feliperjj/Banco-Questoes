from src.importador.templates import (
    TEMPLATE_CEBRASPE, TEMPLATE_MULTIPROVAS, TEMPLATE_TABELA_HORIZONTAL,
    TEMPLATE_TABELA_VERTICAL, selecionar_template,
)
from src.importador.validacao import associar_gabaritos, validar_gabarito


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


def test_associacao_nao_desloca_gabarito_quando_falta_numero_no_meio():
    questoes = [{"numero": 1}, {"numero": 3}]
    resultado = associar_gabaritos(questoes, {1: "A", 2: "B"})
    assert questoes[0]["gabarito"] == "A"
    assert "gabarito" not in questoes[1]
    assert resultado["vinculados"] == 1
    assert "numeracao_ausente" not in {item["motivo"] for item in resultado["numeracao"]}


def test_numero_ausente_ou_invalido_nao_usa_ordem_visual():
    questoes = [{}, {"numero": "x"}, {"numero": 3}]
    resultado = associar_gabaritos(questoes, {1: "A", 2: "B", 3: "C"})
    assert "gabarito" not in questoes[0]
    assert "gabarito" not in questoes[1]
    assert questoes[2]["gabarito"] == "C"
    assert {item["motivo"] for item in resultado["numeracao"]} == {
        "numeracao_ausente", "numeracao_invalida"
    }


def test_duplicidade_bloqueia_no_mesmo_escopo_mas_repeticao_entre_cargos_eh_valida():
    duplicadas = [{"numero": 1, "cargo": "A"}, {"numero": 1, "cargo": "A"}]
    resultado = associar_gabaritos(duplicadas, {1: "A"})
    assert resultado["duplicados"] == [1]
    assert resultado["vinculados"] == 0

    distintas = [{"numero": 1, "cargo": "A"}, {"numero": 1, "cargo": "B"}]
    resultado = associar_gabaritos(
        distintas,
        {((('cargo', 'A'),), 1): "A", ((('cargo', 'B'),), 1): "B"},
    )
    assert resultado["duplicados"] == []
    assert resultado["vinculados"] == 2
