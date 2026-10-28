"""Persistência segura do rascunho da importação em andamento."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path

from src.config import DATA_DIR


RASCUNHO_PATH = DATA_DIR / "importacao_rascunhos" / "atual.json"
VERSAO_RASCUNHO = 1


class FonteRascunhoAlterada(ValueError):
    """A origem guardada no rascunho não corresponde mais ao arquivo atual."""


@lru_cache(maxsize=8)
def _hash_fonte(path: str, size: int, modified_ns: int) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _origens(payload: dict) -> dict[str, dict[str, str]]:
    origins = {}
    locked_hashes = payload.get("source_hashes") or {}
    for key, path_value in (("caderno", payload.get("caminho_caderno")),
                            ("gabarito", payload.get("caminho_gabarito"))):
        if not path_value:
            continue
        path = Path(path_value).expanduser().resolve()
        if not path.is_file():
            raise FonteRascunhoAlterada(f"O arquivo de {key} não está disponível: {path.name}.")
        stat = path.stat()
        digest = locked_hashes.get(key)
        if not digest:
            digest = _hash_fonte(str(path), stat.st_size, stat.st_mtime_ns)
        origins[key] = {"path": str(path), "sha256": digest}
    if "caderno" not in origins:
        raise ValueError("O rascunho não contém o caminho do caderno.")
    return origins


def salvar_rascunho(payload: dict) -> dict[str, str]:
    """Grava por substituição atômica, vinculando o rascunho aos PDFs atuais."""
    document = {"versao": VERSAO_RASCUNHO, "origens": _origens(payload),
                "dados": payload}
    destination = RASCUNHO_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
    os.replace(temporary, destination)
    return {key: origin["sha256"] for key, origin in document["origens"].items()}


def carregar_rascunho() -> dict | None:
    if not RASCUNHO_PATH.is_file():
        return None
    # Recompute after restart even if the file kept its timestamp and size.
    _hash_fonte.cache_clear()
    try:
        document = json.loads(RASCUNHO_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("O rascunho salvo está ilegível; o arquivo foi preservado.") from error
    if document.get("versao") != VERSAO_RASCUNHO or not isinstance(document.get("dados"), dict):
        raise ValueError("O rascunho foi criado por uma versão incompatível; o arquivo foi preservado.")
    for origin in document.get("origens", {}).values():
        path = Path(origin.get("path", ""))
        if not path.is_file():
            raise FonteRascunhoAlterada(f"A fonte {path.name or 'selecionada'} foi removida.")
        stat = path.stat()
        current = _hash_fonte(str(path.resolve()), stat.st_size, stat.st_mtime_ns)
        if current != origin.get("sha256"):
            raise FonteRascunhoAlterada(f"A fonte {path.name} mudou desde que o rascunho foi salvo.")
    data = document["dados"]
    data["source_hashes"] = {key: origin["sha256"]
                             for key, origin in document["origens"].items()}
    return data


def remover_rascunho() -> None:
    RASCUNHO_PATH.unlink(missing_ok=True)
