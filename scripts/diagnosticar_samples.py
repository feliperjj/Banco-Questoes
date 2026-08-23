"""Executa somente extração/validação e gera relatório; não abre o banco."""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.importador.catalogo import carregar_catalogo, normalizar_chave
from src.importador.diagnostico import diagnosticar_caderno, salvar_relatorio
from src.importador.extrator import extrair_gabaritos_pdf, extrair_texto
from src.importador.parser import parsear_questoes


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico não destrutivo dos samples")
    parser.add_argument("--ocr", action="store_true", help="Completa números faltantes com OCR")
    args = parser.parse_args()
    samples = ROOT / "samples"
    catalogo = carregar_catalogo(ROOT / "config" / "gabaritos.json")
    relatorios = []
    for caminho in sorted(samples.rglob("*.pdf")):
        if caminho.name.lower().startswith("gab") or "gabarito" in caminho.name.lower():
            continue
        texto = extrair_texto(str(caminho))
        questoes = parsear_questoes(texto, str(caminho))
        chave = normalizar_chave(caminho.relative_to(samples))
        registro = catalogo.get(chave)
        gabaritos = {}
        motivos = []
        cargo = codigo = ""
        metodo = "nenhum"
        gabarito_candidato = ""
        if registro:
            cargo = registro["cargo"]
            codigo = registro.get("codigo") or registro.get("prova") or ""
            arquivo = samples / registro["gabarito"]
            gabarito_candidato = registro["gabarito"]
            if arquivo.exists():
                numeros = {int(q.get("numero", indice)) for indice, q in enumerate(questoes, 1)}
                gabaritos = extrair_gabaritos_pdf(
                    str(arquivo), codigo, cargo or None,
                    usar_ocr=args.ocr, numeros_esperados=numeros,
                )
                for numero in registro.get("anuladas", []):
                    gabaritos[int(numero)] = "X"
                metodo = "texto|tabela|ocr" if args.ocr else "texto|tabela"
            else:
                motivos.append("arquivo_gabarito_ausente")
        else:
            motivos.append("gabarito_nao_associado")
        relatorios.append(diagnosticar_caderno(
            str(caminho.relative_to(ROOT)), questoes, gabaritos,
            gabarito_candidato=gabarito_candidato, cargo=cargo, codigo=codigo,
            metodo=metodo, motivos=motivos,
        ))
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    salvar_relatorio(relatorios, out / "diagnostico_samples.json", out / "diagnostico_samples.md")
    print(json.dumps({"arquivos": len(relatorios), "questoes": sum(r["total_questoes"] for r in relatorios), "extraidos": sum(r["respostas_extraidas"] for r in relatorios), "vinculados": sum(r["respostas_vinculadas"] for r in relatorios)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
