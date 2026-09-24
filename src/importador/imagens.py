"""Preserva uma página-fonte para questões que dependem de figuras ou tabelas."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pdfplumber


_REF_VISUAL = re.compile(
    r"(?i)\b(?:figura|gr[áa]fico|imagem|tabela|quadro|mapa|charge|tirinha)\b"
    r"\s+(?:a seguir|abaixo|acima|precedente|apresentad\w*|mostrad\w*|seguinte)\b"
)


def anexar_imagens_referenciadas(caminho: str | Path, questoes: list[dict], raiz: str | Path) -> int:
    """Renderiza páginas de origem das questões com referência visual explícita."""
    caminho, raiz = Path(caminho), Path(raiz)
    alvos = [
        q for q in questoes
        if _REF_VISUAL.search(q.get("enunciado", "") + " " + " ".join(a.get("texto", "") for a in q.get("alternativas") or []))
    ]
    if caminho.suffix.lower() != ".pdf" or not alvos:
        return 0

    digest = hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]
    destino = raiz / "data" / "questao_imagens"
    destino.mkdir(parents=True, exist_ok=True)
    paginas = []
    with pdfplumber.open(caminho) as pdf:
        for numero, pagina in enumerate(pdf.pages, 1):
            texto = pagina.extract_text() or ""
            paginas.append((numero, texto))
        salvas = 0
        for q in alvos:
            n = int(q.get("numero") or 0)
            ancora = " ".join(q.get("enunciado", "").split()[:9])
            indice = next(
                (i for i, (_, texto) in enumerate(paginas)
                 if ancora and ancora.casefold() in " ".join(texto.split()).casefold()),
                None,
            )
            achou_por_ancora = indice is not None
            marcador = re.compile(rf"(?im)^\s*(?:QUEST(?:ÃO|AO|�O)\s*)?0*{n}(?:[.)\-:]|\s)\s*$")
            if indice is None:
                indice = next((i for i, (_, texto) in enumerate(paginas) if marcador.search(texto)), None)
            if indice is None:
                q["aviso_importacao"] = " ".join(filter(None, [q.get("aviso_importacao"), "A questão cita um elemento visual, mas não foi possível localizar sua página no PDF."]))
                continue
            # Uma referência no fim da página pode apontar para a figura logo
            # no começo da página seguinte. Combine ambas em uma imagem longa.
            indices = [indice]
            linha = paginas[indice][1]
            pos = marcador.search(linha)
            inicio_bloco = pos.start() if pos else 0
            proximo = re.search(r"(?im)^\s*(?:QUEST(?:ÃO|AO|�O)\s*)?0*\d{1,3}(?:[.)\-:]|\s)\s*$", linha[inicio_bloco + 1:])
            if not achou_por_ancora and proximo is None and indice + 1 < len(paginas):
                indices.append(indice + 1)
            imagens = [pdf.pages[i].to_image(resolution=125).original.convert("RGB") for i in indices]
            if len(imagens) == 1:
                imagem = imagens[0]
            else:
                from PIL import Image
                largura = max(im.width for im in imagens)
                imagem = Image.new("RGB", (largura, sum(im.height for im in imagens)), "white")
                topo = 0
                for parte in imagens:
                    imagem.paste(parte, (0, topo))
                    topo += parte.height
            nome = f"{digest}_q{n}.png"
            caminho_imagem = destino / nome
            imagem.save(caminho_imagem, optimize=True)
            q["imagem_path"] = caminho_imagem.relative_to(raiz).as_posix()
            salvas += 1
    return salvas
