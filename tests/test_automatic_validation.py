import hashlib
import json
import copy
import pytest
from pathlib import Path

from src.db.models import EvidenciaQuestao, QuestaoVersao, RevisaoConteudo, RevisaoGabarito, ValidacaoAutomatica
from src.models import questoes_repo as repo
from src.models.provenance_service import (
    AUTOMATIC_RULE_VERSION, add_evidence, assess_version, create_question_version,
    create_source, get_automatic_validation, record_automatic_validation,
)


def _pdf_and_crop(folder):
    from src.importador.pdf_render import render_region
    source = folder / "fonte.pdf"
    text = (f"BT /F1 10 Tf 10 215 Td (Prova Teste Cargo Analista Codigo 1 Versao 1) Tj "
            "0 -30 Td (Questao 9 Completa.) Tj 0 -30 Td (A Alpha B Bravo C Charlie D Delta E Echo) Tj "
            "0 -30 Td (Gabarito 9-A) Tj ET").encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 240] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
               b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data)); data.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(data); data.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    source.write_bytes(data)
    asset = folder / "questao.png"
    render_region(source, 1, (0, 0, 600, 240), output=asset)
    return source, asset


def test_certificado_automatico_e_idempotente_sem_revisao_humana(tmp_path):
    source, asset = _pdf_and_crop(tmp_path)
    question_id = repo.criar_questao({
        "numero_oficial": 9, "enunciado": "Completa.", "tipo": "multipla_escolha",
        "gabarito": "A", "alternativas": [{"letra": l, "texto": name} for l, name in zip("ABCDE", ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])],
    })
    source_id = create_source(source, tipo="pdf")
    version_id = create_question_version(question_id, source_id=source_id)
    scope = {"prova": "Prova Teste", "cargo": "Cargo Analista", "codigo": "1", "versao": "1"}
    content = add_evidence(version_id, source_id, part="conteudo", page=1, bounds=(0, 0, 600, 240),
                           coordinate_system="pdf-point; origem superior esquerda", page_size=(600, 240), rotation=0, scope=scope, excerpt="texto")
    answer = add_evidence(version_id, source_id, part="gabarito", page=1, bounds=(0, 0, 600, 240),
                          coordinate_system="pdf-point; origem superior esquerda", page_size=(600, 240), rotation=0, scope={**scope, "situacao_gabarito": "documento_fornecido"}, excerpt="A")
    RevisaoConteudo.delete().execute()
    RevisaoGabarito.delete().execute()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {"regra": AUTOMATIC_RULE_VERSION, "numero_oficial": 9, "gabarito": "A", "escopo": {**scope, "situacao_gabarito": "documento_fornecido"},
                "identidade": {"conteudo_termos": ["Prova Teste", "Cargo Analista", "Completa", "Alpha", "Bravo", "Charlie", "Delta", "Echo"], "gabarito_termos": ["Gabarito", "9-A"]},
                "checks": {k: True for k in ("identidade", "numero", "conteudo_completo", "alternativas", "contexto", "recursos", "gabarito")},
                "apresentacao": {"modo": "facsimile", "questao": [{"path": str(asset), "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(), "evidencia_id": content, "scale": 2.0}]},
                "verificador": {"metodo": "teste_sintetico", "versao": AUTOMATIC_RULE_VERSION}}
    first = record_automatic_validation(version_id, evidence_ids=[content, answer], manifest=manifest)
    assert record_automatic_validation(version_id, evidence_ids=[content, answer], manifest=manifest) == first
    assert ValidacaoAutomatica.select().where(ValidacaoAutomatica.questao_versao == version_id).count() == 1
    assert get_automatic_validation(version_id)["valida"]
    result = assess_version(version_id)
    assert result["liberada"] and result["tipo_liberacao"] == "automatica"
    assert result["estado_validacao_automatica"] == "verificado_automaticamente"


def _automatic_fixture(tmp_path):
    source, asset = _pdf_and_crop(tmp_path)
    qid = repo.criar_questao({"numero_oficial": 9, "enunciado": "Completa.", "tipo": "multipla_escolha", "gabarito": "A",
                              "alternativas": [{"letra": l, "texto": l} for l in "ABCDE"]})
    sid = create_source(source, tipo="pdf")
    vid = create_question_version(qid, source_id=sid)
    scope = {"prova": "Prova Teste", "cargo": "Cargo Analista", "codigo": "1", "versao": "1"}
    cid = add_evidence(vid, sid, part="conteudo", page=1, bounds=(0, 0, 600, 240), coordinate_system="pdf-point; origem superior esquerda", page_size=(600, 240), rotation=0, scope=scope)
    aid = add_evidence(vid, sid, part="gabarito", page=1, bounds=(0, 0, 600, 240), coordinate_system="pdf-point; origem superior esquerda", page_size=(600, 240), rotation=0, scope={**scope, "situacao_gabarito": "definitivo"})
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {"regra": AUTOMATIC_RULE_VERSION, "numero_oficial": 9, "gabarito": "A", "escopo": scope,
                "identidade": {"conteudo_termos": ["Prova Teste", "Cargo Analista", "Completa", "Alpha", "Bravo", "Charlie", "Delta", "Echo"], "gabarito_termos": ["Gabarito", "9-A"]},
                "checks": {k: True for k in ("identidade", "numero", "conteudo_completo", "alternativas", "contexto", "recursos", "gabarito")},
                "apresentacao": {"modo": "facsimile", "questao": [{"path": str(asset), "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(), "evidencia_id": cid, "scale": 2.0}]},
                "verificador": {"metodo": "fixture", "versao": AUTOMATIC_RULE_VERSION}}
    record_automatic_validation(vid, evidence_ids=[cid, aid], manifest=manifest)
    return source, vid, cid, aid, manifest


def test_certificado_invalida_fonte_crop_escopo_e_regra_antiga(tmp_path):
    source, vid, cid, aid, manifest = _automatic_fixture(tmp_path)
    assert get_automatic_validation(vid)["valida"]
    source_file = Path(EvidenciaQuestao.get_by_id(cid).documento_fonte.localizacao)
    original = source_file.read_bytes()
    source_file.write_bytes(b"source-alterada")
    assert not get_automatic_validation(vid)["valida"]
    source_file.write_bytes(original)
    evidence = EvidenciaQuestao.get_by_id(cid)
    evidence.x0 = 0.25
    evidence.save(only=[EvidenciaQuestao.x0])
    assert not get_automatic_validation(vid)["valida"]
    evidence.x0 = 0.0
    evidence.save(only=[EvidenciaQuestao.x0])
    old = dict(manifest, regra="pdf-geometrico-v0")
    from pytest import raises
    with raises(ValueError, match="regra_incompativel"):
        record_automatic_validation(vid, evidence_ids=[cid, aid], manifest=old)


def test_snapshot_novo_e_rejeicao_humana_nao_sao_contornados(tmp_path):
    source, vid, cid, aid, manifest = _automatic_fixture(tmp_path)
    question_id = QuestaoVersao.get_by_id(vid).questao_id
    repo.atualizar_questao(question_id, {"enunciado": "Alterada"})
    assert not get_automatic_validation(vid)["valida"]

    source, vid, cid, aid, manifest = _automatic_fixture(tmp_path)
    RevisaoConteudo.create(questao_versao=vid, decisao="rejeitado", justificativa="rejeição explícita", evidencia_json=json.dumps([cid]))
    result = assess_version(vid)
    assert not result["liberada"]
    assert not RevisaoConteudo.select().where(RevisaoConteudo.questao_versao == vid).count() == 0


@pytest.mark.parametrize("change", [
    {"identidade": {"conteudo_termos": ["Outra questão"], "gabarito_termos": ["Gabarito", "9-A"]}},
    {"identidade": {"conteudo_termos": ["Prova Teste", "Cargo Analista", "Completa", "Alpha", "Bravo", "Wrong", "Delta", "Echo"], "gabarito_termos": ["Gabarito", "9-A"]}},
    {"numero_oficial": 8}, {"gabarito": "B"},
    {"escopo": {"prova": "Falsa", "cargo": "Cargo Analista", "codigo": "1", "versao": "1"}},
])
def test_manifesto_nao_pode_provar_conteudo_numero_gabarito_ou_scope_falso(tmp_path, change):
    source, vid, cid, aid, manifest = _automatic_fixture(tmp_path)
    invalid = copy.deepcopy(manifest)
    invalid.update(change)
    with pytest.raises(ValueError):
        record_automatic_validation(vid, evidence_ids=[cid, aid], manifest=invalid)


def test_recurso_png_ou_crop_alterado_invalida_certificado(tmp_path):
    source, vid, cid, aid, manifest = _automatic_fixture(tmp_path)
    item = manifest["apresentacao"]["questao"][0]
    Path(item["path"]).write_bytes(b"not-an-image")
    assert not get_automatic_validation(vid)["valida"]


def test_reaplicar_lote_nao_recria_versao_para_contornar_rejeicao(tmp_path):
    from src.config import ROOT_DIR
    from src.db.database import db
    from src.models.reparacao_service import apply_repair
    source, vid, cid, aid, manifest = _automatic_fixture(tmp_path)
    qid = QuestaoVersao.get_by_id(vid).questao_id
    current = repo.obter_questao(qid)
    fields = ("numero_oficial", "enunciado", "texto_apoio", "tipo", "alternativas", "gabarito")
    proposed = {key: current.get(key) for key in fields}
    RevisaoConteudo.create(questao_versao=vid, decisao="rejeitado", justificativa="Rejeição de teste",
                          evidencia_json=json.dumps([cid]))
    proposal = {"catalogo_sha256": hashlib.sha256((ROOT_DIR / "config/gabaritos.json").read_bytes()).hexdigest(),
                "propostas": [{"questao_id": qid, "prova_id": 1, "fonte": str(source),
                    "fonte_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "gabarito_sha256": None,
                    "anterior": proposed, "proposta": proposed, "liberacao_pendencias": []}]}
    path = tmp_path / "lote.json"
    path.write_text(json.dumps(proposal), encoding="utf-8")
    version_count = QuestaoVersao.select().where(QuestaoVersao.questao == qid).count()
    result = apply_repair(path, db_path=db.database)
    assert result["reparadas"] == result["liberadas_automaticamente"] == 0
    assert result["pendencias"] == [{"questao_id": qid, "motivos": ["rejeicao_humana_do_mesmo_conteudo"]}]
    assert QuestaoVersao.select().where(QuestaoVersao.questao == qid).count() == version_count
    assert not get_automatic_validation(vid)["valida"]
