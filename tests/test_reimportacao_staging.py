import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.importador.reimportacao_staging import stage_proposals


def test_staging_e_idempotente_e_nao_aprova_propostas(tmp_path):
    path = tmp_path / "staging.sqlite3"
    proposal = {"arquivo": "prova.pdf", "sha256_fonte": "abc", "questao_id": 7,
                "ordem_candidata": 3, "status": "proposta_pendente_de_conferencia",
                "identidade_certificada": False, "revisao_humana": "pendente"}
    first = stage_proposals(path, [proposal])
    second = stage_proposals(path, [proposal])
    assert first["novas"] == 1
    assert second["novas"] == 0
    assert second["total"] == second["pendentes"] == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT status FROM propostas_reimportacao").fetchone()[0] == "pendente"


def test_falha_em_staging_faz_rollback(tmp_path):
    path = tmp_path / "staging.sqlite3"
    proposals = [{"arquivo": "p.pdf", "ordem_candidata": n} for n in (1, 2, 3)]
    with pytest.raises(RuntimeError, match="falha simulada"):
        stage_proposals(path, proposals, fail_after=2)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM propostas_reimportacao").fetchone()[0] == 0


def test_aplicacao_aprovada_preserva_versao_e_reexecucao_nao_duplica(tmp_path):
    from helpers import write_test_pdf
    from src.db.database import init_db
    from src.db.models import QuestaoVersao
    from src.importador.reimportacao_staging import decide_proposal, list_proposals
    from src.models import questoes_repo as repo
    from scripts.gerenciar_staging_reimportacao import aplicar_aprovadas

    database_path = tmp_path / "acervo.db"
    staging_path = tmp_path / "staging.sqlite3"
    source = write_test_pdf(tmp_path / "origem.pdf")
    init_db(str(database_path))
    question_id = repo.criar_questao({
        "numero_oficial": 1, "enunciado": "Texto atual de teste.",
        "tipo": "multipla_escolha", "gabarito": "A",
        "alternativas": [{"letra": letter, "texto": f"Alternativa {letter}"} for letter in "ABCDE"],
    })
    proof_id = repo.criar_prova_cadastrada(
        "Prova de staging", [{"_questao_id": question_id}], arquivo_questoes=str(source),
    )
    current = repo.obter_questao(question_id)
    proposed = {key: value for key, value in current.items() if key != "id"}
    proposed["enunciado"] = "Texto corrigido por proposta aprovada."
    payload = {
        "arquivo": "origem.pdf", "fonte_path": str(source),
        "sha256_fonte": hashlib.sha256(source.read_bytes()).hexdigest(),
        "prova_id": proof_id, "questao_id": question_id, "ordem_candidata": 1,
        "status": "proposta_pendente_de_conferencia",
        "conteudo_atual": {key: current.get(key) for key in proposed},
        "proposta": proposed, "diferencas": {"enunciado": {"atual": current["enunciado"], "proposto": proposed["enunciado"]}},
    }
    stage_proposals(staging_path, [payload])
    proposal = list_proposals(staging_path)[0]
    decide_proposal(staging_path, proposal["chave"], decision="aprovada",
                    reviewer="Pessoa de teste", rationale="Correspondência conferida na fixture sintética.")

    before = QuestaoVersao.select().where(QuestaoVersao.questao == question_id).count()
    result = aplicar_aprovadas(staging_path, database_path)

    assert result["aplicadas"] == 1
    assert result["backup"] and Path(result["backup"]).is_file()
    assert QuestaoVersao.select().where(QuestaoVersao.questao == question_id).count() == before + 1
    versions = list(QuestaoVersao.select().where(QuestaoVersao.questao == question_id).order_by(QuestaoVersao.numero_versao))
    assert json.loads(versions[-2].conteudo_json)["enunciado"] == "Texto atual de teste."
    assert versions[-1].revisao_conteudo == "pendente"
    assert repo.obter_questao(question_id)["enunciado"] == proposed["enunciado"]
    assert not aplicar_aprovadas(staging_path, database_path)["aplicadas"]
