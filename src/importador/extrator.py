import logging
import os
import re

import docx
import pdfplumber


logger = logging.getLogger(__name__)


def _normalizar_pagina(texto: str) -> str:
    texto = texto.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    # Une palavras quebradas no fim da linha, sem destruir a separação de questões.
    texto = re.sub(r"(?<=\w)-\n(?=\w)", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    return "\n".join(linha.strip() for linha in texto.splitlines() if linha.strip())


def _linhas_repetidas(paginas: list[str]) -> set[str]:
    if len(paginas) < 2:
        return set()
    ocorrencias = {}
    for pagina in paginas:
        for linha in set(pagina.splitlines()):
            if len(linha) <= 120:
                ocorrencias[linha] = ocorrencias.get(linha, 0) + 1
    limite = max(2, int(len(paginas) * 0.6))
    # Números isolados podem ser marcadores legítimos de questões em provas FGV.
    # Não os trate como cabeçalho/rodapé repetido.
    return {
        linha for linha, quantidade in ocorrencias.items()
        if quantidade >= limite and not re.fullmatch(r"\d{1,3}", linha)
    }


def extrair_texto_pdf(caminho: str) -> str:
    paginas = []
    with pdfplumber.open(caminho) as pdf:
        for numero, pagina in enumerate(pdf.pages, start=1):
            palavras = pagina.extract_words(x_tolerance=2, y_tolerance=3)
            metade = pagina.width / 2
            esquerda = [palavra for palavra in palavras if palavra["x0"] < metade]
            direita = [palavra for palavra in palavras if palavra["x0"] >= metade]
            # Provas CESPE costumam ter duas colunas. A ordem visual correta é
            # coluna esquerda inteira e, depois, coluna direita inteira.
            if len(esquerda) > 30 and len(direita) > 30:
                caixa_esquerda = pagina.crop((0, 0, metade, pagina.height))
                caixa_direita = pagina.crop((metade, 0, pagina.width, pagina.height))
                partes = [
                    caixa_esquerda.extract_text(x_tolerance=2, y_tolerance=3) or "",
                    caixa_direita.extract_text(x_tolerance=2, y_tolerance=3) or "",
                ]
                texto = "\n".join(parte for parte in partes if parte)
            else:
                texto = pagina.extract_text(x_tolerance=2, y_tolerance=3)
            if texto:
                paginas.append(_normalizar_pagina(texto))
            else:
                logger.warning("Página %s sem texto extraível no arquivo %s", numero, caminho)

    repetidas = _linhas_repetidas(paginas)
    resultado = []
    for pagina in paginas:
        linhas = [
            linha for linha in pagina.splitlines()
            if linha not in repetidas and not re.fullmatch(r"página\s+\d+(?:\s+de\s+\d+)?", linha, re.IGNORECASE)
        ]
        resultado.append("\n".join(linhas))
    texto_final = "\n".join(parte for parte in resultado if parte).strip()
    logger.info("PDF extraído: %s caracteres de %s páginas", len(texto_final), len(paginas))
    return texto_final


def extrair_texto_docx(caminho: str) -> str:
    documento = docx.Document(caminho)
    paragrafos = [paragrafo.text.strip() for paragrafo in documento.paragraphs if paragrafo.text.strip()]
    texto = "\n".join(paragrafos)
    logger.info("DOCX extraído: %s caracteres", len(texto))
    return texto


def extrair_gabaritos_pdf(caminho: str, codigo_prova: str | None = None) -> dict[int, str]:
    """Extrai o mapa questão -> alternativa de tabelas de gabarito."""
    gabaritos = {}
    codigo_prova = (codigo_prova or "").lower().replace("-", "_")
    with pdfplumber.open(caminho) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            texto_normalizado = texto.lower().replace("-", "_")
            pagina_especifica = not codigo_prova or codigo_prova in texto_normalizado
            pagina_comum_superior = "dpf14_cbns01" in texto_normalizado
            if codigo_prova and not pagina_especifica and not pagina_comum_superior:
                continue
            linhas = [re.sub(r"\s+", " ", linha).strip() for linha in texto.splitlines()]
            for indice, linha in enumerate(linhas):
                if not re.match(r"^Item\s+", linha, re.IGNORECASE):
                    continue
                itens = [int(valor) for valor in re.findall(r"\d+", linha)]
                if indice + 1 >= len(linhas):
                    continue
                respostas = re.findall(r"\b[CE]\b", linhas[indice + 1].upper())
                for item, resposta in zip(itens, respostas):
                    if item:
                        gabaritos[item] = "Certo" if resposta == "C" else "Errado"
            # Gabaritos de múltipla escolha normalmente vêm em duas linhas:
            # "1 2 3 ..." e, logo abaixo, "A C B ...". O cabeçalho do cargo
            # permite ignorar os demais gabaritos existentes no mesmo PDF.
            cargo_selecionado = not codigo_prova
            for indice, linha in enumerate(linhas):
                if re.search(r"c[oó]digo\s*\d{3}", linha, re.IGNORECASE):
                    codigo = re.search(r"c[oó]digo\s*(\d{3})", linha, re.IGNORECASE).group(1)
                    cargo_selecionado = not codigo_prova or codigo in codigo_prova
                    continue
                numeros = re.findall(r"\d{1,3}", linha) if cargo_selecionado else []
                if not numeros or indice + 1 >= len(linhas):
                    continue
                respostas_linha = re.findall(r"\b[A-E]\b", linhas[indice + 1].upper())
                if len(respostas_linha) != len(numeros):
                    continue
                for numero, resposta in zip(numeros, respostas_linha):
                    gabaritos[int(numero)] = resposta
            if len(gabaritos) >= 120 and codigo_prova:
                break
    logger.info("Gabarito extraído: %s itens de %s", len(gabaritos), caminho)
    if not gabaritos:
        gabaritos = _extrair_gabaritos_ocr(caminho)
    return gabaritos


def _extrair_gabaritos_ocr(caminho: str) -> dict[int, str]:
    """Lê tabelas de gabarito escaneadas usando OCR somente no ambiente Python."""
    try:
        import cv2
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        logger.warning("OCR não disponível no ambiente Python")
        return {}

    try:
        with pdfplumber.open(caminho) as pdf:
            pagina = pdf.pages[0]
            imagem = np.array(pagina.to_image(resolution=180).original.convert("RGB"))
        ocr = RapidOCR()
        deteccoes, _ = ocr(imagem)
        if not deteccoes:
            return {}

        # Localiza o cabeçalho da primeira prova e usa a geometria da grade,
        # em vez de depender do texto ou da banca do documento.
        cabecalho_y = None
        for caixa, texto, _ in deteccoes:
            if re.search(r"prova\s*1", str(texto), re.IGNORECASE):
                cabecalho_y = sum(ponto[1] for ponto in caixa) / 4
                break
        if cabecalho_y is None:
            cabecalho_y = 500

        limite_inferior = cabecalho_y + 430
        gray = cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY)
        regiao = gray[int(cabecalho_y + 35):int(limite_inferior), :]
        projecao_horizontal = (regiao < 180).sum(axis=1)
        linhas = [i + int(cabecalho_y + 35) for i, valor in enumerate(projecao_horizontal) if valor > imagem.shape[1] * 0.38]
        grupos = []
        for linha in linhas:
            if not grupos or linha > grupos[-1][-1] + 1:
                grupos.append([])
            grupos[-1].append(linha)
        linhas_grade = [sum(grupo) / len(grupo) for grupo in grupos if len(grupo) >= 1]
        centros_y = []
        for primeira, segunda in zip(linhas_grade, linhas_grade[1:]):
            if 25 <= segunda - primeira <= 48:
                centros_y.append((primeira + segunda) / 2)
        centros_y = centros_y[:4]
        if len(centros_y) < 4:
            centros_y = [cabecalho_y + valor for valor in (72, 157, 242, 326)]

        # A grade tem 21 linhas verticais; detectá-las torna o OCR independente
        # da resolução exata do PDF.
        regiao_vertical = gray[int(cabecalho_y + 35):int(limite_inferior), :]
        projecao_vertical = (regiao_vertical < 180).sum(axis=0)
        linhas_x = [i for i, valor in enumerate(projecao_vertical) if valor > (limite_inferior - cabecalho_y) * 0.70]
        grupos_x = []
        for linha in linhas_x:
            if not grupos_x or linha > grupos_x[-1][-1] + 1:
                grupos_x.append([])
            grupos_x[-1].append(linha)
        linhas_grade_x = [sum(grupo) / len(grupo) for grupo in grupos_x]
        if len(linhas_grade_x) < 21:
            return {}
        linhas_grade_x = linhas_grade_x[:21]
        centros_x = [(linhas_grade_x[i] + linhas_grade_x[i + 1]) / 2 for i in range(20)]

        resultado = {}
        for linha, centro_y in enumerate(centros_y):
            for coluna, centro_x in enumerate(centros_x):
                candidatos = []
                for largura, altura in ((15, 18), (24, 25), (25, 30)):
                    recorte = imagem[int(centro_y - altura):int(centro_y + altura), int(centro_x - largura):int(centro_x + largura)]
                    recorte = cv2.resize(recorte, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
                    deteccoes_celula, _ = ocr(recorte)
                    candidatos.extend((str(celula[1]).strip().upper(), celula[2]) for celula in (deteccoes_celula or []) if str(celula[1]).strip().upper() in "ABCDE")
                if candidatos:
                    letra, confianca = max(candidatos, key=lambda item: item[1])
                    if confianca >= 0.35:
                        resultado[linha * 20 + coluna + 1] = letra
        logger.info("OCR de gabarito: %s itens reconhecidos", len(resultado))
        return resultado
    except Exception:
        logger.exception("Falha ao executar OCR do gabarito %s", caminho)
        return {}


def extrair_texto(caminho: str) -> str:
    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".pdf":
        return extrair_texto_pdf(caminho)
    if ext == ".docx":
        return extrair_texto_docx(caminho)
    raise ValueError(f"Formato não suportado: {ext}. Use PDF ou DOCX.")
