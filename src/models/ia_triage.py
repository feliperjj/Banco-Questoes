"""Triagem somente leitura para conferência local de alternativas.

Esta camada é deliberadamente conservadora: ``assess_version`` continua sendo
a autoridade para liberação e nenhuma sugestão produz escrita no banco.
"""
from __future__ import annotations

import json
import math
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from src.db.models import (Alternativa, DocumentoFonte, EvidenciaQuestao,
                           Questao, QuestaoVersao)
from src.models import questoes_repo as repo
from src.models.provenance_service import assess_version, verify_source
from src.importador.ia_revisao import analyze_evidence, prepare_evidence
from src.models.review_workflow import diagnostic_target


def _batch(value: Any):
    method = getattr(value, "batch", None)
    return method() if callable(method) else nullcontext(value)


def _get(model, ident, reader=None):
    if reader is not None:
        for name in ("get", "record"):
            fn = getattr(reader, name, None)
            if callable(fn):
                try:
                    value = fn(model, ident)
                except TypeError:
                    value = fn(ident)
                if value is not None:
                    return value
    return model.get_or_none(model.id == ident)


def _latest(question_id, source):
    fn = getattr(source, "ultima_versao", None)
    if callable(fn):
        return fn(question_id)
    return (QuestaoVersao.select().where(QuestaoVersao.questao == question_id)
            .order_by(QuestaoVersao.numero_versao.desc()).first())


def _question(question_id, source):
    fn = getattr(source, "obter_questao", None)
    if callable(fn):
        return fn(question_id)
    q = Questao.get_or_none(Questao.id == question_id)
    if q is None:
        return None
    return {"id": q.id, "ativa": q.ativa, "alternativas": [
        {"letra": a.letra, "texto": a.texto}
        for a in Alternativa.select().where(Alternativa.questao == q.id).order_by(Alternativa.letra)
    ]}


def _content(version):
    try:
        return json.loads(version.conteudo_json or "{}")
    except (TypeError, ValueError):
        return {}


def _geometry(evidence):
    values = (evidence.x0, evidence.y0, evidence.x1, evidence.y1)
    if evidence.pagina is None or any(v is None for v in values):
        return False
    try:
        x0, y0, x1, y1 = map(float, values)
        return (all(math.isfinite(v) for v in (x0, y0, x1, y1))
                and x0 >= 0 and y0 >= 0 and x1 > x0 and y1 > y0)
    except (TypeError, ValueError):
        return False


def _scope_supports_alternatives(evidence):
    try:
        scope = json.loads(evidence.escopo_json or "{}")
    except (TypeError, ValueError):
        scope = {}
    if not isinstance(scope, dict):
        return False
    # Evidências reais identificam o documento pelo escopo (prova/cargo/código/
    # versão), não por um campo artificial. ``parte=conteudo`` é o suporte do
    # alvo; contexto compartilhado não delimita alternativas por si só.
    return (evidence.parte == "conteudo"
            and all(str(scope.get(key) or "").strip() for key in ("prova", "cargo", "codigo"))
            and bool(str(scope.get("versao") or scope.get("numero") or "").strip()))


def _source(version, evidence):
    source_id = evidence.documento_fonte_id if evidence is not None else version.documento_fonte_id
    if not source_id:
        return None
    return DocumentoFonte.get_or_none(DocumentoFonte.id == source_id)


def _row(version, letter, current, proposal, status, reason, *, evidence=None, result=None,
         categoria=None, field="alternativas"):
    region = None
    if isinstance(result, dict) and isinstance(result.get("region"), dict):
        source_region = result["region"]
        region = {"source_id": source_region.get("source_id") or (evidence.documento_fonte_id if evidence else None),
                  "sha256": source_region.get("source_sha256") or source_region.get("sha256"),
                  "page": source_region.get("page") or (evidence.pagina if evidence else None),
                  "bounds": source_region.get("bounds") or ([evidence.x0, evidence.y0, evidence.x1, evidence.y1] if evidence else None)}
    elif evidence is not None:
        source = DocumentoFonte.get_or_none(DocumentoFonte.id == evidence.documento_fonte_id)
        region = {"source_id": evidence.documento_fonte_id, "sha256": getattr(source, "sha256", None),
                  "page": evidence.pagina, "bounds": [evidence.x0, evidence.y0, evidence.x1, evidence.y1]}
    analysis = None
    if isinstance(result, dict):
        analysis = {"version_id": version.id, "field": field, "letter": letter,
                    "status": status, "proposal": proposal, "reason": reason,
                    "readings": result.get("readings", {}),
                    "evidence": result.get("region"), "region": region}
    return {
        "questao_id": version.questao_id, "version_id": version.id,
        "categoria": categoria or ("revisao" if status == "revisao" else status),
        "field": field, "letter": letter, "current": current,
        "proposal": proposal, "status": status, "reason": reason,
        "region": region, "geometry": region and region["bounds"],
        "evidence": result.get("region") if isinstance(result, dict) else None,
        "readings": result.get("readings", {}) if isinstance(result, dict) else {},
        "result": result, "analysis": analysis, "error": False,
    }


def _stable(version, source):
    return (version.id, version.numero_versao, version.hash_conteudo,
            getattr(source, "id", None), getattr(source, "sha256", None))


def _valid_source(source):
    if source is None or not source.localizacao or not Path(source.localizacao).is_file():
        return False
    try:
        return bool(verify_source(source.id).get("integro"))
    except Exception:
        return False


def _unhandled_rows(version, assessment, *, exclude_fields=()):
    """Materializa pendências que a triagem de alternativas não lê."""
    rows, seen = [], set(exclude_fields)
    for item in assessment.get("pendencias", []):
        field = diagnostic_target(item)
        if field == "alternativas":
            continue
        if item.get("parte") == "contexto":
            field = "texto_apoio"
        elif item.get("parte") == "recurso_visual":
            field = "recurso_visual"
        if field in seen:
            continue
        seen.add(field)
        code = item.get("codigo") or "diagnostico"
        message = (item.get("mensagem") or item.get("message") or
                   item.get("justificativa") or "Confira o original.")
        rows.append(_row(version, None, None, None, "revisao",
                         f"{code}: {message}", categoria="revisao", field=field))
    return rows


def triage_questions(question_ids, *, cancel_event=None, progress=None, runtime=None,
                     reader=None, repo_module=None):
    """Analisa apenas as questões selecionadas e devolve propostas pendentes."""
    source_repo = repo_module or repo
    ids = list(dict.fromkeys(question_ids or []))
    rows, counts = [], {"liberada": 0, "bloqueada": 0, "conferir": 0,
                        "proposta": 0, "revisao": 0, "erro": 0}
    cancelled = False

    def stopped():
        return cancel_event is not None and cancel_event.is_set()

    from src.importador.ia_runtime import LocalVisionRuntime
    from src.importador.ia_ocr import LocalOcrReader
    runtime_used = runtime or LocalVisionRuntime()
    reader_used = reader or LocalOcrReader()
    with _batch(runtime_used), _batch(reader_used):
        for index, question_id in enumerate(ids, 1):
            if stopped():
                cancelled = True
                break
            try:
                question = _question(question_id, source_repo)
                if not question or not question.get("ativa", True):
                    continue
                version = _latest(question_id, source_repo)
                if version is None:
                    continue
                before = _stable(version, _source(version, None))
                from src.models.provenance_service import _version_is_current
                if not _version_is_current(version):
                    raise ValueError("A versão atual não corresponde ao snapshot.")
                assessment = assess_version(version.id)
                if assessment.get("liberada"):
                    counts["liberada"] += 1
                    rows.append(_row(version, None, None, None, "liberada",
                                     "Versão liberada por assess_version; nenhuma IA foi acionada.",
                                     categoria="liberada", field=None))
                    continue
                evidence_rows = list(EvidenciaQuestao.select().where(
                    EvidenciaQuestao.questao_versao == version.id).order_by(EvidenciaQuestao.id))
                content_evidence = [e for e in evidence_rows
                                    if e.parte == "conteudo"
                                    and e.documento_fonte_id == version.documento_fonte_id
                                    and _geometry(e) and _scope_supports_alternatives(e)]
                unique_regions = {(e.pagina, e.x0, e.y0, e.x1, e.y1) for e in content_evidence}
                source_evidence = content_evidence[0] if len(unique_regions) == 1 else None
                source = _source(version, source_evidence)
                preliminary = any(item.get("codigo") == "gabarito_preliminar"
                                  for item in assessment.get("pendencias", []))
                if (preliminary or not content_evidence or len(unique_regions) != 1
                        or source is None or not _valid_source(source)
                        or not isinstance(_content(version).get("numero_oficial"), int)
                        or not _version_is_current(version)):
                    counts["bloqueada"] += 1
                    if preliminary:
                        preliminary_items = [item for item in assessment.get("pendencias", [])
                                             if item.get("codigo") == "gabarito_preliminar"]
                        reason = "; ".join(
                            f"{item.get('codigo')}: {item.get('mensagem') or item.get('message') or item.get('justificativa') or 'gabarito preliminar'}"
                            for item in preliminary_items
                        ) or "gabarito_preliminar: o gabarito preliminar não libera a questão."
                        rows.append(_row(version, None, None, None, "bloqueada", reason,
                                         categoria="bloqueada", field="gabarito"))
                        rows.extend(_unhandled_rows(version, assessment, exclude_fields={"gabarito"}))
                    else:
                        codes = [str(item.get("codigo")) for item in assessment.get("pendencias", [])
                                 if item.get("codigo")]
                        reason = "Sem fonte íntegra/evidência geométrica suficiente de conteúdo"
                        if codes:
                            reason += ". Diagnósticos: " + ", ".join(codes)
                        rows.append(_row(version, None, None, None, "bloqueada", reason,
                                         categoria="bloqueada", field=None))
                        rows.extend(_unhandled_rows(version, assessment))
                    continue
                alternatives = _content(version).get("alternativas") or []
                if not alternatives:
                    counts["bloqueada"] += 1
                    rows.append(_row(version, None, None, None, "bloqueada",
                                     "A versão não possui alternativas analisáveis.", categoria="bloqueada", field=None))
                    rows.extend(_unhandled_rows(version, assessment))
                    continue
                for alt in alternatives:
                    if stopped():
                        cancelled = True
                        break
                    letter, current = alt.get("letra"), alt.get("texto", "")
                    try:
                        evidence = prepare_evidence(source.localizacao, source_evidence.pagina,
                            (source_evidence.x0, source_evidence.y0, source_evidence.x1, source_evidence.y1),
                            letter=letter, expected_sha256=source.sha256,
                            cancel_event=cancel_event, reader=reader_used)
                        result = analyze_evidence(evidence, current, runtime=runtime_used,
                                                   cancel_event=cancel_event)
                        row_status = result.get("status", "revisao")
                        reason = result.get("reason") or "Leitura pendente de conferência humana."
                        category = ("proposta" if row_status == "proposta" else
                                    "conferir" if row_status == "manter" else "revisao")
                        rows.append(_row(version, letter, current, result.get("proposal"), row_status,
                                         reason, evidence=source_evidence, result=result,
                                         categoria=category))
                        counts[category] += 1
                    except (InterruptedError, TimeoutError) as exc:
                        if stopped():
                            cancelled = True
                            break
                        error_row = _row(version, letter, current, None, "revisao",
                                         f"Falha isolada na leitura: {type(exc).__name__}.", evidence=source_evidence,
                                         categoria="revisao")
                        error_row["error"] = True
                        rows.append(error_row)
                        counts["erro"] += 1
                        counts["revisao"] += 1
                    except Exception as exc:
                        error_row = _row(version, letter, current, None, "revisao",
                                         f"Falha isolada na leitura: {type(exc).__name__}.", evidence=source_evidence)
                        error_row["error"] = True
                        rows.append(error_row)
                        counts["erro"] += 1
                        counts["revisao"] += 1
                after = _latest(question_id, source_repo)
                after_source = _source(after, None) if after is not None else None
                after_current = after is not None and _stable(after, after_source) == before
                after_current = after_current and _version_is_current(after) and _valid_source(after_source)
                if not after_current:
                    for row in rows:
                        if row["version_id"] == version.id:
                            row["status"] = "revisao"
                            row["categoria"] = "revisao"
                            row["proposal"] = None
                            row["analysis"] = None
                            row["reason"] = "A versão ou a fonte mudou durante a análise; proposta invalidada."
                if cancelled:
                    break
                # A triagem v1 só lê alternativas. Pendências de outros campos
                # continuam visíveis para a fila, sem inventar geometria.
                rows.extend(_unhandled_rows(version, assessment))
            except Exception as exc:
                counts["erro"] += 1
                rows.append({"questao_id": question_id, "version_id": None, "field": "alternativas",
                             "letter": None, "current": None, "proposal": None, "status": "revisao",
                             "reason": f"Falha isolada na triagem: {type(exc).__name__}.",
                             "region": None, "geometry": None, "evidence": None, "readings": {},
                             "result": None, "analysis": None, "categoria": "revisao", "field": None, "error": True})
            finally:
                if progress:
                    progress(index, len(ids))
    counts = {key: 0 for key in counts}
    for row in rows:
        category = row.get("categoria")
        if category in counts:
            counts[category] += 1
        if row.get("error"):
            counts["erro"] += 1
    return {"rows": rows, "counts": counts, "cancelled": cancelled}


def validate_triage_row(row):
    """Confirma que a versão/fonte de uma proposta ainda são os atuais."""
    try:
        version = QuestaoVersao.get_or_none(QuestaoVersao.id == row["version_id"])
        question = Questao.get_or_none(Questao.id == version.questao_id) if version else None
        if version is None or question is None or not question.ativa:
            raise ValueError("A questão não está ativa ou a versão não existe.")
        latest = _latest(version.questao_id, repo)
        from src.models.provenance_service import _version_is_current
        if latest is None or latest.id != version.id or not _version_is_current(version):
            raise ValueError("A versão mudou; atualize a triagem.")
        region = row.get("region") or {}
        source_id = region.get("source_id")
        source = DocumentoFonte.get_or_none(DocumentoFonte.id == source_id)
        if source is None or source.id != version.documento_fonte_id or not _valid_source(source):
            raise ValueError("A fonte da triagem está ausente, alterada ou não pertence à versão.")
        expected = region.get("sha256")
        if expected and expected != source.sha256:
            raise ValueError("O hash da fonte mudou; releia a evidência.")
        return True
    except (KeyError, AttributeError, TypeError) as exc:
        raise ValueError("Linha de triagem inválida.") from exc

