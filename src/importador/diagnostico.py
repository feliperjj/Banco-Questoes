"""Geração de cobertura sem persistir ou alterar o banco local."""

from __future__ import annotations

import json
from pathlib import Path

from src.importador.validacao import validar_gabarito

def diagnosticar_caderno(
    caderno: str,
    questoes: list[dict],
    gabaritos: dict[int, str] | None = None,
    *,
    gabarito_candidato="",
    cargo="",
    codigo="",
    metodo="nenhum",
    motivos=None,
) -> dict:
    gabaritos = {} if gabaritos is None else gabaritos
    validacao = validar_gabarito(questoes, gabaritos)
    motivos_finais = set(motivos or []) | set(validacao["motivos"])
    vinculados = validacao["associados"]
    total = len(questoes)
    cobertura = vinculados / total * 100 if total else 0.0
    return {
        "caderno": caderno, "total_questoes": total, "gabarito_candidato": gabarito_candidato,
        "cargo": cargo, "codigo": codigo, "metodo": metodo, "respostas_extraidas": len(gabaritos),
        "respostas_vinculadas": vinculados,
        "taxa_extracao": len(gabaritos) / total * 100 if total else 0.0,
        "taxa_associacao": vinculados / len(gabaritos) * 100 if gabaritos else 0.0,
        "cobertura_final": cobertura,
        "ganho_potencial": max(0, total - vinculados),
        "faltantes": validacao["faltantes"], "extras": validacao["extras"], "duplicados": validacao["duplicados"],
        "motivos": sorted(motivos_finais), "revisao_manual": bool(motivos_finais),
        "numeracao": validacao["numeracao"], "escopo_divergente": validacao["escopo_divergente"],
        "quantidade_sem_numero_oficial": sum(
            not q.get("numero") or str(q.get("numero")).strip() in {"", "0"} for q in questoes
        ),
    }


def relatorio_markdown(relatorios: list[dict]) -> str:
    linhas = ["# Diagnóstico de cobertura", "", "| Caderno | Questões | Extraídos | Vinculados | Cobertura | Potencial | Motivos |", "|---|---:|---:|---:|---:|---:|---|"]
    for item in sorted(relatorios, key=lambda registro: registro["ganho_potencial"], reverse=True):
        motivos = ", ".join(item["motivos"]) or "—"
        linhas.append(f"| {item['caderno']} | {item['total_questoes']} | {item['respostas_extraidas']} | {item['respostas_vinculadas']} | {item['cobertura_final']:.1f}% | {item['ganho_potencial']} | {motivos} |")
    return "\n".join(linhas) + "\n"


def salvar_relatorio(relatorios: list[dict], json_path: str | Path, markdown_path: str | Path) -> None:
    Path(json_path).write_text(json.dumps(relatorios, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(markdown_path).write_text(relatorio_markdown(relatorios), encoding="utf-8")
