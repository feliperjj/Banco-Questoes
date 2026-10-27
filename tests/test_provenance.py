import sqlite3
import json
import pytest

from src.db.database import init_db
from src.db.migrations import CURRENT_SCHEMA_VERSION
import src.db.database as database_module
from src.db.models import EvidenciaQuestao, ExecucaoExtracao, ProvaQuestao, QuestaoVersao, RevisaoConteudo, RevisaoGabarito
from src.models import questoes_repo as repo
from src.models.provenance_service import (
    add_evidence,
    assess_version,
    begin_source_verification_batch,
    create_question_version,
    create_source,
    end_source_verification_batch,
    review_answer,
    review_content,
    resolve_diagnostic,
    version_is_eligible,
    verify_source,
)


def _question():
    return {
        "enunciado": "Selecione a primeira opção.",
        "tipo": "multipla_escolha",
        "gabarito": "A",
        "alternativas": [{"letra": letter, "texto": f"Opção {letter}"} for letter in "ABCDE"],
    }


def _approve_question(question_id, source_path):
    from helpers import approve_with_evidence
    return approve_with_evidence(question_id, source_path, "A")


def test_legado_recebe_snapshot_pendente_com_backup_restauravel(tmp_path):
    path = tmp_path / "legado.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE questoes (id INTEGER PRIMARY KEY, enunciado TEXT NOT NULL, tipo TEXT NOT NULL)")
        connection.execute("INSERT INTO questoes (enunciado, tipo) VALUES ('Questão legada', 'certo_errado')")

    database_module.LAST_VERIFIED_SCHEMA_BACKUP = None
    database = init_db(str(path))

    assert database.execute_sql("SELECT version FROM schema_version").fetchone()[0] == CURRENT_SCHEMA_VERSION
    assert database.execute_sql("SELECT COUNT(*) FROM questoes").fetchone()[0] == 1
    version = QuestaoVersao.get(QuestaoVersao.questao == 1)
    assert version.revisao_conteudo == "pendente"
    assert version.revisao_gabarito == "desconhecido"
    assert version.documento_fonte_id is None
    assert not version_is_eligible(version)
    backup = database_module.LAST_VERIFIED_SCHEMA_BACKUP
    assert backup and backup.is_file()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_attempt_uses_immutable_question_version_after_later_edit(tmp_path):
    path = tmp_path / "attempt.db"
    source = tmp_path / "source.pdf"
    from helpers import write_test_pdf
    write_test_pdf(source)
    init_db(str(path))

    question_id = repo.criar_questoes_em_lote(
        [_question()], source_path=str(source),
        extraction_metadata={"profile": "integracao_sintetica_v1", "diagnostics": [{"code": "fixture"}]},
    )[0]
    first_version = repo.ultima_versao(question_id)
    assert first_version.revisao_conteudo == "pendente"
    assert not assess_version(first_version.id)["liberada"]
    assert repo.contar_questoes_elegiveis() == 0

    approved_version = _approve_question(question_id, source)
    assert version_is_eligible(QuestaoVersao.get_by_id(approved_version))
    proof_id = repo.criar_prova("Snapshot", {}, 1, 0)
    proof_question = ProvaQuestao.get(ProvaQuestao.prova == proof_id)
    assert proof_question.questao_versao_id == approved_version

    attempt_id = repo.iniciar_tentativa(proof_id)
    repo.salvar_progresso(attempt_id, {question_id: "A"}, 0, 12)
    assert repo.obter_progresso(attempt_id) == {"respostas": {question_id: "A"}, "indice": 0, "tempo_seg": 12}
    repo.atualizar_questao(question_id, {"gabarito": "B"})
    assert repo.ultima_versao(question_id).numero_versao == approved_version + 1
    assert repo.ultima_versao(question_id).documento_fonte_id == first_version.documento_fonte_id

    result = repo.finalizar_tentativa(attempt_id, {question_id: "A"}, 7)

    assert result["acertos"] == 1
    assert result["total"] == 1
    assert result["nota"] == 100.0


def test_fonte_alterada_retira_versao_de_elegibilidade(tmp_path):
    path = tmp_path / "tamper.db"
    source = tmp_path / "source.pdf"
    from helpers import write_test_pdf
    write_test_pdf(source)
    init_db(str(path))
    question_id = repo.criar_questao(_question())
    version_id = _approve_question(question_id, source)
    assert version_is_eligible(QuestaoVersao.get_by_id(version_id))

    source.write_bytes(b"%PDF-1.4 changed")

    assert not version_is_eligible(QuestaoVersao.get_by_id(version_id))
    assert repo.contar_questoes_elegiveis() == 0


def test_importacao_guarda_origem_execucao_e_invalidacao_ao_juntar_evidencia(tmp_path):
    path = tmp_path / "importacao.db"
    source = tmp_path / "source.pdf"
    from helpers import write_test_pdf
    write_test_pdf(source)
    init_db(str(path))
    question_id = repo.criar_questoes_em_lote(
        [_question()],
        source_path=str(source),
        extraction_metadata={
            "profile": "fixture_profile_v1",
            "parameters": {"columns": 2},
            "diagnostics": [{"code": "fixture"}],
        },
    )[0]
    version = repo.ultima_versao(question_id)
    assert version.documento_fonte is not None
    assert version.execucao_extracao_id is not None
    extraction = ExecucaoExtracao.get_by_id(version.execucao_extracao_id)
    assert extraction.perfil == "fixture_profile_v1"
    assert extraction.parametros_json == '{"columns":2}'
    assert extraction.diagnosticos_json == '[{"code": "fixture"}]'

    approved_version = _approve_question(question_id, source)
    assert version_is_eligible(QuestaoVersao.get_by_id(approved_version))
    evidence_id = add_evidence(
        approved_version,
        create_source(source, tipo="pdf"),
        part="contexto",
        page=1,
        bounds=(0, 0, 612, 792),
        coordinate_system="pdf-point; origem superior esquerda",
        page_size=(612, 792),
        rotation=0,
        scope={"prova": "fixture", "cargo": "fixture", "codigo": "T1", "versao": "1"},
        excerpt="Nova evidência exige nova revisão.",
    )
    updated = QuestaoVersao.get_by_id(approved_version)
    assert evidence_id
    assert updated.revisao_conteudo == "pendente"
    assert updated.revisao_gabarito == "definitivo_confirmado"
    assert not version_is_eligible(updated)


def test_decisoes_exigem_ids_existentes_da_parte_correta(tmp_path):
    from helpers import write_test_pdf

    path = tmp_path / "evidence.db"
    source = write_test_pdf(tmp_path / "source.pdf")
    init_db(str(path))
    question_id = repo.criar_questao(_question())
    version_id = _approve_question(question_id, source)
    evidence = list(EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == version_id))
    content_id = next(item.id for item in evidence if item.parte == "conteudo")
    answer_id = next(item.id for item in evidence if item.parte == "gabarito")

    with pytest.raises(ValueError, match="outra parte"):
        review_content(version_id, decision="conferido", reviewer="Teste", rationale="Teste", evidence_ids=[answer_id])
    with pytest.raises(ValueError, match="outra parte"):
        review_answer(version_id, answer="A", decision="definitivo_confirmado", reviewer="Teste", rationale="Teste", evidence_ids=[content_id])
    with pytest.raises(ValueError, match="não existem"):
        review_content(version_id, decision="conferido", reviewer="Teste", rationale="Teste", evidence_ids=[999999])


def test_evidencia_rejeita_pagina_ausente_e_repetir_snapshot_e_regiao_nao_duplica(tmp_path):
    from helpers import approve_with_evidence, write_test_pdf

    path = tmp_path / "idempotence.db"
    source = write_test_pdf(tmp_path / "source.pdf")
    init_db(str(path))
    question_id = repo.criar_questao(_question())
    version_id = approve_with_evidence(question_id, source, "A")
    version = QuestaoVersao.get_by_id(version_id)
    source_id = version.documento_fonte_id
    scope = {"prova": "fixture", "cargo": "fixture", "codigo": "T1", "versao": "1"}
    before = EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == version_id).count()
    content_review = RevisaoConteudo.select().where(RevisaoConteudo.questao_versao == version_id).order_by(RevisaoConteudo.id.desc()).first()
    answer_review = RevisaoGabarito.select().where(RevisaoGabarito.questao_versao == version_id).order_by(RevisaoGabarito.id.desc()).first()
    assert review_content(version_id, decision="conferido", reviewer="Teste automatizado",
                          rationale=content_review.justificativa,
                          evidence_ids=json.loads(content_review.evidencia_json)) == content_review.id
    assert review_answer(version_id, answer="A", decision="definitivo_confirmado",
                         reviewer="Teste automatizado", rationale=answer_review.justificativa,
                         evidence_ids=json.loads(answer_review.evidencia_json)) == answer_review.id
    assert create_question_version(question_id, source_id=source_id) == version_id
    same_id = add_evidence(
        version_id, source_id, part="conteudo", page=1, bounds=(0, 0, 612, 396),
        coordinate_system="pdf-point; origem superior esquerda", page_size=(612, 792),
        rotation=0, scope=scope, excerpt="Área sintética para conteúdo; não representa revisão do acervo.",
    )
    assert same_id == next(item.id for item in EvidenciaQuestao.select().where(
        (EvidenciaQuestao.questao_versao == version_id) & (EvidenciaQuestao.parte == "conteudo")
    ))
    assert EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == version_id).count() == before
    with pytest.raises(ValueError, match="não existe"):
        add_evidence(
            version_id, source_id, part="conteudo", page=2, bounds=(0, 0, 612, 396),
            coordinate_system="pdf-point; origem superior esquerda", page_size=(612, 792),
            rotation=0, scope=scope,
        )


def test_diagnostico_suspeita_evidenciada_pode_ser_resolvida_sem_ignorar_erro_objetivo(tmp_path):
    from helpers import approve_with_evidence, write_test_pdf

    path = tmp_path / "diagnostics.db"
    source = write_test_pdf(tmp_path / "source.pdf")
    init_db(str(path))
    question_data = _question()
    question_data["alternativas"][1]["texto"] = "Texto da alternativa B) continuação longa"
    question_id = repo.criar_questao(question_data)
    version_id = approve_with_evidence(question_id, source, "A")
    assessment = assess_version(version_id)
    assert not assessment["liberada"]
    alert = next(item for item in assessment["alertas"] if item["codigo"] == "alternativas_possivelmente_fundidas")
    content_evidence_id = next(item.id for item in EvidenciaQuestao.select().where(
        (EvidenciaQuestao.questao_versao == version_id) & (EvidenciaQuestao.parte == "conteudo")
    ))
    resolution_id = resolve_diagnostic(
        version_id, code=alert["codigo"], decision="alerta_descartado",
        reviewer="Pessoa de teste", rationale="Conferi a alternativa completa na fonte sintética.",
        evidence_ids=[content_evidence_id],
    )
    assert resolution_id > 0
    result = assess_version(version_id)
    assert result["liberada"]
    assert next(item for item in result["alertas"] if item["codigo"] == alert["codigo"])["resolucao"]["decisao"] == "alerta_descartado"

    with pytest.raises(ValueError, match="bloqueios objetivos"):
        resolve_diagnostic(
            version_id, code="enunciado_vazio", decision="alerta_descartado",
            reviewer="Pessoa de teste", rationale="Não pode dispensar um impedimento estrutural.",
            evidence_ids=[content_evidence_id],
        )


def test_analise_nao_aprova_por_comprimento_de_alternativa(tmp_path):
    from helpers import approve_with_evidence, write_test_pdf

    init_db(str(tmp_path / "long.db"))
    data = _question()
    data["alternativas"][2]["texto"] = "Resposta legítima. " * 500
    question_id = repo.criar_questao(data)
    version_id = approve_with_evidence(question_id, write_test_pdf(tmp_path / "long.pdf"), "A")
    result = assess_version(version_id)
    assert result["liberada"]
    assert not any("comprimento" in item["mensagem"].lower() for item in result["pendencias"])


def test_cache_de_hash_e_limitado_a_execucao_e_revalidacao_critica_le_de_novo(tmp_path, monkeypatch):
    from pathlib import Path
    from helpers import write_test_pdf

    init_db(str(tmp_path / "source-cache.db"))
    path = write_test_pdf(tmp_path / "cached-source.pdf")
    source_id = create_source(path, tipo="pdf")
    original = Path.read_bytes
    reads = []

    def counted(file):
        reads.append(str(file))
        return original(file)

    monkeypatch.setattr(Path, "read_bytes", counted)
    token = begin_source_verification_batch()
    try:
        assert verify_source(source_id)["integro"]
        assert verify_source(source_id)["integro"]
        assert len(reads) == 1
    finally:
        end_source_verification_batch(token)
    path.write_bytes(original(path) + b"\n")
    assert not verify_source(source_id)["integro"]
    assert len(reads) == 2
