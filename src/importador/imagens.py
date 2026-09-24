"""Extrai recortes das figuras e tabelas citadas pelas questões."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pdfplumber


_REF_VISUAL = re.compile(
    r"(?i)\b(?:figura|gr[áa]fico|imagem|tabela|quadro|mapa|cartograma|charge|tirinha)\b"
    r"\s+(?:a seguir|abaixo|acima|precedente|apresentad\w*|mostrad\w*|seguinte)\b"
)
_REFERENCIA_ABAIXO = re.compile(r"(?i)\b(?:a seguir|abaixo|seguinte)\b")
_REFERENCIA_ACIMA = re.compile(r"(?i)\b(?:acima|precedente)\b")


def _texto_questao(questao: dict) -> str:
    alternativas = " ".join(a.get("texto", "") for a in questao.get("alternativas") or [])
    return " ".join((questao.get("enunciado", ""), questao.get("texto_apoio", ""), alternativas))


def _padrao_frase(texto: str) -> str:
    return r"\s+".join(re.escape(parte) for parte in texto.split())


def _ancora_pagina(pdf, questao: dict):
    palavras = questao.get("enunciado", "").split()[:9]
    if len(palavras) >= 3:
        ancora = _padrao_frase(" ".join(palavras))
        for indice, pagina in enumerate(pdf.pages):
            achados = pagina.search(ancora, regex=True, case=False)
            if achados:
                return indice, achados[0]

    numero = int(questao.get("numero") or 0)
    padrao_numero = re.compile(rf"(?<!\d)0*{numero}(?:[.)])?(?!\d)")
    for indice, pagina in enumerate(pdf.pages):
        palavras_pagina = pagina.extract_words()
        achados = [
            palavra for palavra in palavras_pagina
            if padrao_numero.fullmatch(palavra["text"].strip())
            and (palavra["x0"] < pagina.width * 0.2
                 or pagina.width * 0.48 < palavra["x0"] < pagina.width * 0.68)
        ]
        if achados:
            palavra = achados[0]
            return indice, {
                "x0": palavra["x0"], "x1": palavra["x1"],
                "top": palavra["top"], "bottom": palavra["bottom"],
            }
    return None, None


def _marcador_seguinte(pagina, questao: dict, ancora: dict):
    numero_seguinte = int(questao.get("numero") or 0) + 1
    if numero_seguinte <= 1:
        return None
    x_ancora = ancora["x0"]
    candidatos = []
    for palavra in pagina.extract_words():
        texto = palavra["text"].strip().rstrip(".)")
        if texto != str(numero_seguinte) or palavra["top"] <= ancora["top"] + 15:
            continue
        if abs(palavra["x0"] - x_ancora) <= 22:
            candidatos.append(palavra)
    return min(candidatos, key=lambda palavra: palavra["top"]) if candidatos else None


def _limites_horizontais(pagina, ancora: dict, duas_colunas_pdf: bool = False) -> tuple[float, float]:
    """Recorta a coluna da questão quando os marcadores confirmam duas colunas."""
    meio = pagina.width / 2
    marcadores = []
    for palavra in pagina.extract_words():
        texto = palavra["text"].strip().rstrip(".)")
        if not texto.isdigit() or not 1 <= int(texto) <= 200:
            continue
        if meio - 28 <= palavra["x0"] <= meio + 100:
            marcadores.append((int(texto), palavra["x0"]))
    tem_coluna_direita = any(
        numero + 1 == seguinte and abs(x - proximo_x) <= 22
        for numero, x in marcadores
        for seguinte, proximo_x in marcadores
    )
    if not (duas_colunas_pdf or tem_coluna_direita):
        return 0, pagina.width
    if ancora["x0"] >= meio - 28:
        return meio, pagina.width
    return 0, meio


def _fim_do_conteudo(pagina, limites_x: tuple[float, float], topo: float) -> float:
    """Evita carregar marca d'água e rodapé depois do fim do item."""
    linhas: dict[int, list[dict]] = {}
    limite_rodape = pagina.height * 0.92
    for palavra in pagina.extract_words():
        if not (limites_x[0] <= palavra["x0"] < limites_x[1]):
            continue
        if not topo <= palavra["top"] < limite_rodape:
            continue
        texto = palavra["text"].strip("()[]{}.,:;—–-_")
        if len(texto) < 2 or re.fullmatch(r"(?i)(?:www|https?|prova|terra|administra\w*)", texto):
            continue
        linhas.setdefault(round(palavra["top"] / 3), []).append(palavra)
    finais = [
        max(palavra["bottom"] for palavra in palavras)
        for palavras in linhas.values()
        if len(palavras) >= 2 or len(palavras[0]["text"].strip("()[]{}.,:;—–-_")) >= 5
    ]
    return max(finais, default=topo) + 16


def _pdf_tem_duas_colunas(pdf) -> bool:
    for pagina in pdf.pages:
        marcadores = []
        for palavra in pagina.extract_words():
            texto = palavra["text"].strip().rstrip(".)")
            if not texto.isdigit() or not 1 <= int(texto) <= 200:
                continue
            if pagina.width * 0.48 < palavra["x0"] < pagina.width * 0.68:
                marcadores.append((int(texto), palavra["x0"]))
        if any(
            numero + 1 == seguinte and abs(x - proximo_x) <= 22
            for numero, x in marcadores
            for seguinte, proximo_x in marcadores
        ):
            return True
    return False


def _recortar_regiao(pdf, questao: dict, frase: str, duas_colunas_pdf: bool = False):
    indice, ancora = _ancora_pagina(pdf, questao)
    if indice is None:
        padrao_frase = _padrao_frase(frase)
        for numero_pagina, candidata in enumerate(pdf.pages):
            referencias = candidata.search(padrao_frase, regex=True, case=False)
            if referencias:
                indice, ancora = numero_pagina, referencias[0]
                break
    if indice is None:
        return None
    padrao_frase = _padrao_frase(frase)
    referencias = [
        (numero_pagina, referencia)
        for numero_pagina, candidata in enumerate(pdf.pages)
        for referencia in candidata.search(padrao_frase, regex=True, case=False)
    ]
    if referencias:
        indice_referencia, referencia = min(
            referencias,
            key=lambda item: (abs(item[0] - indice), abs(item[1]["top"] - ancora["top"]))
        )
    else:
        indice_referencia, referencia = indice, None
    pagina = pdf.pages[indice_referencia]
    ancora_visual = referencia or ancora
    limites_x = _limites_horizontais(pagina, ancora_visual, duas_colunas_pdf)
    seguinte = _marcador_seguinte(pagina, questao, ancora) if indice_referencia == indice else None
    margem = 12

    if referencia and _REFERENCIA_ABAIXO.search(frase):
        topo = referencia["top"] - margem
        fundo = seguinte["top"] - 1 if seguinte else _fim_do_conteudo(pagina, limites_x, topo)
    elif referencia and _REFERENCIA_ACIMA.search(frase):
        # A referência costuma vir depois da figura/tabela. Em PDFs com duas
        # colunas, ela pode estar longe da âncora numérica da questão; use a
        # posição real da frase e a coluna em que ela aparece.
        topo = max(0, referencia["top"] - 360)
        fundo = referencia["bottom"] + margem
    else:
        topo = ancora["top"] - margem
        fundo = seguinte["top"] - 8 if seguinte else _fim_do_conteudo(pagina, limites_x, topo)

    topo = max(0, topo)
    fundo = min(fundo, topo + 650)
    fundo = min(pagina.height, max(topo + 80, fundo))
    # Para referências "a seguir" no rodapé, a figura pode começar na página
    # seguinte. Inclua apenas seu topo, sem anexar a página inteira.
    imagem = pagina.crop((limites_x[0], topo, limites_x[1], fundo)).to_image(resolution=150).original.convert("RGB")
    if referencia and _REFERENCIA_ABAIXO.search(frase) and referencia["top"] > pagina.height * 0.72 and indice + 1 < len(pdf.pages):
        proxima_pagina = pdf.pages[indice + 1]
        limite_proximo = _limites_horizontais(proxima_pagina, ancora, duas_colunas_pdf)
        complemento = proxima_pagina.crop(
            (limite_proximo[0], 20, limite_proximo[1], min(proxima_pagina.height, 320))
        ).to_image(resolution=150).original.convert("RGB")
        from PIL import Image
        largura = max(imagem.width, complemento.width)
        combinado = Image.new("RGB", (largura, imagem.height + complemento.height), "white")
        combinado.paste(imagem, (0, 0))
        combinado.paste(complemento, (0, imagem.height))
        imagem = combinado
    return imagem


def anexar_imagens_referenciadas(caminho: str | Path, questoes: list[dict], raiz: str | Path) -> int:
    """Salva um recorte contextual para cada questão que cita uma figura."""
    caminho, raiz = Path(caminho), Path(raiz)
    alvos = []
    for questao in questoes:
        referencia = _REF_VISUAL.search(_texto_questao(questao))
        if referencia:
            alvos.append((questao, referencia.group(0)))
    if caminho.suffix.lower() != ".pdf" or not alvos:
        return 0

    digest = hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]
    destino = raiz / "data" / "questao_imagens"
    destino.mkdir(parents=True, exist_ok=True)
    salvas = 0
    with pdfplumber.open(caminho) as pdf:
        duas_colunas_pdf = _pdf_tem_duas_colunas(pdf)
        for questao, frase in alvos:
            imagem = _recortar_regiao(pdf, questao, frase, duas_colunas_pdf)
            if imagem is None:
                questao["aviso_importacao"] = " ".join(filter(None, [
                    questao.get("aviso_importacao"),
                    "A questão cita um elemento visual, mas não foi possível localizar seu recorte no PDF.",
                ]))
                continue
            numero = int(questao.get("numero") or 0)
            caminho_imagem = destino / f"{digest}_q{numero}_crop.png"
            imagem.save(caminho_imagem, optimize=True)
            questao["imagem_path"] = caminho_imagem.relative_to(raiz).as_posix()
            salvas += 1
    return salvas
