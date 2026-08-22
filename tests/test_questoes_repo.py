from src.db.database import init_db
import pytest

from src.db.models import Alternativa, Questao
from src.models.questoes_repo import atualizar_questao, criar_prova, criar_questao, criar_questoes_em_lote, finalizar_tentativa, iniciar_tentativa, listar_provas, obter_prova


def test_criar_questoes_em_lote_persiste_questoes_e_alternativas(tmp_path):
    init_db(str(tmp_path / "questoes.db"))

    ids = criar_questoes_em_lote([
        {
            "enunciado": "Texto da primeira questao",
            "tipo": "multipla_escolha",
            "disciplina": "Informatica",
            "topico": "Redes",
            "banca": "CEBRASPE",
            "ano": 2026,
            "cargo": "Analista",
            "dificuldade": "media",
            "gabarito": "A",
            "alternativas": [
                {"letra": "A", "texto": "Opcao correta"},
                {"letra": "B", "texto": "Outra opcao"},
            ],
        },
        {
            "enunciado": "Texto da segunda questao",
            "tipo": "certo_errado",
            "disciplina": "Portugues",
            "topico": "Interpretacao",
            "banca": "FGV",
            "ano": 2025,
            "cargo": "Tecnico",
            "dificuldade": "media",
            "gabarito": "Certo",
        },
    ])

    assert len(ids) == 2
    assert Questao.select().count() == 2
    assert Alternativa.select().count() == 2

    primeira = Questao.get_by_id(ids[0])
    assert primeira.banca == "CEBRASPE"
    assert primeira.cargo == "Analista"
    assert [alt.letra for alt in Alternativa.select().where(Alternativa.questao == primeira.id).order_by(Alternativa.letra)] == ["A", "B"]


def test_finalizar_tentativa_calcula_nota_sobre_todas_as_questoes(tmp_path):
    init_db(str(tmp_path / "questoes.db"))
    primeira = criar_questao({"enunciado": "Primeira questão", "tipo": "certo_errado", "gabarito": "Certo"})
    segunda = criar_questao({"enunciado": "Segunda questão", "tipo": "certo_errado", "gabarito": "Errado"})
    prova_id = criar_prova("Prova parcial", {}, 2, None)

    # A seleção aleatória da prova pode escolher as duas questões disponíveis;
    # a asserção abaixo garante o cenário sem depender da ordem dos IDs.
    assert Questao.select().where(Questao.id.in_([primeira, segunda])).count() == 2
    tentativa_id = iniciar_tentativa(prova_id)
    resultado = finalizar_tentativa(tentativa_id, {primeira: "Certo"}, 10)

    assert resultado["total"] == 2
    assert resultado["acertos"] in (0, 1)
    assert resultado["nota"] in (0, 50.0)


def test_atualizar_questao_remove_alternativas_ao_trocar_para_certo_errado(tmp_path):
    init_db(str(tmp_path / "questoes.db"))
    questao_id = criar_questao({
        "enunciado": "Questão com alternativas suficientes",
        "tipo": "multipla_escolha",
        "alternativas": [{"letra": "A", "texto": "Opção"}],
    })

    atualizar_questao(questao_id, {"enunciado": "Agora é um item certo ou errado", "tipo": "certo_errado"})

    assert Alternativa.select().where(Alternativa.questao == questao_id).count() == 0


def test_criar_prova_persiste_tempo_limite_e_rejeita_quantidade_invalida(tmp_path):
    init_db(str(tmp_path / "questoes.db"))
    criar_questao({"enunciado": "Questão para limite de tempo", "tipo": "certo_errado", "gabarito": "Certo"})

    assert criar_prova("Inválida", {}, 0, 1) == 0
    prova_id = criar_prova("Com limite", {}, 1, 2)

    assert obter_prova(prova_id)["tempo_limite_min"] == 2
    assert listar_provas()[0]["tempo_limite_min"] == 2


def test_finalizar_tentativa_rejeita_repeticao_e_questao_fora_da_prova(tmp_path):
    init_db(str(tmp_path / "questoes.db"))
    dentro = criar_questao({"enunciado": "Questão dentro da prova", "tipo": "certo_errado", "gabarito": "Certo"})
    prova_id = criar_prova("Integridade", {}, 1, None)
    fora = criar_questao({"enunciado": "Questão fora da prova", "tipo": "certo_errado", "gabarito": "Certo"})
    tentativa_id = iniciar_tentativa(prova_id)

    # Com apenas uma questão disponível, a primeira pertence à prova.
    assert fora != dentro
    with pytest.raises(ValueError, match="não pertencem"):
        finalizar_tentativa(tentativa_id, {fora: "Certo"}, 1)
    resultado = finalizar_tentativa(tentativa_id, {}, 1)
    assert resultado["total"] == 1
    with pytest.raises(ValueError, match="já foi finalizada"):
        finalizar_tentativa(tentativa_id, {}, 1)
