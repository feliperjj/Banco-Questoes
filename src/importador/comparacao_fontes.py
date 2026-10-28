"""Equivalência documental exata de cópias, sem usar o nome do arquivo."""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

import pdfplumber

from .pdf_render import render_region, rendering_batch
from .pdf_texto import _normalizar_pagina


@lru_cache(maxsize=64)
@rendering_batch
def _comparar(actual_path, actual_hash, reference_path, reference_hash):
    if actual_hash == reference_hash:
        return {"regra": "pdf-sha256-v1", "sha256_fonte": actual_hash,
                "sha256_referencia": reference_hash}
    pages = []
    with pdfplumber.open(actual_path) as actual, pdfplumber.open(reference_path) as reference:
        if len(actual.pages) != len(reference.pages):
            return None
        for number, (left, right) in enumerate(zip(actual.pages, reference.pages), 1):
            dimensions = (float(left.width), float(left.height), int(left.rotation or 0))
            if dimensions != (float(right.width), float(right.height), int(right.rotation or 0)):
                return None
            left_text = _normalizar_pagina(left.extract_text() or "")
            right_text = _normalizar_pagina(right.extract_text() or "")
            if left_text != right_text:
                return None
            bbox = (0, 0, dimensions[0], dimensions[1])
            left_pixels = render_region(actual_path, number, bbox, scale=2.0)
            right_pixels = render_region(reference_path, number, bbox, scale=2.0)
            if left_pixels != right_pixels:
                return None
            pages.append({"pagina": number, "dimensoes": dimensions,
                "texto_sha256": sha256(left_text.encode("utf-8")).hexdigest(),
                "pixels_sha256": left_pixels["pixels_sha256"], "tamanho_pixels": left_pixels["size"]})
    return {"regra": "pdf-texto-e-pixels-v1", "sha256_fonte": actual_hash,
        "sha256_referencia": reference_hash, "paginas": len(pages), "escala": 2.0,
        "fingerprint_paginas": sha256(json.dumps(pages, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def comparar_documentos(actual, reference):
    actual, reference = Path(actual).resolve(), Path(reference).resolve()
    # O hash entra no cache, além do caminho: mudar uma imagem preservando
    # tamanho/mtime não pode reaproveitar uma equivalência antiga.
    actual_hash = sha256(actual.read_bytes()).hexdigest()
    reference_hash = sha256(reference.read_bytes()).hexdigest()
    return deepcopy(_comparar(str(actual), actual_hash, str(reference), reference_hash))
