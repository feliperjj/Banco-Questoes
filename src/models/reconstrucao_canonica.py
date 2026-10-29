"""Reconstrói identidades pela fonte preservando registros e histórico antigos."""
from __future__ import annotations
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import shutil
from uuid import uuid4
from src.config import DB_PATH, ROOT_DIR, REPORTS_DIR, IMAGE_DIR
from src.importador.catalogo import carregar_catalogo, normalizar_chave
from src.importador.extrator import extrair_texto
from src.importador.parser import parsear_questoes
from src.importador.gabarito_fonte import extract_answer_evidence
from src.importador.pdf_fonte import extract_pdf_source, readable_source_page
from src.importador.pdf_render import rendering_batch, render_region
from src.importador.validacao import normalizar_gabarito
from src.models.reparacao_service import _legacy_match, _read_catalogue, _sha, _structured, _verified_backup, apply_repair


def _proof_numbers(geometry, expected_count):
    numbers = [q.get("numero") for q in geometry.get("questions", [])]
    if len(numbers) != expected_count or len(set(numbers)) != expected_count:
        return None, "conjunto_fisico_incompleto_ou_duplicado"
    if set(numbers) != set(range(1, expected_count + 1)):
        return None, "numeracao_fisica_nao_e_1_a_N"
    if any(f"marcador_duplicado:{n}" in geometry.get("issues", []) for n in numbers):
        return None, "marcador_fisico_duplicado"
    return numbers, None


def _full_context(source, directory, digest):
    import pdfplumber
    regions, assets, texts = [], [], []
    with pdfplumber.open(source) as document:
        for number, original in enumerate(document.pages, 1):
            bbox = [0.0, 0.0, float(original.width), float(original.height)]
            target = directory / "assets" / digest[:16] / f"caderno-p{number:03}.png"
            rendered = render_region(source, number, bbox, output=target)
            regions.append({"page": number, "bbox": bbox})
            assets.append({"path": rendered["path"], "sha256": rendered["sha256"], "scale": 2.0, "region_index": number - 1})
            texts.append(readable_source_page(original).extract_text(x_tolerance=2, y_tolerance=3) or "")
    return regions, assets, "\n".join(texts)


def _links(connection, proof_id):
    return [list(row) for row in connection.execute("SELECT questao_id,ordem,questao_versao_id FROM prova_cadastrada_questoes WHERE prova_cadastrada_id=? ORDER BY ordem,questao_id", (proof_id,))]


@rendering_batch
def prepare_canonical(*, db_path=DB_PATH, proof_ids=None, output=None):
    import sqlite3
    from contextlib import closing
    directory = Path(output or REPORTS_DIR / ("reconstrucao-canonica-" + datetime.now().strftime("%Y%m%d-%H%M%S")))
    directory.mkdir(parents=True, exist_ok=True)
    catalogue_path = ROOT_DIR / "config/gabaritos.json"
    catalogue = carregar_catalogo(catalogue_path)
    report = {"regra": "reconstrucao-canonica-fisica-v1", "job_uuid": str(uuid4()), "catalogo_sha256": _sha(catalogue_path), "provas": [], "propostas": [], "pendencias": []}
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        for proof in _read_catalogue(db_path):
            if proof_ids and proof["id"] not in proof_ids:
                continue
            print(f"Preparando reconstrução da prova {proof['id']}", flush=True)
            source = Path(proof.get("arquivo_questoes") or "")
            if not source.is_absolute():
                source = ROOT_DIR / source
            if not source.is_file():
                report["pendencias"].append({"prova_id": proof["id"], "motivo": "caderno_ausente"})
                continue
            digest = _sha(source)
            candidates = parsear_questoes(extrair_texto(str(source)), str(source))
            geometry = extract_pdf_source(source, expected_questions=candidates, asset_dir=directory / "assets" / digest[:16])
            scoped = dict(geometry, questions=[q for q in geometry["questions"] if 1 <= q["numero"] <= len(proof["questoes"]) or q.get("checks", {}).get("anchor_confirmed")])
            numbers, error = _proof_numbers(scoped, len(proof["questoes"]))
            report["provas"].append({"id": proof["id"], "nome": proof["nome"], "questoes": len(proof["questoes"]), "conjunto_completo": error is None, "composicao_anterior": _links(connection, proof["id"])})
            if error:
                report["pendencias"].append({"prova_id": proof["id"], "motivo": error})
                continue
            key = normalizar_chave(source.relative_to(ROOT_DIR / "samples"))
            binding = catalogue.get(key)
            answer_path = ROOT_DIR / "samples" / binding["gabarito"] if binding else None
            answer_result = {"answers": {}, "issues": []}
            if answer_path and answer_path.is_file():
                answer_result = extract_answer_evidence(answer_path, codigo_prova=binding.get("codigo") or binding.get("prova"), cargo=binding.get("cargo"), expected_answers={n: None for n in numbers})
            status = "preliminar" if binding and "preliminar" in (str(binding) + str(answer_path)).casefold() else "documento_fornecido"
            scope = {"prova": binding.get("prova") or "pdf:" + digest, "cargo": binding.get("cargo") or "caderno-unico", "codigo": binding.get("codigo") or binding.get("prova") or "caderno-unico", "versao": "sha256:" + digest, "situacao_gabarito": status} if binding else {}
            full_context, used, canonical_ids = None, set(), {}
            for old in proof["questoes"]:
                row = connection.execute("SELECT e.parametros_json FROM questoes_versoes v JOIN execucoes_extracao e ON e.id=v.execucao_extracao_id WHERE v.questao_id=? ORDER BY v.numero_versao DESC LIMIT 1", (old["id"],)).fetchone()
                params = json.loads(row[0]) if row else {}
                if params.get("canonical_prova_id") == proof["id"] and params.get("fonte_sha256") == digest:
                    canonical_ids[params.get("canonical_numero")] = old
            for item in sorted(scoped["questions"], key=lambda q: q["numero"]):
                number, proposed = item["numero"], _structured(item)
                old, _ = _legacy_match(item, proof["questoes"])
                old = canonical_ids.get(number) or old
                letters = [a["letra"] for a in proposed["alternativas"]]
                if old and (old["id"] in used or (proposed["tipo"] == "multipla_escolha" and letters != [a["letra"] for a in old["alternativas"]])):
                    old = None
                if old:
                    used.add(old["id"])
                issues = [issue for issue in item.get("issues", []) if issue != "contexto_necessario_nao_encontrado"]
                complete_context = not old or "contexto_necessario_nao_encontrado" in item.get("issues", []) or bool(old.get("texto_apoio") and not proposed["texto_apoio"])
                geometry_item = dict(item)
                if complete_context:
                    if full_context is None:
                        full_context = _full_context(source, directory, digest)
                    regions, assets, text = full_context
                    geometry_item = dict(item, context_regions=regions, context_assets=assets)
                    proposed["texto_apoio"] = text
                if not item.get("checks", {}).get("anchor_confirmed"):
                    issues.append("ancora_fisica_nao_confirmada")
                if proposed["tipo"] == "multipla_escolha" and letters not in [list("ABCD"), list("ABCDE")]:
                    issues.append("alternativas_incompletas")
                if not item.get("assets"):
                    issues.append("facsimile_ausente")
                evidence = answer_result["answers"].get(number)
                answer = normalizar_gabarito(evidence["resposta"], proposed["tipo"]) if evidence else None
                previous = normalizar_gabarito(old.get("gabarito"), proposed["tipo"]) if old else None
                conflict = bool(previous and answer and previous != answer)
                proposed["gabarito"] = previous if conflict else answer or previous
                if conflict:
                    issues.append("conflito_com_gabarito_anterior")
                if not evidence or not answer:
                    issues.append("gabarito_sem_evidencia_geometrica")
                if status == "preliminar":
                    issues.append("gabarito_preliminar")
                if proposed["gabarito"] == "Anulada" or (binding and number in binding.get("anuladas", [])):
                    proposed["gabarito"] = "Anulada"
                    issues.append("questao_anulada")
                if not old:
                    for name in ("banca", "ano", "cargo", "orgao"):
                        values = [q.get(name) for q in proof["questoes"] if q.get(name)]
                        if values:
                            proposed[name] = Counter(values).most_common(1)[0][0]
                before = {field: old.get(field) for field in proposed} if old else None
                if old:
                    before["imagem_path"] = old.get("imagem_path")
                report["propostas"].append({"prova_id": proof["id"], "questao_id": old["id"] if old else None, "numero": number, "anterior": before, "proposta": proposed, "fonte": str(source.resolve()), "fonte_sha256": digest, "gabarito_fonte": str(answer_path.resolve()) if answer_path else None, "gabarito_sha256": _sha(answer_path) if answer_path and answer_path.is_file() else None, "catalogo_chave": key, "escopo": scope, "geometria": geometry_item, "evidencia_gabarito": evidence, "contexto_caderno_completo": complete_context, "liberacao_pendencias": sorted(set(issues)), "parametros_reconstrucao": {"canonical_job_uuid": report["job_uuid"], "canonical_numero": number, "canonical_prova_id": proof["id"]}})
            # Uma nova identidade não pode apagar um veto humano cuja origem
            # antiga ficou ambígua. Preserve o veto até ele ser identificado.
            unmatched = {q["id"] for q in proof["questoes"]} - used
            rejected = False
            for qid in unmatched:
                version = connection.execute("SELECT id FROM questoes_versoes WHERE questao_id=? ORDER BY numero_versao DESC LIMIT 1", (qid,)).fetchone()
                if not version:
                    continue
                for table, decisions in (("revisoes_conteudo", {"rejeitado"}), ("revisoes_gabarito", {"conflitante", "anulado"})):
                    row = connection.execute(f"SELECT decisao FROM {table} WHERE questao_versao_id=? AND decisao!='pendente' ORDER BY id DESC LIMIT 1", (version[0],)).fetchone()
                    rejected = rejected or bool(row and row[0] in decisions)
            if rejected:
                for item in report["propostas"]:
                    if item["prova_id"] == proof["id"] and item["questao_id"] is None:
                        item["liberacao_pendencias"].append("veto_humano_na_origem_sem_identidade_recuperavel")
            path = directory / "proposta-canonica.json"
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["resumo"] = {"provas": len(report["provas"]), "propostas": len(report["propostas"]), "novas": sum(p["questao_id"] is None for p in report["propostas"]), "pendencias": len(report["pendencias"])}
    path = directory / "proposta-canonica.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, report["resumo"]


def _copy_media(proposal):
    media = {"questao": [], "contexto": []}
    folder = IMAGE_DIR / "reparacao-v1" / proposal["fonte_sha256"][:16]
    folder.mkdir(parents=True, exist_ok=True)
    for kind, key in (("questao", "assets"), ("contexto", "context_assets")):
        for asset in sorted(proposal["geometria"][key], key=lambda a: a["region_index"]):
            if _sha(asset["path"]) != asset["sha256"]:
                raise ValueError("Derivado alterado após a preparação.")
            target = folder / Path(asset["path"]).name
            if target.exists() and _sha(target) != asset["sha256"]:
                raise ValueError("Derivado existente divergente; preservado sem sobrescrita.")
            if not target.exists():
                shutil.copy2(asset["path"], target)
            media[kind].append(dict(asset, path=str(target.resolve())))
    return media


@rendering_batch
def apply_canonical(proposal_path, *, db_path=DB_PATH):
    from src.db.database import db, init_db, initialized_database_batch
    from src.db.models import ExecucaoExtracao, QuestaoVersao, Questao, ProvaCadastradaQuestao
    from src.models import questoes_repo as repo
    from src.models.provenance_service import create_source, register_extraction
    path = Path(proposal_path)
    report = json.loads(path.read_text(encoding="utf-8"))
    proofs = {p["id"]: p for p in report.get("provas", []) if p.get("conjunto_completo")}
    if not proofs:
        return {"aplicado": False, "motivo": "conjunto_fisico_incompleto", "pendencias": report.get("pendencias", [])}
    if report["catalogo_sha256"] != _sha(ROOT_DIR / "config/gabaritos.json"):
        raise ValueError("Catálogo alterado após a preparação.")
    proposals = [p for p in report["propostas"] if p["prova_id"] in proofs]
    init_db(str(db_path))
    backup = Path(db_path).with_name(f"questoes.pre-canonica-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}.db")
    staged, repaired = [], []
    completed = report.get("composicoes_aplicadas", {})
    with initialized_database_batch(), db.atomic("IMMEDIATE"):
        _verified_backup(db_path, backup)
        for proof_id, proof in proofs.items():
            if _links(db.connection(), proof_id) != completed.get(str(proof_id), proof["composicao_anterior"]):
                raise ValueError(f"A composição da prova {proof_id} mudou; preservada sem substituição.")
        for proposal in proposals:
            if _sha(proposal["fonte"]) != proposal["fonte_sha256"]:
                raise ValueError("Caderno alterado após a preparação.")
            item = dict(proposal)
            if proposal["questao_id"] is None:
                params, existing_version = proposal["parametros_reconstrucao"], None
                for extraction in ExecucaoExtracao.select().where(ExecucaoExtracao.extrator == "reconstrucao_canonica_preparada"):
                    origin = json.loads(extraction.parametros_json)
                    if all(origin.get(k) == v for k, v in params.items()):
                        existing_version = QuestaoVersao.select().where(QuestaoVersao.execucao_extracao == extraction.id).first()
                        break
                if existing_version:
                    qid = existing_version.questao_id
                else:
                    media = _copy_media(proposal)
                    data = dict(proposal["proposta"], imagem_path=media["questao"][0]["path"])
                    source = create_source(proposal["fonte"], tipo="pdf")
                    extraction = register_extraction(source, extractor="reconstrucao_canonica_preparada", profile=report["regra"], parameters={**params, "fonte_sha256": proposal["fonte_sha256"], "facsimile": media, "contexto_caderno_completo": proposal["contexto_caderno_completo"]})
                    qid = repo._criar_questao_sem_transacao(data, source_id=source, extraction_id=extraction)
                    staged.append(qid)
                item["questao_id"] = qid
                current = repo.obter_questao(qid)
                current["alternativas"] = current.get("alternativas") or []
                item["anterior"] = {field: current.get(field) for field in proposal["proposta"]}
                item["anterior"]["imagem_path"] = current.get("imagem_path")
            repaired.append(item)
    repair_path = path.with_name("reparos-identidades-alocadas.json")
    repair_path.write_text(json.dumps({"regra": report["regra"], "catalogo_sha256": report["catalogo_sha256"], "propostas": repaired}, ensure_ascii=False, indent=2), encoding="utf-8")
    application = apply_repair(repair_path, db_path=db_path)
    archived = []
    with initialized_database_batch(), db.atomic("IMMEDIATE"):
        for proof_id, proof in proofs.items():
            expected_links = completed.get(str(proof_id), proof["composicao_anterior"])
            if [row[:2] for row in _links(db.connection(), proof_id)] != [row[:2] for row in expected_links]:
                raise ValueError("Composição editada durante a reconstrução; preservada sem substituição.")
            items = sorted((p for p in repaired if p["prova_id"] == proof_id), key=lambda p: p["numero"])
            if len(items) != proof["questoes"] or len({p["questao_id"] for p in items}) != len(items):
                raise ValueError("Reconstrução incompleta ou duas questões compartilham identidade.")
            for item in items:
                current = repo.obter_questao(item["questao_id"])
                current["alternativas"] = current.get("alternativas") or []
                if any(current.get(k) != v for k, v in item["proposta"].items()):
                    raise ValueError(f"Questão {item['questao_id']} não recebeu integralmente a proposta; composição preservada.")
            old_ids, new_ids = {row[0] for row in proof["composicao_anterior"]}, {p["questao_id"] for p in items}
            ProvaCadastradaQuestao.delete().where(ProvaCadastradaQuestao.prova_cadastrada == proof_id).execute()
            for item in items:
                version = repo.ultima_versao(item["questao_id"])
                ProvaCadastradaQuestao.create(prova_cadastrada=proof_id, questao=item["questao_id"], questao_versao=version.id, ordem=item["numero"])
            for qid in old_ids - new_ids:
                if not ProvaCadastradaQuestao.select().where(ProvaCadastradaQuestao.questao == qid).exists():
                    Questao.update(ativa=False).where(Questao.id == qid).execute()
                    archived.append(qid)
            completed[str(proof_id)] = _links(db.connection(), proof_id)
    if db.execute_sql("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Falha na auditoria de integridade da reconstrução.")
    report["composicoes_aplicadas"] = completed
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {"aplicado": True, "backup": str(backup), "novas": len(staged), "arquivadas": archived, "provas_reconstruidas": sorted(proofs), "reparacao": application}
    path.with_name("resultado-canonico.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
