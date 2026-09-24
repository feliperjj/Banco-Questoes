"""Compare reimported answers with the pre-reimport local answer reference."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "questoes.db"
REPORT = ROOT / "reports" / "reimportacao_samples.json"
OUT = ROOT / "reports" / "avaliacao_reimportacao.json"


def _chave(caminho: str) -> str:
    return str(caminho).replace("\\", "/").removeprefix("./").casefold()


def _normalizar(valor: str | None) -> str:
    valor = (valor or "").strip().casefold()
    return {
        "x": "anulada", "anulado": "anulada", "anulada": "anulada",
        "certo": "certo", "errado": "errado",
    }.get(valor, valor)


def main() -> None:
    relatorio = json.loads(REPORT.read_text(encoding="utf-8"))
    backup = Path(relatorio["backup"])
    if not backup.is_absolute():
        backup = ROOT / backup
    if not backup.exists():
        raise FileNotFoundError(f"Backup anterior ao reimport não encontrado: {backup}")
    with sqlite3.connect(backup) as db:
        ouro = {}
        sql = """
            SELECT p.arquivo_questoes, q.gabarito
            FROM provas_cadastradas p
            JOIN prova_cadastrada_questoes pq ON pq.prova_cadastrada_id = p.id
            JOIN questoes q ON q.id = pq.questao_id
            ORDER BY p.id, pq.ordem
        """
        for caminho, resposta in db.execute(sql):
            ouro.setdefault(_chave(caminho), []).append(_normalizar(resposta))

    por_arquivo = []
    totais = {"referencias": 0, "preditas": 0, "corretas": 0, "divergentes": 0, "ausentes": 0}
    for arquivo in relatorio["por_arquivo"]:
        caminho = _chave(arquivo["arquivo"])
        gabarito_ouro = ouro.get(caminho, [])
        itens = arquivo.get("itens", [])
        if not gabarito_ouro:
            continue
        comparaveis = min(len(gabarito_ouro), len(itens))
        corretas = divergentes = preditas = 0
        for indice in range(comparaveis):
            esperado = gabarito_ouro[indice]
            obtido = _normalizar(itens[indice].get("gabarito"))
            if obtido:
                preditas += 1
            if esperado and obtido == esperado:
                corretas += 1
            elif esperado and obtido:
                divergentes += 1
        gold_count = sum(bool(v) for v in gabarito_ouro)
        faltantes = max(0, len(gabarito_ouro) - comparaveis) + sum(
            bool(gabarito_ouro[i]) and not _normalizar(itens[i].get("gabarito"))
            for i in range(comparaveis)
        )
        precisao = corretas / preditas if preditas else 0
        cobertura = corretas / gold_count if gold_count else 0
        por_arquivo.append({
            "arquivo": arquivo["arquivo"],
            "referencias": gold_count,
            "preditas": preditas,
            "corretas": corretas,
            "divergentes": divergentes,
            "ausentes": faltantes,
            "precisao": precisao,
            "cobertura": cobertura,
            "cobertura_extracao_do_importador": arquivo.get("validacao", {}).get("cobertura_percentual"),
        })
        totais["referencias"] += gold_count
        totais["preditas"] += preditas
        totais["corretas"] += corretas
        totais["divergentes"] += divergentes
        totais["ausentes"] += faltantes

    resultado = {
        "referencia": str(backup.relative_to(ROOT)) if backup.is_relative_to(ROOT) else str(backup),
        "fontes_com_gabarito_de_referencia": len(por_arquivo),
        "totais": totais,
        "precisao": totais["corretas"] / totais["preditas"] if totais["preditas"] else 0,
        "cobertura": totais["corretas"] / totais["referencias"] if totais["referencias"] else 0,
        "por_arquivo": por_arquivo,
    }
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in resultado.items() if k != "por_arquivo"}, ensure_ascii=False, indent=2))
    print(f"Detalhes por prova: {OUT}")


if __name__ == "__main__":
    main()
