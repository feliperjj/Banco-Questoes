import pytest

from src.db.database import init_db
from src.db.models import Prova, ProvaQuestao, Questao, RevisaoEspacada, Tentativa
from src.importador.validacao import associar_gabaritos
from src.models.questoes_repo import criar_prova, criar_questao, finalizar_tentativa, iniciar_tentativa
from src.models.revisao_service import questoes_para_revisar_hoje


def _aprovar_fixture(questao_id, tmp_path, answer="Certo"):
    from helpers import approve_with_evidence
    fonte = tmp_path / "fonte.pdf"
    approve_with_evidence(questao_id, fonte, answer)


def test_associacao_nao_desloca_numero_faltante():
    questoes = [{"numero": 1}, {"numero": 2}, {"numero": 4}]
    resultado = associar_gabaritos(questoes, {1: "A", 2: "B", 4: "D"})
    assert resultado["vinculados"] == 3
    assert [q["gabarito"] for q in questoes] == ["A", "B", "D"]


def test_numeros_duplicados_nao_sao_aplicados_silenciosamente():
    questoes = [{"numero": 2}, {"numero": 2}]
    resultado = associar_gabaritos(questoes, {2: "A"})
    assert resultado["duplicados"] == [2]
    assert resultado["vinculados"] == 0


def test_criar_prova_ignora_sem_gabarito_e_falha_sem_avaliaveis(tmp_path):
    init_db(str(tmp_path / "integridade.db"))
    criar_questao({"enunciado": "sem resposta", "tipo": "certo_errado"})
    assert criar_prova("não deve criar", {}, 1, 0) == 0
    respondivel = criar_questao({"enunciado": "respondível", "tipo": "certo_errado", "gabarito": "Certo"})
    assert criar_prova("pendente não deve criar", {}, 1, 0) == 0

    _aprovar_fixture(respondivel, tmp_path)
    assert criar_prova("deve criar", {}, 1, 0) > 0


def test_anulada_nao_reduz_nota_nem_entra_na_revisao(tmp_path):
    init_db(str(tmp_path / "anulada.db"))
    anulada = criar_questao({"enunciado": "anulada", "tipo": "certo_errado", "gabarito": "Anulada"})
    certa = criar_questao({"enunciado": "certa", "tipo": "certo_errado", "gabarito": "Certo"})
    from src.models.questoes_repo import ultima_versao
    # Simula uma composição histórica, preservando as versões registradas.
    prova = Prova.create(nome="nota histórica", filtros="{}")
    ProvaQuestao.create(prova=prova.id, questao=anulada, ordem=1, questao_versao=ultima_versao(anulada).id)
    ProvaQuestao.create(prova=prova.id, questao=certa, ordem=2, questao_versao=ultima_versao(certa).id)
    # Representa uma tentativa antiga já aberta, antes da política nova de início.
    tentativa = Tentativa.create(prova=prova.id).id
    resultado = finalizar_tentativa(tentativa, {anulada: "Errado", certa: "Certo"}, 0)
    assert resultado["total"] == 1
    assert resultado["acertos"] == 1
    assert resultado["nota"] == 100
    RevisaoEspacada.create(questao=anulada, proxima_revisao=__import__("datetime").date.today())
    assert anulada not in {q["id"] for q in questoes_para_revisar_hoje()}


def test_prova_nova_nao_inclui_anulada(tmp_path):
    init_db(str(tmp_path / "somente-anulada.db"))
    criar_questao({"enunciado": "questão anulada", "tipo": "certo_errado", "gabarito": "Anulada"})
    assert criar_prova("sem avaliáveis", {}, 1, 0) == 0


def test_iniciar_tentativa_reutiliza_aberta_e_rejeita_prova_finalizada(tmp_path):
    init_db(str(tmp_path / "tentativa-unica.db"))
    questao = criar_questao({"enunciado": "questão válida", "tipo": "certo_errado", "gabarito": "Certo"})
    _aprovar_fixture(questao, tmp_path)
    prova = criar_prova("tentativa única", {}, 1, 0)
    primeira = iniciar_tentativa(prova)
    assert iniciar_tentativa(prova) == primeira
    assert Tentativa.select().where(Tentativa.prova == prova).count() == 1
    finalizar_tentativa(primeira, {questao: "C"}, 1)
    with pytest.raises(ValueError, match="já foi finalizada"):
        iniciar_tentativa(prova)
