"""Gera inventário somente leitura do acervo e das evidências atualmente disponíveis."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import DB_PATH, REPORTS_DIR
from src.db.database import db
from src.db.models import QuestaoVersao
from src.models.provenance_service import (
    assess_version, begin_source_verification_batch, end_source_verification_batch,
)

DB_DEFAULT = DB_PATH
REPORT_DEFAULT = REPORTS_DIR / "diagnostico_confiabilidade"

KNOWN_CASES = [
    {"prova": "transpetro", "numero": 10, "codigo": "alternativa_provavelmente_fundida", "descricao": "Alternativa E na base contém o início do texto de inglês seguinte; no original a alternativa termina em 'incompreensão'.", "pagina_pdf": 3, "status": "divergencia_observada_pelo_agente; revisao_humana_pendente"},
    {"prova": "transpetro", "numeros": list(range(11, 21)), "codigo": "contexto_compartilhado_suspeito", "descricao": "Texto-base de inglês aparece no original nas páginas 4–5; os registros 11–20 devem estar vinculados a ele, mas texto_apoio está vazio.", "pagina_pdf": "4–5", "status": "vinculo_ausente_no_banco; revisao_humana_pendente"},
    {"prova": "transpetro", "numeros": [1, 2, 3, 4, 5, 6, 7, 8, 15], "codigo": "classificacao_suspeita", "descricao": "Classificação de disciplina possivelmente incompatível com o conteúdo.", "status": "observacao_nao_conferida"},
    {"prova": "transpetro", "numeros": [8, 20, 68, 70], "codigo": "residuo_suspeito", "descricao": "A base contém resíduo após alternativas em Q8, Q20, Q68 e Q70; os originais visuais não incluem esses sufixos.", "pagina_pdf": [3, 5, 14, 15], "status": "divergencia_observada_pelo_agente; revisao_humana_pendente"},
    {"prova": "transpetro", "numeros": [24, 25, 36], "codigo": "contraprova_alternativa_longa", "descricao": "Alternativas extensas legítimas no original; contraprovas contra bloqueio baseado apenas em comprimento.", "pagina_pdf": "não determinada nesta rodada", "status": "conferir_conteudo_pendente"},
    {"prova": "transpetro", "numeros": [41], "codigo": "formula_suspeita", "descricao": "A fórmula está impressa na fonte; conferir se a extração estruturada preserva sua notação completa.", "pagina_pdf": 10, "status": "fonte_visualizada; comparacao_completa_pendente"},
    {"prova": "transpetro", "numeros": [55, 57, 68, 70], "codigo": "recurso_visual_suspeito", "descricao": "Tabelas estão no original nas páginas indicadas; crops existem no acervo, mas os limites não foram certificados.", "pagina_pdf": [12, 13, 14, 15], "status": "fonte_visualizada; revisao_humana_pendente"},
    {"prova": "ibfc", "source_contains": "analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf", "numero": 1, "codigo": "contexto_referenciado", "descricao": "Texto-base e Q1 aparecem na página 2 do original; registro Q1 do Correios está sem texto_apoio.", "pagina_pdf": 2, "status": "vinculo_ausente_no_banco; revisao_humana_pendente"},
]


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def safe_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    direct = ROOT / path
    if direct.is_file():
        return direct
    in_samples = ROOT / "samples" / path
    return in_samples if in_samples.is_file() else direct


def extract_official_number(text: str | None) -> int | None:
    """Retorna somente número inicial explícito; não substitui ordem nem ID."""
    match = re.match(r"\s*(\d{1,3})\s*[.)\-:]\s+", text or "")
    return int(match.group(1)) if match else None


def audit_database(db_path: Path) -> dict:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}
        table_columns = {table: sorted(columns(conn, table)) for table in tables}
        quick_check = [r[0] for r in conn.execute("PRAGMA quick_check")]
        foreign_key_errors = [dict(r) for r in conn.execute("PRAGMA foreign_key_check")]

        proof_cols = columns(conn, "provas_cadastradas") if "provas_cadastradas" in tables else set()
        proof_select = [c for c in ("id", "nome", "arquivo_questoes", "arquivo_gabarito", "ativa") if c in proof_cols]
        proofs = [dict(r) for r in conn.execute(f'SELECT {", ".join(proof_select)} FROM provas_cadastradas ORDER BY id')] if proof_select else []
        question_cols = columns(conn, "questoes") if "questoes" in tables else set()
        q_fields = [c for c in ("id", "numero_oficial", "enunciado", "texto_apoio", "tipo", "banca", "ano", "cargo", "gabarito", "imagem_path", "ativa", "prova_origem_id") if c in question_cols]
        questions = {r["id"]: dict(r) for r in conn.execute(f'SELECT {", ".join(q_fields)} FROM questoes')} if q_fields else {}
        alternative_counts = {r[0]: r[1] for r in conn.execute("SELECT questao_id, COUNT(*) FROM alternativas GROUP BY questao_id")} if "alternativas" in tables else {}

        links = []
        if "prova_cadastrada_questoes" in tables and "provas_cadastradas" in tables:
            for row in conn.execute("SELECT prova_cadastrada_id, questao_id, ordem FROM prova_cadastrada_questoes ORDER BY prova_cadastrada_id, ordem, questao_id"):
                q = questions.get(row[1])
                links.append({
                    "prova_id": row[0], "questao_id": row[1], "ordem_na_prova": row[2],
                    "numero_oficial": (q or {}).get("numero_oficial"),
                    "numero_oficial_extraido_do_inicio": (q or {}).get("numero_oficial") or extract_official_number(q.get("enunciado") if q else None),
                    "questao_encontrada": q is not None,
                    "alternativas": alternative_counts.get(row[1], 0),
                    "tem_texto_apoio": bool((q or {}).get("texto_apoio")),
                    "tem_imagem_referenciada": bool((q or {}).get("imagem_path")),
                    "gabarito_armazenado": bool((q or {}).get("gabarito")),
                    "conteudo_conferido_por_pessoa": False,
                    "gabarito_confirmado_por_pessoa": False,
                })

        proof_by_id = {p["id"]: p for p in proofs}
        by_question = defaultdict(list)
        for link in links:
            by_question[link["questao_id"]].append(link["prova_id"])
        image_paths = []
        for qid, q in questions.items():
            if q.get("imagem_path"):
                path = safe_path(q["imagem_path"])
                image_paths.append({"questao_id": qid, "caminho": q["imagem_path"], "disponivel": bool(path and path.is_file())})

        sources = []
        for proof in proofs:
            item = dict(proof)
            for field in ("arquivo_questoes", "arquivo_gabarito"):
                path = safe_path(item.get(field))
                item[field + "_disponibilidade"] = "nao_informado" if path is None else ("presente" if path.is_file() else "ausente")
                item[field + "_sha256"] = sha256_file(path) if path and path.is_file() else None
            item["questoes_vinculadas"] = sum(link["prova_id"] == item["id"] for link in links)
            sources.append(item)

        cases = []
        for case in KNOWN_CASES:
            matches = []
            order_candidates = []
            proof_ids = [p["id"] for p in proofs if case["prova"] in (p.get("nome") or "").casefold()]
            if case.get("source_contains"):
                token = case["source_contains"].casefold()
                proof_ids = [
                    p["id"] for p in proofs
                    if token in (p.get("arquivo_questoes") or "").replace("\\", "/").casefold()
                ]
            nums = set(case.get("numeros", [case.get("numero")]))
            for link in links:
                if link["prova_id"] in proof_ids and link["numero_oficial_extraido_do_inicio"] in nums:
                    matches.append({"prova_id": link["prova_id"], "questao_id": link["questao_id"], "ordem_na_prova": link["ordem_na_prova"], "numero_oficial_extraido_do_inicio": link["numero_oficial_extraido_do_inicio"]})
                if link["prova_id"] in proof_ids and link["ordem_na_prova"] in nums:
                    order_candidates.append({"prova_id": link["prova_id"], "questao_id": link["questao_id"], "ordem_na_prova": link["ordem_na_prova"], "numero_oficial_extraido_do_inicio": link["numero_oficial_extraido_do_inicio"], "status": "candidato_por_ordem_nao_confirmado_como_numero_oficial"})
            cases.append({**case, "registros_encontrados": matches, "candidatos_por_ordem_na_prova": order_candidates, "fonte_disponivel": any(p.get("arquivo_questoes_disponibilidade") == "presente" for p in sources if p["id"] in proof_ids), "conferencia_humana": "pendente"})

        attempt_summary = {}
        for table in ("provas", "prova_questoes", "tentativas", "respostas", "progresso_tentativas"):
            if table in tables:
                attempt_summary[table] = counts[table]
        unfinished = []
        if "tentativas" in tables:
            cols = columns(conn, "tentativas")
            if {"id", "prova_id", "finalizada_em"}.issubset(cols):
                unfinished = [dict(r) for r in conn.execute("SELECT id, prova_id, iniciada_em, finalizada_em FROM tentativas WHERE finalizada_em IS NULL ORDER BY id")]
        return {
            "database": str(db_path.resolve()),
            "database_integrity": {"quick_check": quick_check, "foreign_key_errors": foreign_key_errors},
            "schema_version": conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()[0] if "schema_version" in tables else None,
            "tables": {name: {"rows": counts[name], "columns": table_columns[name]} for name in tables},
            "acervo": {
                "questoes": counts.get("questoes", 0), "alternativas": counts.get("alternativas", 0),
                "provas_cadastradas": counts.get("provas_cadastradas", 0), "vinculos_prova_questao": len(links),
                "questoes_com_gabarito_armazenado": sum(bool(q.get("gabarito")) for q in questions.values()),
                "questoes_com_texto_apoio": sum(bool(q.get("texto_apoio")) for q in questions.values()),
                "questoes_com_imagem_referenciada": len(image_paths),
                "imagens_referenciadas_ausentes": sum(not i["disponivel"] for i in image_paths),
                "questoes_vinculadas_a_mais_de_uma_prova": sum(len(ids) > 1 for ids in by_question.values()),
                "tentativas": attempt_summary, "tentativas_abertas": unfinished,
                "liberacao_por_revisao_humana": 0,
            },
            "fontes": sources,
            "imagens": image_paths,
            "questoes_por_prova": links,
            "casos_de_referencia": cases,
            "limites": [
                "O banco atual não registra status confiável de revisão humana nem evidência por página/região.",
                "Número oficial é extraído apenas quando aparece explicitamente no início do enunciado; ordem_na_prova e ID interno são campos separados.",
                "Um gabarito armazenado não prova que seja definitivo, correto, nem da versão/cargo correspondente.",
                "Os casos de referência são observações ainda não conferidas contra o original.",
            ],
        }
    finally:
        conn.close()


def render_markdown(report: dict) -> str:
    counts = report["acervo"]
    lines = [
        "# Diagnóstico de confiabilidade do acervo", "",
        f"- Gerado em UTC: {report['generated_at_utc']}",
        f"- Banco: `{report['database']}` (aberto somente para leitura)",
        f"- Schema: `{report['schema_version']}`",
        f"- Integridade: `quick_check={report['database_integrity']['quick_check']}`; violações FK: {len(report['database_integrity']['foreign_key_errors'])}", "",
        "## Inventário", "",
        f"- {counts['questoes']} questões; {counts['alternativas']} alternativas.",
        f"- {counts['provas_cadastradas']} provas cadastradas; {counts['vinculos_prova_questao']} vínculos questão/prova.",
        f"- {counts['questoes_com_gabarito_armazenado']} questões têm um gabarito armazenado; nenhuma é declarada confirmada por pessoa por falta desse registro.",
        f"- {counts['questoes_com_texto_apoio']} questões têm texto de apoio; {counts['questoes_com_imagem_referenciada']} referenciam imagens, das quais {counts['imagens_referenciadas_ausentes']} estão ausentes.",
        f"- Tentativas: {counts['tentativas']}; abertas: {len(counts['tentativas_abertas'])}; respostas: {counts['tentativas'].get('respostas', 0)}; progressos: {counts['tentativas'].get('progresso_tentativas', 0)}.", "",
        "## Fontes cadastradas", "", "| Prova ID | Questões | Fonte | Gabarito | SHA-256 da fonte |", "|---:|---:|---|---|---|",
    ]
    for source in report["fontes"]:
        lines.append(f"| {source['id']} | {source['questoes_vinculadas']} | {source.get('arquivo_questoes') or '—'} ({source['arquivo_questoes_disponibilidade']}) | {source.get('arquivo_gabarito') or '—'} ({source['arquivo_gabarito_disponibilidade']}) | {source['arquivo_questoes_sha256'] or '—'} |")
    funnel = report.get("funil")
    if funnel:
        lines.extend(["", "## Avaliação do funil por versão", "",
                      f"- Denominador: {funnel['denominador_versoes']} versões; liberadas: {funnel['liberadas']}; pendentes humanas/evidenciais: {funnel['pendentes_humanas']}.",
                      "- As etapas principais particionam versões; motivos podem se sobrepor.", "",
                      "| Etapa principal | Versões |", "|---|---:|"])
        lines.extend(f"| {stage} | {count} |" for stage, count in funnel["por_etapa_principal"].items())
        lines.extend(["", "| Motivo (sobreposto) | Versões |", "|---|---:|"])
        lines.extend(f"| {code} | {count} |" for code, count in funnel["por_motivo_sobreposto"].items())
    lines.extend(["", "## Referências prioritárias", "", "Os status abaixo são observações não conferidas, não expectativas certificadas. Candidatos localizados pela posição não são considerados equivalentes ao número oficial.", "", "| Código | Prova | Número(s) | Localização | Fonte | Conferência |", "|---|---|---|---|---|---|"])
    for case in report["casos_de_referencia"]:
        nums = case.get("numeros", [case.get("numero")])
        nums_text = ", ".join(map(str, nums))
        found = ", ".join(f"qID {m['questao_id']} / ordem {m['ordem_na_prova']} (nº explícito {m['numero_oficial_extraido_do_inicio']})" for m in case["registros_encontrados"]) or "não localizado por número inicial"
        candidates = ", ".join(f"qID {m['questao_id']} / ordem {m['ordem_na_prova']} (candidato, não confirmado)" for m in case["candidatos_por_ordem_na_prova"])
        location = found if case["registros_encontrados"] else candidates or found
        page = case.get("pagina_pdf", "—")
        lines.append(f"| {case['codigo']} | {case['prova']} | {nums_text} | {location} | p. {page}; {'presente' if case['fonte_disponivel'] else 'ausente'} | {case['status']} |")
    lines.extend(["", "## Limites", ""])
    lines.extend(f"- {item}" for item in report["limites"])
    return "\n".join(lines) + "\n"


def audit_funnel(db_path: Path) -> dict:
    """Executa a política do domínio numa conexão SQLite somente leitura."""
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    db.init(uri, uri=True, pragmas={"foreign_keys": 1, "query_only": 1})
    if not db.is_closed():
        db.close()
    db.connect(reuse_if_open=True)
    source_cache = begin_source_verification_batch()
    stages, reasons = Counter(), Counter()
    items = []
    released = 0
    try:
        versions = list(QuestaoVersao.select().order_by(QuestaoVersao.questao, QuestaoVersao.numero_versao))
        for version in versions:
            result = assess_version(version.id)
            stages[result["etapa_principal"]] += 1
            released += int(result["liberada"])
            codes = sorted({item["codigo"] for item in result["pendencias"]})
            reasons.update(codes)
            items.append({"questao_id": version.questao_id, "versao_id": version.id,
                          "versao": version.numero_versao, "etapa_principal": result["etapa_principal"],
                          "liberada": result["liberada"], "motivos": codes})
        return {"denominador_versoes": len(versions), "liberadas": released,
                "pendentes_humanas": len(versions) - released,
                "por_etapa_principal": dict(sorted(stages.items())),
                "por_motivo_sobreposto": dict(sorted(reasons.items())), "avaliacoes": items}
    finally:
        db.close()
        end_source_verification_batch(source_cache)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    parser.add_argument("--saida", type=Path, default=REPORT_DEFAULT)
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(f"Banco não encontrado: {args.db}")
    report = audit_database(args.db)
    report["funil"] = audit_funnel(args.db)
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.saida.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(f"Diagnóstico somente leitura gravado em {args.saida.with_suffix('.json')} e {args.saida.with_suffix('.md')}")
    print(f"{report['acervo']['questoes']} questões; {report['acervo']['vinculos_prova_questao']} vínculos; revisão humana registrada: 0")
    return 0 if report["database_integrity"]["quick_check"] == ["ok"] and not report["database_integrity"]["foreign_key_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
