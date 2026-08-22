import pytest

from src.importador.lote import aplicar_classificacao_as_questoes, aplicar_gabarito_as_questoes, parsear_gabarito_em_lote


def test_parsear_gabarito_em_lote_encontra_letras_e_certo_errado():
    assert parsear_gabarito_em_lote("A D B C E certo errado") == ["A", "D", "B", "C", "E", "CERTO", "ERRADO"]


def test_parsear_gabarito_em_lote_ignora_letras_dentro_de_palavras():
    assert parsear_gabarito_em_lote("Caderno A Exemplo B") == ["A", "B"]


def test_aplicar_gabarito_preserva_ce_em_multipla_escolha_e_mapeia_certo_errado():
    questoes = [
        {"tipo": "multipla_escolha"},
        {"tipo": "multipla_escolha"},
        {"tipo": "certo_errado"},
        {"tipo": "certo_errado"},
    ]

    respostas = aplicar_gabarito_as_questoes(questoes, ["C", "E", "C", "E"])

    assert respostas == ["C", "E", "Certo", "Errado"]
    assert [questao["gabarito"] for questao in questoes] == respostas


def test_aplicar_gabarito_rejeita_quantidade_diferente():
    with pytest.raises(ValueError, match="1 respostas para 2"):
        aplicar_gabarito_as_questoes([{}, {}], ["A"])


def test_aplicar_classificacao_as_questoes_no_intervalo_informado():
    questoes = [{"enunciado": "q1"}, {"enunciado": "q2"}, {"enunciado": "q3"}]

    quantidade = aplicar_classificacao_as_questoes(questoes, 2, 3, "Informatica", "Redes")

    assert quantidade == 2
    assert questoes[0] == {"enunciado": "q1"}
    assert questoes[1]["disciplina"] == "Informatica"
    assert questoes[1]["topico"] == "Redes"
    assert questoes[2]["disciplina"] == "Informatica"
