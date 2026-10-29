"""Policy-specific coverage for preliminary answer certificates."""

import hashlib
import json
from pathlib import Path

import pytest

from src.db.models import EvidenciaQuestao, RevisaoGabarito
from src.models import provenance_service as provenance
from src.models import questoes_repo as repo
from src.models.provenance_service import (
    AUTOMATIC_RULE_VERSION,
    add_evidence,
    create_question_version,
    create_source,
    get_automatic_validation,
    record_automatic_validation,
)

from test_automatic_validation import _pdf_and_crop


def _preliminary_fixture(tmp_path, monkeypatch, *, policy=True):
    root = tmp_path / "policy-root"
    samples = root / "samples"
    (root / "config").mkdir(parents=True)
    samples.mkdir()
    source, asset = _pdf_and_crop(tmp_path)
    # Avoid cross-test source-row deduplication in the shared test database.
    source.write_bytes(source.read_bytes() + ("\n% " + tmp_path.name).encode())
    book = samples / "book.pdf"
    answer = samples / "answer.pdf"
    book.write_bytes(source.read_bytes())
    # Keep rendered evidence identical while giving the answer document its
    # own source identity (the provenance table deduplicates equal hashes).
    answer.write_bytes(source.read_bytes() + b"\n% answer-document")

    digest_book = hashlib.sha256(book.read_bytes()).hexdigest()
    digest_answer = hashlib.sha256(answer.read_bytes()).hexdigest()
    catalogue = {
        "book.pdf": {"gabarito": "answer.pdf", "confirmado": True,
                      "evidencia": "fixture", "cargo": "Cargo Analista",
                      "prova": "Prova Teste", "codigo": "1", "versao": "1"}
    }
    (root / "config" / "gabaritos.json").write_text(json.dumps(catalogue), encoding="utf-8")
    payload = {"versao": 1, "fontes": [{
        "catalogo_chave": "book.pdf", "caderno_sha256": digest_book,
        "gabarito_sha256": digest_answer,
        "aceitar_preliminar_para_estudo": True,
    }]} if policy else {"versao": 1, "fontes": []}
    (root / "config" / "gabaritos_estudo.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(provenance, "ROOT_DIR", root)

    qid = repo.criar_questao({"numero_oficial": 9, "enunciado": "Completa.",
                              "tipo": "multipla_escolha", "gabarito": "A",
                              "alternativas": [{"letra": l, "texto": name}
                                               for l, name in zip("ABCDE", ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])]})
    sid = create_source(book, tipo="pdf")
    answer_sid = create_source(answer, tipo="pdf")
    vid = create_question_version(qid, source_id=sid)
    scope = {"prova": "Prova Teste", "cargo": "Cargo Analista", "codigo": "1", "versao": "sha256:" + digest_book}
    cid = add_evidence(vid, sid, part="conteudo", page=1, bounds=(0, 0, 600, 240),
                       coordinate_system="pdf-point; origem superior esquerda", page_size=(600, 240),
                       rotation=0, scope=scope)
    aid = add_evidence(vid, answer_sid, part="gabarito", page=1, bounds=(0, 0, 600, 240),
                       coordinate_system="pdf-point; origem superior esquerda", page_size=(600, 240),
                       rotation=0, scope={**scope, "situacao_gabarito": "preliminar"})
    manifest = {
        "regra": AUTOMATIC_RULE_VERSION, "numero_oficial": 9, "gabarito": "A", "escopo": scope,
        "identidade": {"catalogo_chave": "book.pdf",
                        "catalogo_sha256": hashlib.sha256((root / "config" / "gabaritos.json").read_bytes()).hexdigest(),
                        "conteudo_termos": ["Prova Teste", "Cargo Analista", "Completa", "Alpha", "Bravo", "Charlie", "Delta", "Echo"],
                        "gabarito_termos": ["Gabarito", "9-A"]},
        "checks": {key: True for key in ("identidade", "numero", "conteudo_completo", "alternativas", "contexto", "recursos", "gabarito")},
        "apresentacao": {"modo": "facsimile", "questao": [{"path": str(asset),
            "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(), "evidencia_id": cid, "scale": 2.0}]},
        "verificador": {"metodo": "fixture", "versao": AUTOMATIC_RULE_VERSION},
    }
    return root, vid, cid, aid, manifest, digest_book, digest_answer


def test_preliminar_allowlist_exata_libera_e_preserva_aviso(tmp_path, monkeypatch):
    _, vid, cid, aid, manifest, _, _ = _preliminary_fixture(tmp_path, monkeypatch)
    record_automatic_validation(vid, evidence_ids=[cid, aid], manifest=manifest)
    result = get_automatic_validation(vid)
    assert result["valida"]
    assert "gabarito_preliminar_aceito_para_estudo" in result["motivos"]
    assessed = provenance.assess_version(vid)
    assert assessed["estado_gabarito"] == "preliminar"
    assert any(item["codigo"] == "gabarito_preliminar_aceito_para_estudo" for item in assessed["pendencias"])


@pytest.mark.parametrize("change", [
    {"catalogo_chave": "other.pdf"},
    {"caderno_sha256": "0" * 64},
    {"gabarito_sha256": "1" * 64},
])
def test_preliminar_mismatch_de_fonte_catalogo_ou_hash_bloqueia(tmp_path, monkeypatch, change):
    _, vid, cid, aid, manifest, _, _ = _preliminary_fixture(tmp_path, monkeypatch)
    policy = json.loads((provenance.ROOT_DIR / "config" / "gabaritos_estudo.json").read_text())
    policy["fontes"][0].update(change)
    (provenance.ROOT_DIR / "config" / "gabaritos_estudo.json").write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError):
        record_automatic_validation(vid, evidence_ids=[cid, aid], manifest=manifest)


@pytest.mark.parametrize("payload", [
    {}, {"versao": 2, "fontes": []}, {"versao": 1, "fontes": [{"aceitar_preliminar_para_estudo": "true"}]},
])
def test_politica_ausente_invalida_ou_tipo_incorreto_fecha_por_padrao(tmp_path, monkeypatch, payload):
    _, vid, cid, aid, manifest, _, _ = _preliminary_fixture(tmp_path, monkeypatch)
    (provenance.ROOT_DIR / "config" / "gabaritos_estudo.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        record_automatic_validation(vid, evidence_ids=[cid, aid], manifest=manifest)


def test_revogacao_da_allowlist_invalida_certificado_existente(tmp_path, monkeypatch):
    _, vid, cid, aid, manifest, _, _ = _preliminary_fixture(tmp_path, monkeypatch)
    record_automatic_validation(vid, evidence_ids=[cid, aid], manifest=manifest)
    policy_path = provenance.ROOT_DIR / "config" / "gabaritos_estudo.json"
    payload = json.loads(policy_path.read_text())
    payload["fontes"][0]["aceitar_preliminar_para_estudo"] = False
    policy_path.write_text(json.dumps(payload), encoding="utf-8")
    result = get_automatic_validation(vid)
    assert not result["valida"]
    assert "gabarito_preliminar_nao_autorizado_para_estudo" in result["motivos"]


def test_mistura_preliminar_definitivo_continua_bloqueada(tmp_path, monkeypatch):
    _, vid, cid, aid, manifest, _, _ = _preliminary_fixture(tmp_path, monkeypatch)
    extra = add_evidence(vid, EvidenciaQuestao.get_by_id(aid).documento_fonte_id, part="gabarito", page=1,
                         bounds=(0, 0, 600, 240), coordinate_system="pdf-point; origem superior esquerda",
                         page_size=(600, 240), rotation=0,
                         scope={**manifest["escopo"], "situacao_gabarito": "definitivo"})
    with pytest.raises(ValueError, match="Situação de gabarito"):
        record_automatic_validation(vid, evidence_ids=[cid, aid, extra], manifest=manifest)


@pytest.mark.parametrize("decision", ["anulado", "conflitante"])
def test_veto_humano_anulado_ou_conflitante_nao_e_superado(tmp_path, monkeypatch, decision):
    _, vid, cid, aid, manifest, _, _ = _preliminary_fixture(tmp_path, monkeypatch)
    record_automatic_validation(vid, evidence_ids=[cid, aid], manifest=manifest)
    RevisaoGabarito.create(questao_versao=vid, gabarito="A", decisao=decision,
                           responsavel_declarado="teste", justificativa="veto", evidencia_json=json.dumps([aid]))
    assert not get_automatic_validation(vid)["valida"]


@pytest.mark.parametrize("policy_enabled, expected", [(True, 1), (False, 0)])
def test_importacao_lote_gate_preliminar_usa_allowlist_real(tmp_path, monkeypatch, policy_enabled, expected):
    """The adapter must pass the real source hashes/status through certification."""
    from src.importador import lote_verificado as adapter
    from test_importacao_lote_verificado import _write_text_pdf
    from src.db.database import init_db
    from src.importador.lote_verificado import salvar_lote_verificado

    init_db(str(tmp_path / "adapter.sqlite"))
    root = tmp_path / "adapter-root"
    samples = root / "samples"
    (root / "config").mkdir(parents=True)
    samples.mkdir()
    book = _write_text_pdf(samples / "book.pdf", [
        "Prova Teste", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        "QUESTAO 1", "Complete statement for official question one.",
        "A) Alpha option", "B) Bravo option", "C) Charlie option", "D) Delta option", "E) Echo option",
    ])
    answer = _write_text_pdf(samples / "answer.pdf", [
        "Prova Teste", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        "GABARITO PRELIMINAR", "1 A",
    ])
    book_hash = hashlib.sha256(book.read_bytes()).hexdigest()
    answer_hash = hashlib.sha256(answer.read_bytes()).hexdigest()
    catalog = {"book.pdf": {"gabarito": "answer.pdf", "confirmado": True, "evidencia": "fixture",
                             "cargo": "ANALISTA DE SISTEMAS", "prova": "Prova Teste", "codigo": "A123"}}
    (root / "config" / "gabaritos.json").write_text(json.dumps(catalog), encoding="utf-8")
    payload = {"versao": 1, "fontes": [{"catalogo_chave": "book.pdf", "caderno_sha256": book_hash,
        "gabarito_sha256": answer_hash, "aceitar_preliminar_para_estudo": True}]} if policy_enabled else {"versao": 1, "fontes": []}
    (root / "config" / "gabaritos_estudo.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(adapter, "ROOT_DIR", root)
    monkeypatch.setattr(provenance, "ROOT_DIR", root)
    question = {"numero": 1, "numero_oficial": 1, "enunciado": "Complete statement for official question one.",
                "texto_apoio": "", "tipo": "multipla_escolha", "disciplina": "", "topico": "", "banca": "",
                "ano": None, "cargo": "ANALISTA DE SISTEMAS", "orgao": "", "dificuldade": "", "gabarito": None,
                "comentario": "", "alternativas": [{"letra": letter, "texto": f"{name} option"}
                    for letter, name in zip("ABCDE", ("Alpha", "Bravo", "Charlie", "Delta", "Echo"))]}
    result = salvar_lote_verificado([question], caminho_caderno=str(book), caminho_gabarito=str(answer),
        nome_prova="Prova Teste", perfil_caderno="questoes_nomeadas_v2", codigo_gabarito="A123",
        cargo_gabarito="ANALISTA DE SISTEMAS", prova={"nome": "Prova Teste", "lote_indices": [0],
        "composicao": [{"dados": question, "lote_index": 0}]})
    assert result["certificadas"] == expected, result


def test_apply_repair_revalida_allowlist_revogada(tmp_path, monkeypatch):
    from src.db.database import db, init_db
    from src.models import questoes_repo as repo
    from src.models.reparacao_service import apply_repair
    from src.models import reparacao_service

    init_db(str(tmp_path / "repair.sqlite"))
    root, vid, cid, aid, manifest, book_hash, answer_hash = _preliminary_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(reparacao_service, "ROOT_DIR", root)
    monkeypatch.setattr(reparacao_service, "IMAGE_DIR", tmp_path / "images")
    book = root / "samples" / "book.pdf"
    answer = root / "samples" / "answer.pdf"
    current = repo.obter_questao(1)
    fields = ("numero_oficial", "enunciado", "texto_apoio", "tipo", "alternativas", "gabarito")
    before = {field: current.get(field) for field in fields}
    asset = Path(manifest["apresentacao"]["questao"][0]["path"])
    geometry = {
        "source_sha256": book_hash,
        "regions": [{"page": 1, "bbox": [0, 0, 600, 240]}],
        "context_regions": [], "assets": [{"path": str(asset), "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(), "region_index": 0}],
        "context_assets": [],
    }
    catalog_hash = hashlib.sha256((root / "config" / "gabaritos.json").read_bytes()).hexdigest()
    proposal = {
        "catalogo_sha256": catalog_hash,
        "regra": AUTOMATIC_RULE_VERSION,
        "propostas": [{
            "questao_id": 1, "prova_id": 1, "anterior": before, "proposta": before,
            "fonte": str(book), "fonte_sha256": book_hash,
            "gabarito_fonte": str(answer), "gabarito_sha256": answer_hash,
            "catalogo_chave": "book.pdf",
            "escopo": manifest["escopo"] | {"situacao_gabarito": "preliminar"},
            "geometria": geometry,
            "evidencia_gabarito": {"region": {"page": 1, "bbox": [0, 0, 600, 240]}},
            "liberacao_pendencias": [],
        }],
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    policy_path = root / "config" / "gabaritos_estudo.json"
    revoked = json.loads(policy_path.read_text())
    revoked["fontes"][0]["aceitar_preliminar_para_estudo"] = False
    policy_path.write_text(json.dumps(revoked), encoding="utf-8")
    result = apply_repair(proposal_path, db_path=db.database)
    assert result["liberadas_automaticamente"] == 0
    assert any("gabarito_preliminar" in item["motivos"] for item in result["pendencias"])
    assert not get_automatic_validation(vid)["valida"]
