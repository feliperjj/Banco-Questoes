"""Reparação documental em lote, com propostas, backup e versões preservadas."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
from uuid import uuid4

from src.config import DB_PATH, IMAGE_DIR, REPORTS_DIR, ROOT_DIR
from src.importador.catalogo import carregar_catalogo, normalizar_chave
from src.importador.extrator import extrair_texto, extrair_gabaritos_pdf
from src.importador.gabarito_fonte import extract_answer_evidence
from src.importador.parser import parsear_questoes
from src.importador.pdf_fonte import extract_pdf_source
from src.importador.validacao import normalizar_gabarito, problemas_estrutura
from src.importador.pdf_render import rendering_batch


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _normal(text):
    import unicodedata
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text or "")
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", text).casefold())).strip()


def _content_digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _legacy_match(source, old_questions):
    """Identidade por conteúdo único; posição e ID não escolhem correspondência."""
    body = _normal(source["enunciado"])
    raw_body = _normal(source.get("enunciado_original") or source["enunciado"])
    found = []
    for old in old_questions:
        text = _normal(old["enunciado"])
        words = text.split()
        anchors = [" ".join(words[:min(14, len(words))])]
        if len(words) > 18:
            anchors.append(" ".join(words[-12:]))
        matches = sum(len(anchor) >= 20 and (anchor in body or anchor in raw_body) for anchor in anchors)
        if matches:
            option_anchors = [_normal(option["texto"]) for option in old.get("alternativas", [])]
            option_matches = sum(len(anchor) >= 12 and (anchor in body or anchor in raw_body) for anchor in option_anchors)
            found.append((matches + option_matches * 3, old))
    if not found:
        return None, "identidade_sem_ancora"
    maximum = max(score for score, _ in found)
    best = [old for score, old in found if score == maximum]
    if len(best) != 1:
        return None, "identidade_ambigua"
    return best[0], None


def _structured(question):
    raw = question["enunciado"].strip()
    marker = (question.get("regions") or [{}])[0].get("marker_text")
    if marker:
        offset = raw.splitlines()[0].find(marker)
        if 0 < offset < 16:
            raw = raw[offset:]
    raw = re.sub(r"(?i)^\s*(?:QUEST(?:ÃO|AO)|ITEM|Q\.)?\s*0*" + str(question["numero"]) + r"(?:[.)\-:]|\s|$)\s*", "", raw, count=1)
    raw_lines = raw.splitlines()
    for index, line in enumerate(raw_lines):
        if line.strip().upper() == "RASCUNHO" and all(
            len(item.strip()) <= 1 or item.strip().startswith(("www.", "pcimarkpci"))
            for item in raw_lines[index + 1:]
        ):
            raw_lines = raw_lines[:index]
            break
    lines = [line for line in raw_lines if re.sub(r"\s+", "", line).upper() != "RASCUNHO"
             and not re.search(r"(?i)^\s*(?:www\.|pcimarkpci|PROVA\s+\d+\s*[-–]|TERRA\s+PROVA|TRANSPETRO\s*$)", line)]
    raw = "\n".join(lines)
    parts = re.split(r"(?m)^\s*\(?([A-E])\)\s*|^\s*([A-E])[.)]\s+", raw)
    # Two capture alternatives produce None groups. Use marker spans instead.
    markers = list(re.finditer(r"(?mi)^\s*\(?([A-E])\)\s*|^\s*([A-E])[.)]\s+", raw))
    if question.get("tipo") == "julgamento":
        markers = []
    statement = raw[:markers[0].start()] if markers else raw
    alternatives = []
    for index, marker in enumerate(markers):
        stop = markers[index + 1].start() if index + 1 < len(markers) else len(raw)
        alternatives.append({"letra": (marker.group(1) or marker.group(2)).upper(), "texto": raw[marker.end():stop].strip()})
    join = lambda value: re.sub(r"\s+", " ", re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value or "")).strip()
    return {"numero_oficial": question["numero"], "enunciado": join(statement),
            "tipo": "multipla_escolha" if alternatives else "certo_errado",
            "alternativas": [{"letra": option["letra"], "texto": join(option["texto"])} for option in alternatives],
            "texto_apoio": question.get("texto_apoio") or None}


def _read_catalogue(db_path):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        proofs = [dict(row) for row in conn.execute("SELECT * FROM provas_cadastradas WHERE ativa=1 ORDER BY id")]
        for proof in proofs:
            proof["questoes"] = []
            for row in conn.execute("SELECT q.*,l.ordem FROM questoes q JOIN prova_cadastrada_questoes l ON l.questao_id=q.id WHERE l.prova_cadastrada_id=? ORDER BY l.ordem", (proof["id"],)):
                item = dict(row)
                item["alternativas"] = [dict(alt) for alt in conn.execute("SELECT letra,texto FROM alternativas WHERE questao_id=? ORDER BY letra", (item["id"],))]
                proof["questoes"].append(item)
        return proofs


@rendering_batch
def prepare_repair(*, db_path=DB_PATH, output_dir=None, proof_ids=None):
    directory = Path(output_dir or REPORTS_DIR / ("reparacao-" + datetime.now().strftime("%Y%m%d-%H%M%S")))
    directory.mkdir(parents=True, exist_ok=True)
    catalogue_path = ROOT_DIR / "config/gabaritos.json"
    catalogue = carregar_catalogo(catalogue_path)
    report = {"regra": "pdf-geometrico-v1", "criado_em": datetime.now().isoformat(), "db_path": str(Path(db_path).resolve()),
              "catalogo_sha256": _sha(catalogue_path), "provas": [], "propostas": [], "pendencias": []}
    for proof in _read_catalogue(db_path):
        if proof_ids and proof["id"] not in proof_ids:
            continue
        source = Path(proof["arquivo_questoes"] or "")
        if not source.is_absolute():
            source = ROOT_DIR / source
        if not source.is_file():
            report["pendencias"].append({"prova_id": proof["id"], "motivo": "caderno_ausente"})
            continue
        key = normalizar_chave(source.relative_to(ROOT_DIR / "samples"))
        binding = catalogue.get(key)
        print(f"Extraindo fonte da prova {proof['id']}: {source.name}", flush=True)
        candidates = parsear_questoes(extrair_texto(str(source)), str(source))
        geometry = extract_pdf_source(source, expected_questions=candidates, asset_dir=directory / "assets" / _sha(source)[:16])
        source_metadata = {}
        if "transpetro" in source.name.casefold():
            import pdfplumber
            with pdfplumber.open(source) as document:
                cover = document.pages[0].extract_text() or ""
            if "CESGRANRIO" in cover.upper():
                source_metadata["banca"] = "CESGRANRIO"
        answers, answer_evidence, answer_path = {}, {"answers": {}, "issues": []}, None
        if binding:
            answer_path = ROOT_DIR / "samples" / binding["gabarito"]
            if answer_path.is_file():
                code = binding.get("codigo") or binding.get("prova")
                answers = extrair_gabaritos_pdf(str(answer_path), code, binding.get("cargo"), usar_ocr=False,
                                              numeros_esperados={q["numero"] for q in geometry["questions"]})
                # Valores legados apenas ampliam os números que serão buscados;
                # a resposta e a região continuam exigindo leitura física do
                # quadro de cargo/tipo selecionado, com divergência bloqueada.
                for candidate in geometry["questions"]:
                    previous, identity_error = _legacy_match(candidate, proof["questoes"])
                    if previous and not identity_error and previous.get("gabarito"):
                        answers.setdefault(candidate["numero"], previous["gabarito"])
                answer_evidence = extract_answer_evidence(answer_path, codigo_prova=code, cargo=binding.get("cargo"), expected_answers=answers)
                # O verificador geométrico lê o quadro selecionado diretamente;
                # uma divergência do parser antigo não pode escolher outro cargo.
                answers = {**answers, **{n: item["resposta"] for n, item in answer_evidence["answers"].items()}}
        before_count = len(report["propostas"])
        used_ids = set()
        for source_question in geometry["questions"]:
            number = source_question["numero"]
            issues = list(source_question.get("issues") or [])
            if f"marcador_duplicado:{number}" in geometry["issues"]:
                issues.append("marcador_fisico_duplicado")
            old, error = _legacy_match(source_question, proof["questoes"])
            if error or (old and old["id"] in used_ids):
                issues.append(error or "identidade_usada_duas_vezes")
            if old:
                used_ids.add(old["id"])
            proposed = _structured(source_question)
            proposed.update(source_metadata)
            if not proposed["enunciado"] or not source_question.get("assets"):
                issues.append("conteudo_ou_facsimile_incompleto")
            letters = [option["letra"] for option in proposed["alternativas"]]
            if proposed["tipo"] == "multipla_escolha" and (letters not in [list("ABCD"), list("ABCDE")]):
                issues.append("alternativas_incompletas")
            if old and proposed["tipo"] == "multipla_escolha" and letters != [a["letra"] for a in old["alternativas"]]:
                issues.append("quantidade_alternativas_diverge_legado")
            if old and len(_normal(old.get("texto_apoio"))) >= 12 and not proposed["texto_apoio"]:
                issues.append("contexto_legado_nao_recuperado")
            if old and old["tipo"] == "multipla_escolha" and not letters:
                issues.append("alternativas_nao_recuperadas")
            answer = normalizar_gabarito(answers.get(number), proposed["tipo"]) if number in answers else None
            supplied = normalizar_gabarito(old.get("gabarito"), proposed["tipo"]) if old else None
            answer_conflict = bool(answer and supplied and answer != supplied)
            proposed["gabarito"] = supplied if answer_conflict else answer or supplied
            if issues:
                report["pendencias"].append({"prova_id": proof["id"], "numero": number, "questao_id": old["id"] if old else None, "motivo": sorted(set(issues))})
                continue
            snapshot = {name: old.get(name) for name in proposed if name != "numero_oficial"}
            snapshot["numero_oficial"] = old.get("numero_oficial")
            snapshot["imagem_path"] = old.get("imagem_path")
            release_issues = []
            if answer_conflict:
                release_issues.append("conflito_com_gabarito_anterior")
            evidence = answer_evidence["answers"].get(number)
            if not answer or not evidence:
                release_issues.append("gabarito_sem_evidencia_geometrica")
            status = "documento_fornecido"
            if answer_path and "preliminar" in (answer_path.name + " " + str(binding)).casefold():
                status = "preliminar"
                release_issues.append("gabarito_preliminar")
            if proposed["gabarito"] == "Anulada" or (binding and number in binding.get("anuladas", [])):
                proposed["gabarito"] = "Anulada"
                release_issues.append("questao_anulada")
            scope = {"prova": binding.get("prova") or "pdf:" + geometry["source_sha256"],
                     "cargo": binding.get("cargo") or "caderno-unico",
                     "codigo": binding.get("codigo") or binding.get("prova") or "caderno-unico",
                     "versao": "sha256:" + geometry["source_sha256"], "situacao_gabarito": status} if binding else {}
            report["propostas"].append({"questao_id": old["id"], "prova_id": proof["id"], "numero": number,
                "anterior": snapshot, "proposta": proposed, "fonte": str(source.resolve()), "fonte_sha256": geometry["source_sha256"],
                "gabarito_fonte": str(answer_path.resolve()) if answer_path else None,
                "gabarito_sha256": _sha(answer_path) if answer_path and answer_path.is_file() else None,
                "catalogo_chave": key, "escopo": scope, "geometria": source_question,
                "evidencia_gabarito": evidence, "liberacao_pendencias": release_issues})
        missing = [q["id"] for q in proof["questoes"] if q["id"] not in used_ids]
        report["pendencias"].extend({"prova_id": proof["id"], "questao_id": qid, "motivo": "marcador_ou_ancora_nao_confirmado"} for qid in missing)
        report["provas"].append({"id": proof["id"], "nome": proof["nome"], "questoes": len(proof["questoes"]),
            "marcadores": len(geometry["questions"]), "reparaveis": len(report["propostas"]) - before_count,
            "gabaritos_com_regiao": len(answer_evidence["answers"]), "issues_fonte": geometry["issues"], "issues_gabarito": answer_evidence["issues"]})
        path = directory / "proposta.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["resumo"] = {"questoes_inventariadas": sum(p["questoes"] for p in report["provas"]), "reparaveis": len(report["propostas"]),
                        "candidatas_liberacao": sum(not p["liberacao_pendencias"] for p in report["propostas"]), "pendencias": len(report["pendencias"])}
    path = directory / "proposta.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, report["resumo"]


def _verified_backup(db_path, target):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(target)) as backup:
            source.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or backup.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Backup inválido; reparação interrompida.")
            restore = Path(target).with_suffix(".restore-check.db")
            try:
                with closing(sqlite3.connect(restore)) as restored:
                    backup.backup(restored)
                    if list(backup.iterdump()) != list(restored.iterdump()) or restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise RuntimeError("Cópia de restauração diverge do backup.")
            finally:
                restore.unlink(missing_ok=True)


@rendering_batch
def apply_repair(proposal_path, *, db_path=DB_PATH):
    from src.db.database import db, init_db, initialized_database_batch
    from src.db.models import QuestaoVersao, ProvaCadastradaQuestao, ExecucaoExtracao, RevisaoConteudo, RevisaoGabarito
    from src.models import questoes_repo as repo
    from src.models.provenance_service import (AUTOMATIC_RULE_VERSION, add_evidence, create_source, get_automatic_validation,
        record_automatic_validation, register_extraction, begin_source_verification_batch, end_source_verification_batch, source_pdf)
    report = json.loads(Path(proposal_path).read_text(encoding="utf-8"))
    if report["catalogo_sha256"] != _sha(ROOT_DIR / "config/gabaritos.json"):
        raise ValueError("O catálogo mudou desde a proposta.")
    # A migração tem seu próprio backup verificado. Este snapshot anterior
    # também preserva integralmente os dados antes de qualquer nova versão.
    backup = Path(db_path).with_name(f"questoes.pre-reparacao-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}.db")
    init_db(str(db_path))
    result = {"backup": str(backup), "reparadas": 0, "liberadas_automaticamente": 0, "ja_aplicadas": 0, "pendencias": []}
    token = begin_source_verification_batch()
    try:
        with initialized_database_batch(), db.atomic("IMMEDIATE"):
            _verified_backup(db_path, backup)
            # Lock de escrita impede alterações concorrentes enquanto os
            # snapshots propostos são conferidos e aplicados atomicamente.
            current_proof = None
            for proposal in report["propostas"]:
                if proposal["prova_id"] != current_proof:
                    current_proof = proposal["prova_id"]
                    print(f"Aplicando reparos da prova {current_proof}", flush=True)
                qid = proposal["questao_id"]
                if _sha(proposal["fonte"]) != proposal["fonte_sha256"] or (proposal["gabarito_sha256"] and _sha(proposal["gabarito_fonte"]) != proposal["gabarito_sha256"]):
                    raise ValueError(f"Fonte da questão {qid} mudou; transação revertida.")
                current = repo.obter_questao(qid)
                if current:
                    current["alternativas"] = current.get("alternativas") or []
                before = proposal["anterior"]
                proposed = proposal["proposta"]
                safety = []
                if len(_normal(before.get("texto_apoio"))) >= 12 and not proposed.get("texto_apoio"):
                    safety.append("contexto_legado_nao_recuperado")
                if proposed["tipo"] == "multipla_escolha":
                    letters = [a["letra"] for a in proposed["alternativas"]]
                    if letters not in [list("ABCD"), list("ABCDE")] or letters != [a["letra"] for a in before["alternativas"]]:
                        safety.append("alternativas_incompletas_ou_divergentes")
                if safety:
                    result["pendencias"].append({"questao_id": qid, "motivos": safety})
                    continue
                same = current and all(current.get(key) == value for key, value in before.items())
                latest = QuestaoVersao.select().where(QuestaoVersao.questao == qid).order_by(QuestaoVersao.numero_versao.desc()).first()
                if latest:
                    human_content = RevisaoConteudo.select().where((RevisaoConteudo.questao_versao == latest.id) &
                        (RevisaoConteudo.decisao != "pendente")).order_by(RevisaoConteudo.id.desc()).first()
                    human_answer = RevisaoGabarito.select().where((RevisaoGabarito.questao_versao == latest.id) &
                        (RevisaoGabarito.decisao != "pendente")).order_by(RevisaoGabarito.id.desc()).first()
                    rejected = ((human_content and human_content.decisao == "rejeitado") or
                                (human_answer and human_answer.decisao in {"conflitante", "anulado"}))
                    unchanged_content = all(current.get(key) == proposed.get(key) for key in
                        ("numero_oficial", "enunciado", "texto_apoio", "tipo", "alternativas", "gabarito"))
                    if rejected and unchanged_content:
                        result["pendencias"].append({"questao_id": qid, "motivos": ["rejeicao_humana_do_mesmo_conteudo"]})
                        continue
                    if proposal["liberacao_pendencias"] and set(proposal["liberacao_pendencias"]) <= {"gabarito_sem_evidencia_geometrica"} and get_automatic_validation(latest.id)["valida"]:
                        # Uma dificuldade nova do extrator não revoga evidência
                        # íntegra já existente para a mesma versão e fonte.
                        result["ja_aplicadas"] += 1
                        continue
                extraction = (ExecucaoExtracao.get_or_none(ExecucaoExtracao.id == latest.execucao_extracao_id)
                              if latest and latest.execucao_extracao_id else None)
                applied = bool(current and extraction and extraction.extrator == "reparacao_documental"
                               and all(current.get(key) == value for key, value in proposal["proposta"].items()))
                parameters = json.loads(extraction.parametros_json) if applied else {}
                applied = applied and parameters.get("fonte_sha256") == proposal["fonte_sha256"]
                if applied:
                    media = parameters.get("facsimile", {})
                    assets = [a for group in media.values() for a in group]
                    applied = bool(assets) and all(Path(a["path"]).is_file() and _sha(a["path"]) == a["sha256"] for a in assets)
                    applied = applied and current.get("imagem_path") == media["questao"][0]["path"]
                if applied:
                    if proposal["liberacao_pendencias"] or get_automatic_validation(latest.id)["valida"]:
                        result["ja_aplicadas"] += 1
                        continue
                    # O conteúdo já coincide integralmente com este reparo,
                    # mas uma nova evidência pode agora permitir certificá-lo.
                    same = True
                if not same:
                    # Uma proposta posterior pode aperfeiçoar um reparo deste
                    # mesmo lote. Só aceite se a versão atual ainda for o
                    # resultado íntegro da reparação; edições manuais continuam
                    # protegidas pela comparação do snapshot.
                    prior_parameters = json.loads(extraction.parametros_json) if extraction else {}
                    prior_fields = prior_parameters.get("campos_reparados") or {}
                    intact_repair = bool(prior_fields and all(current.get(k) == v for k, v in prior_fields.items())
                                         and prior_parameters.get("fonte_sha256") == proposal["fonte_sha256"])
                    if not intact_repair:
                        raise ValueError(f"Questão {qid} mudou após a proposta; transação revertida.")
                source_id = create_source(proposal["fonte"], tipo="pdf")
                geometry = proposal["geometria"]
                media = {"questao": [], "contexto": []}
                for kind, assets in (("questao", geometry["assets"]), ("contexto", geometry["context_assets"])):
                    for asset in sorted(assets, key=lambda item: item["region_index"]):
                        folder = IMAGE_DIR / "reparacao-v1" / proposal["fonte_sha256"][:16]
                        folder.mkdir(parents=True, exist_ok=True)
                        target = folder / Path(asset["path"]).name
                        if target.exists() and _sha(target) != asset["sha256"]:
                            raise ValueError("Recurso existente diverge; não foi sobrescrito.")
                        if not target.exists():
                            shutil.copy2(asset["path"], target)
                        media[kind].append({**asset, "path": str(target.resolve())})
                data = dict(proposal["proposta"], imagem_path=media["questao"][0]["path"])
                extraction = register_extraction(source_id, extractor="reparacao_documental", extractor_version=AUTOMATIC_RULE_VERSION,
                    profile=report["regra"], parameters={"facsimile": media, "fonte_sha256": proposal["fonte_sha256"],
                                                       "campos_reparados": data,
                                                       "contexto_caderno_completo": bool(proposal.get("contexto_caderno_completo")),
                                                       **proposal.get("parametros_reconstrucao", {})})
                repo.atualizar_questao(qid, data, source_id=source_id, extraction_id=extraction)
                version = QuestaoVersao.select().where(QuestaoVersao.questao == qid).order_by(QuestaoVersao.numero_versao.desc()).first()
                # Atualiza só a composição do catálogo; tentativas e provas
                # já criadas mantêm integralmente as versões anteriores.
                ProvaCadastradaQuestao.update(questao_versao=version.id).where(
                    (ProvaCadastradaQuestao.prova_cadastrada == proposal["prova_id"]) &
                    (ProvaCadastradaQuestao.questao == qid)).execute()
                result["reparadas"] += 1
                if proposal["liberacao_pendencias"]:
                    result["pendencias"].append({"questao_id": qid, "motivos": proposal["liberacao_pendencias"]})
                    continue
                ids = []
                for kind, regions in (("questao", geometry["regions"]), ("contexto", geometry["context_regions"])):
                    for index, region in enumerate(regions):
                        # Page dimensions are taken from the PDF, never the
                        # width/height of the crop returned by the extractor.
                        import pdfplumber
                        with source_pdf(proposal["fonte"]) as pdf:
                            page = pdf.pages[region["page"] - 1]
                            size, rotation = (page.width, page.height), page.rotation or 0
                        eid = add_evidence(version.id, source_id, part="conteudo" if kind == "questao" else "contexto",
                            page=region["page"], bounds=region["bbox"], coordinate_system="pdf-point; origem superior esquerda",
                            page_size=size, rotation=rotation, scope=proposal["escopo"])
                        ids.append(eid)
                        for asset in media[kind]:
                            if asset["region_index"] == index:
                                asset["evidencia_id"] = eid
                answer_source = create_source(proposal["gabarito_fonte"], tipo="pdf")
                region = proposal["evidencia_gabarito"]["region"]
                import pdfplumber
                with source_pdf(proposal["gabarito_fonte"]) as pdf:
                    page = pdf.pages[region["page"] - 1]
                    size, rotation = (page.width, page.height), page.rotation or 0
                ids.append(add_evidence(version.id, answer_source, part="gabarito", page=region["page"], bounds=region["bbox"],
                    coordinate_system="pdf-point; origem superior esquerda", page_size=size, rotation=rotation, scope=proposal["escopo"]))
                manifest = {"regra": AUTOMATIC_RULE_VERSION, "numero_oficial": data["numero_oficial"], "gabarito": data["gabarito"],
                    "escopo": proposal["escopo"], "identidade": {"catalogo_chave": proposal["catalogo_chave"],
                    "catalogo_sha256": report["catalogo_sha256"], "conteudo_termos": [data["enunciado"]], "gabarito_termos": [str(data["numero_oficial"])]},
                    "checks": {key: True for key in ("identidade", "numero", "conteudo_completo", "alternativas", "contexto", "recursos", "gabarito")},
                    "apresentacao": {"modo": "facsimile", **media,
                                     "contexto_caderno_completo": bool(proposal.get("contexto_caderno_completo"))},
                    "verificador": {"metodo": "marcador_geometrico_ancora_textual_catalogo_e_pixels", "versao": AUTOMATIC_RULE_VERSION}}
                try:
                    record_automatic_validation(version.id, evidence_ids=ids, manifest=manifest)
                    if get_automatic_validation(version.id)["valida"]:
                        result["liberadas_automaticamente"] += 1
                except ValueError as error:
                    result["pendencias"].append({"questao_id": qid, "motivos": [str(error)]})
        if db.execute_sql("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute_sql("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Auditoria final de integridade falhou.")
    finally:
        end_source_verification_batch(token)
    Path(proposal_path).with_name("resultado_aplicacao.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
