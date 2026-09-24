"""Catalogs reusable layouts found in the current PDF sample collection.

This is a read-only inventory of PDFs and the confirmed associations in
config/gabaritos.json. It writes reports/catalogo_padroes.json and never opens
or changes the question database.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pdfplumber

from src.importador.catalogo import carregar_catalogo, normalizar_chave
from src.importador.perfis.documentos import (
    PerfilDocumento,
    classificar_caderno,
    classificar_gabarito,
    pontuar_associacao,
    segmentar_blocos_gabarito,
)


SAMPLES = ROOT / "samples"
CATALOGO = carregar_catalogo(ROOT / "config" / "gabaritos.json", base_dir=SAMPLES)
OUT = ROOT / "reports" / "catalogo_padroes.json"


def _perfil_de_dict(dados: dict) -> PerfilDocumento:
    return PerfilDocumento(
        tipo=dados["tipo"], padrao=dados["padrao"],
        evidencias=tuple(dados.get("evidencias", ())),
        identificadores=tuple(dados.get("identificadores", ())),
        candidatos=tuple(dados.get("candidatos", ())), aviso=dados.get("aviso", ""),
        familia=dados.get("familia", "desconhecida"),
        metadados={k: tuple(v) for k, v in (dados.get("metadados") or {}).items()},
        intervalo_questoes=tuple(dados.get("intervalo_questoes", ())),
        quantidade_respostas=dados.get("quantidade_respostas", 0),
    )


def _construir_funis(cadernos: dict, gabaritos: dict) -> dict:
    funis = {}
    registro_por_caderno = {normalizar_chave(k): v for k, v in CATALOGO.items()}
    for chave, perfil_caderno in cadernos.items():
        registro = registro_por_caderno.get(chave, {})
        candidatos = []
        por_etapa = {nome: 0 for nome in ("familia", "identificadores", "modelo_versao", "layout", "faixa_numerica")}
        for chave_gabarito, diagnostico in gabaritos.items():
            perfil_gabarito = PerfilDocumento(
                "gabarito", diagnostico["padrao_predominante"],
                tuple(sorted({e for p in diagnostico["paginas"] for e in p["evidencias"]})),
                tuple(diagnostico["identificadores"]),
                familia=diagnostico["familia_predominante"],
                metadados={k: tuple(v) for k, v in diagnostico["metadados"].items()},
                intervalo_questoes=tuple(diagnostico["intervalo_questoes"]),
            )
            registro_eh_este = normalizar_chave(registro.get("gabarito", "")) == chave_gabarito
            pontuacao = pontuar_associacao(
                perfil_caderno, perfil_gabarito,
                codigo=registro.get("codigo") or registro.get("prova") or "",
                cargo=registro.get("cargo") or "",
                evidencia_catalogo=registro.get("evidencia", "") if registro_eh_este and registro.get("confirmado") else "",
            )
            etapas = {etapa["etapa"]: etapa["sobreviveu"] for etapa in pontuacao["etapas"]}
            sobrevivente = True
            for nome in por_etapa:
                sobrevivente = sobrevivente and etapas.get(nome, False)
                if sobrevivente:
                    por_etapa[nome] += 1
            if pontuacao["decisao"] != "descartada":
                candidatos.append({
                    "gabarito": diagnostico["arquivo"], "pontos": pontuacao["pontos"],
                    "decisao": pontuacao["decisao"], "etapas": pontuacao["etapas"],
                })
        candidatos.sort(key=lambda item: (-item["pontos"], item["gabarito"]))
        funis[chave] = {
            "candidatos_iniciais": len(gabaritos),
            "sobreviventes_por_etapa": por_etapa,
            "candidatos_restantes": len(candidatos),
            "candidatos": candidatos[:5],
        }
    return funis


def _caderno_pdf(path: Path) -> bool:
    name = path.name.casefold()
    return not (name.startswith("gab") or "gabarito" in name)


def _texto_caderno(path: Path, max_paginas: int = 8) -> str:
    """Lê páginas representativas para inventário; não roda OCR nem o parser."""
    with pdfplumber.open(path) as pdf:
        return "\n".join((pagina.extract_text() or "") for pagina in pdf.pages[:max_paginas])


def _diagnosticar_gabarito(path: Path) -> dict:
    paginas = []
    textos = []
    with pdfplumber.open(path) as pdf:
        for numero, pagina in enumerate(pdf.pages, 1):
            texto = pagina.extract_text() or ""
            if not texto.strip():
                continue
            textos.append(texto)
            perfil = classificar_gabarito(texto)
            blocos = segmentar_blocos_gabarito(texto)
            paginas.append({
                "pagina": numero,
                "padrao": perfil.padrao,
                "familia": perfil.familia,
                "evidencias": list(perfil.evidencias),
                "identificadores": list(perfil.identificadores),
                "metadados": perfil.metadados or {},
                "intervalo_questoes": list(perfil.intervalo_questoes),
                "quantidade_respostas": perfil.quantidade_respostas,
                "blocos": [
                    {"id": bloco.identificador, "titulo": bloco.titulo, "padrao": bloco.padrao}
                    for bloco in blocos
                ],
            })
    perfis = defaultdict(list)
    for pagina in paginas:
        perfis[pagina["padrao"]].append(pagina["pagina"])
    perfil_completo = classificar_gabarito("\n".join(textos))
    padrao_predominante = perfil_completo.padrao if textos else "sem_texto"
    identificadores = sorted(perfil_completo.identificadores)
    familias = defaultdict(int)
    for pagina in paginas:
        if pagina["familia"] != "desconhecida":
            familias[pagina["familia"]] += 1
    intervalos = [perfil_completo.intervalo_questoes] if perfil_completo.intervalo_questoes else []
    metadados = {tipo: list(valores) for tipo, valores in (perfil_completo.metadados or {}).items()}
    return {
        "arquivo": path.relative_to(ROOT).as_posix(),
        "padrao_predominante": padrao_predominante,
        "familia_predominante": perfil_completo.familia,
        "padroes_por_pagina": dict(sorted(perfis.items())),
        "identificadores": identificadores,
        "metadados": metadados,
        "intervalo_questoes": [min(i[0] for i in intervalos), max(i[1] for i in intervalos)] if intervalos else [],
        "paginas": paginas,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Catalogar perfis e afunilar possíveis gabaritos.")
    parser.add_argument("--atualizar-funil", action="store_true",
                        help="Recalcula apenas o funil usando o último inventário salvo.")
    args = parser.parse_args()
    if args.atualizar_funil:
        resultado = json.loads(OUT.read_text(encoding="utf-8"))
        cadernos = {k: _perfil_de_dict(v) for k, v in resultado["cadernos"].items()}
        resultado["funis_candidatos"] = _construir_funis(cadernos, resultado["gabaritos"])
        OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Funil atualizado em {OUT}")
        return

    cadernos = {}
    padroes_caderno = defaultdict(list)
    for path in sorted(p for p in SAMPLES.rglob("*.pdf") if _caderno_pdf(p)):
        print(f"Caderno: {path.relative_to(SAMPLES)}", flush=True)
        texto = _texto_caderno(path)
        perfil = classificar_caderno(texto)
        chave = normalizar_chave(path.relative_to(SAMPLES))
        cadernos[chave] = perfil
        padroes_caderno[perfil.padrao].append(path.relative_to(ROOT).as_posix())

    caminhos_gabarito = {}
    for registro in CATALOGO.values():
        caminhos_gabarito.setdefault(normalizar_chave(registro["gabarito"]), registro["gabarito"])
    gabaritos = {}
    padroes_gabarito = defaultdict(list)
    for chave, caminho in sorted(caminhos_gabarito.items()):
        print(f"Gabarito: {caminho}", flush=True)
        diagnostico = _diagnosticar_gabarito(SAMPLES / caminho)
        gabaritos[chave] = diagnostico
        padroes_gabarito[diagnostico["padrao_predominante"]].append(diagnostico["arquivo"])

    associacoes = []
    for caderno, registro in CATALOGO.items():
        chave = normalizar_chave(caderno)
        perfil_caderno = cadernos.get(chave)
        diagnostico_gabarito = gabaritos.get(normalizar_chave(registro["gabarito"]))
        if not perfil_caderno or not diagnostico_gabarito:
            continue
        perfil_gabarito = PerfilDocumento(
            "gabarito",
            diagnostico_gabarito["padrao_predominante"],
            tuple(sorted({e for pagina in diagnostico_gabarito["paginas"] for e in pagina["evidencias"]})),
            tuple(diagnostico_gabarito["identificadores"]),
            familia=diagnostico_gabarito["familia_predominante"],
            metadados={k: tuple(v) for k, v in diagnostico_gabarito["metadados"].items()},
            intervalo_questoes=tuple(diagnostico_gabarito["intervalo_questoes"]),
        )
        associacoes.append({
            "caderno": caderno,
            "gabarito": registro["gabarito"],
            "perfil_caderno": perfil_caderno.como_dict(),
            "perfil_gabarito": perfil_gabarito.como_dict(),
            "resultado": pontuar_associacao(
                perfil_caderno,
                perfil_gabarito,
                codigo=registro.get("codigo") or registro.get("prova") or "",
                cargo=registro.get("cargo") or "",
                evidencia_catalogo=registro.get("evidencia", "") if registro.get("confirmado") else "",
            ),
        })

    # O catálogo confirmado prevalece; outros resultados são candidatos para revisão.
    funis = _construir_funis(cadernos, gabaritos)

    resultado = {
        "versao_catalogo": 1,
        "origem": "samples/*.pdf e config/gabaritos.json",
        "somente_leitura": True,
        "resumo": {
            "total_cadernos": len(cadernos),
            "total_gabaritos": len(gabaritos),
            "associacoes_confirmadas": len(associacoes),
            "padroes_caderno": {k: {"quantidade": len(v), "amostras": v} for k, v in sorted(padroes_caderno.items())},
            "padroes_gabarito": {k: {"quantidade": len(v), "amostras": v} for k, v in sorted(padroes_gabarito.items())},
        },
        "cadernos": {k: v.como_dict() for k, v in sorted(cadernos.items())},
        "gabaritos": gabaritos,
        "associacoes": associacoes,
        "funis_candidatos": funis,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado["resumo"], ensure_ascii=False, indent=2))
    print(f"Catálogo de padrões salvo em {OUT}")


if __name__ == "__main__":
    main()
