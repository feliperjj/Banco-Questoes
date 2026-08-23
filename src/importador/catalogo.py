"""Catálogo versionado de associações confirmadas de gabaritos."""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED = {"gabarito", "confirmado", "evidencia"}


def normalizar_chave(caderno: str | Path) -> str:
    """Normaliza a chave relativa sem descartar diretórios significativos."""
    return str(caderno).replace("\\", "/").removeprefix("./").casefold()


def validar_catalogo(catalogo: dict, *, base_dir: Path | None = None, exigir_arquivos: bool = False) -> dict:
    if not isinstance(catalogo, dict):
        raise ValueError("O catálogo deve ser um objeto JSON.")
    base_dir = base_dir or Path.cwd()
    chaves_normalizadas = set()
    for caderno, registro in catalogo.items():
        chave = normalizar_chave(caderno)
        if chave in chaves_normalizadas:
            raise ValueError(f"Chave duplicada no catálogo: {caderno}.")
        chaves_normalizadas.add(chave)
        if not isinstance(registro, dict) or not REQUIRED.issubset(registro):
            raise ValueError(f"Registro inválido para {caderno}: campos obrigatórios ausentes.")
        if not registro["confirmado"] or not str(registro["evidencia"]).strip():
            raise ValueError(f"Registro sem confirmação/evidência: {caderno}.")
        if not str(registro.get("cargo") or "").strip() and not registro.get("arquivo_unico"):
            raise ValueError(f"Cargo vazio sem confirmação de arquivo único: {caderno}.")
        if exigir_arquivos and not (base_dir / str(registro["gabarito"])).exists():
            raise FileNotFoundError(f"Arquivo de gabarito ausente: {registro['gabarito']}")
    return {normalizar_chave(chave): registro for chave, registro in catalogo.items()}


def carregar_catalogo(caminho: str | Path, *, base_dir: Path | None = None, exigir_arquivos: bool = False) -> dict:
    caminho = Path(caminho)
    with caminho.open(encoding="utf-8") as arquivo:
        catalogo = json.load(arquivo)
    return validar_catalogo(catalogo, base_dir=base_dir or caminho.parent, exigir_arquivos=exigir_arquivos)


def selecionar_associacao(catalogo: dict, caderno: str, *, cargo: str | None = None, prova: str | None = None) -> dict:
    """Seleciona somente registro exato; nomes semelhantes são ambíguos."""
    registro = catalogo.get(normalizar_chave(caderno))
    if registro is None:
        raise LookupError(f"Caderno não catalogado: {caderno}")
    if cargo is not None and registro.get("cargo") != cargo:
        raise LookupError("Cargo não confirmado para o caderno.")
    if prova is not None and registro.get("prova") != prova:
        raise LookupError("Prova não confirmada para o caderno.")
    return registro
