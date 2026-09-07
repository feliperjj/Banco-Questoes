import logging
import re
import pdfplumber
from pdfminer.pdfdocument import PDFSyntaxError
from src.importador.templates import selecionar_template
logger=logging.getLogger(__name__)
# Constantes calibradas para o layout CEBRASPE atual de gabarito escaneado.
OCR_CEBRASPE_RESOLUCAO = 180
OCR_CEBRASPE_CABECALHO_Y_FALLBACK = 500
OCR_CEBRASPE_ALTURA_GRADE = 430
OCR_CEBRASPE_OFFSET_GRADE_Y = 35
OCR_CEBRASPE_LIMIAR_PIXELS_ESCUROS = 180
OCR_CEBRASPE_LIMIAR_LINHA_HORIZONTAL = 0.38
OCR_CEBRASPE_LIMIAR_LINHA_VERTICAL = 0.70
OCR_CEBRASPE_LINHAS_VERTICAIS_ESPERADAS = 21
OCR_CEBRASPE_COLUNAS_RESPOSTAS = 20
OCR_CEBRASPE_LINHAS_RESPOSTAS = 4
OCR_CEBRASPE_ESPACO_LINHA_MIN = 25
OCR_CEBRASPE_ESPACO_LINHA_MAX = 48
OCR_CEBRASPE_CENTROS_Y_FALLBACK = (72, 157, 242, 326)
OCR_CEBRASPE_RECORTES_CELULA = ((15, 18), (24, 25), (25, 30))
OCR_CEBRASPE_ESCALA_RECORTE = 6
OCR_CEBRASPE_CONFIANCA_MINIMA = 0.35


from src.importador.pdf_texto import _corrigir_encoding_ocr


def _agrupar_indices_consecutivos(indices):
    grupos = []
    for indice in indices:
        if not grupos or indice > grupos[-1][-1] + 1:
            grupos.append([])
        grupos[-1].append(indice)
    return grupos


def _detectar_cabecalho_y(deteccoes):
    for caixa, texto, _ in deteccoes:
        if re.search(r"prova\s*1", str(texto), re.IGNORECASE):
            return sum(ponto[1] for ponto in caixa) / 4
    return OCR_CEBRASPE_CABECALHO_Y_FALLBACK


def _detectar_grade(imagem, cabecalho_y=None):
    import cv2

    cabecalho_y = OCR_CEBRASPE_CABECALHO_Y_FALLBACK if cabecalho_y is None else cabecalho_y
    limite_inferior = cabecalho_y + OCR_CEBRASPE_ALTURA_GRADE
    gray = cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY)
    regiao = gray[int(cabecalho_y + OCR_CEBRASPE_OFFSET_GRADE_Y):int(limite_inferior), :]
    projecao_horizontal = (regiao < OCR_CEBRASPE_LIMIAR_PIXELS_ESCUROS).sum(axis=1)
    linhas = [
        i + int(cabecalho_y + OCR_CEBRASPE_OFFSET_GRADE_Y)
        for i, valor in enumerate(projecao_horizontal)
        if valor > imagem.shape[1] * OCR_CEBRASPE_LIMIAR_LINHA_HORIZONTAL
    ]
    grupos = _agrupar_indices_consecutivos(linhas)
    linhas_grade = [sum(grupo) / len(grupo) for grupo in grupos if len(grupo) >= 1]
    centros_y = []
    for primeira, segunda in zip(linhas_grade, linhas_grade[1:]):
        if OCR_CEBRASPE_ESPACO_LINHA_MIN <= segunda - primeira <= OCR_CEBRASPE_ESPACO_LINHA_MAX:
            centros_y.append((primeira + segunda) / 2)
    centros_y = centros_y[:OCR_CEBRASPE_LINHAS_RESPOSTAS]
    if len(centros_y) < OCR_CEBRASPE_LINHAS_RESPOSTAS:
        centros_y = [cabecalho_y + valor for valor in OCR_CEBRASPE_CENTROS_Y_FALLBACK]

    # A grade tem 21 linhas verticais; detectá-las torna o OCR independente
    # da resolução exata do PDF.
    regiao_vertical = gray[int(cabecalho_y + OCR_CEBRASPE_OFFSET_GRADE_Y):int(limite_inferior), :]
    projecao_vertical = (regiao_vertical < OCR_CEBRASPE_LIMIAR_PIXELS_ESCUROS).sum(axis=0)
    linhas_x = [
        i for i, valor in enumerate(projecao_vertical)
        if valor > (limite_inferior - cabecalho_y) * OCR_CEBRASPE_LIMIAR_LINHA_VERTICAL
    ]
    grupos_x = _agrupar_indices_consecutivos(linhas_x)
    linhas_grade_x = [sum(grupo) / len(grupo) for grupo in grupos_x]
    if len(linhas_grade_x) < OCR_CEBRASPE_LINHAS_VERTICAIS_ESPERADAS:
        return centros_y, []
    linhas_grade_x = linhas_grade_x[:OCR_CEBRASPE_LINHAS_VERTICAIS_ESPERADAS]
    centros_x = [(linhas_grade_x[i] + linhas_grade_x[i + 1]) / 2 for i in range(OCR_CEBRASPE_COLUNAS_RESPOSTAS)]
    return centros_y, centros_x


def _ler_celula(imagem, centro_y, centro_x, ocr):
    import cv2

    candidatos = []
    for largura, altura in OCR_CEBRASPE_RECORTES_CELULA:
        recorte = imagem[int(centro_y - altura):int(centro_y + altura), int(centro_x - largura):int(centro_x + largura)]
        recorte = cv2.resize(recorte, None, fx=OCR_CEBRASPE_ESCALA_RECORTE, fy=OCR_CEBRASPE_ESCALA_RECORTE, interpolation=cv2.INTER_CUBIC)
        deteccoes_celula, _ = ocr(recorte)
        candidatos.extend((texto, celula[2]) for celula in (deteccoes_celula or []) if (texto := str(celula[1]).strip().upper()) in "ABCDE")
    if not candidatos:
        return None
    letra, confianca = max(candidatos, key=lambda item: item[1])
    if confianca >= OCR_CEBRASPE_CONFIANCA_MINIMA:
        return letra
    return None


def _extrair_pares_ocr(deteccoes) -> dict[int, str]:
    """Interpreta texto OCR simples quando a grade não foi detectada."""
    if not deteccoes:
        return {}
    linhas = []
    for caixa, texto, confianca in deteccoes:
        texto = str(texto).strip().upper()
        if not texto or confianca < OCR_CEBRASPE_CONFIANCA_MINIMA:
            continue
        topo = sum(ponto[1] for ponto in caixa) / 4
        linha = next((item for item in linhas if abs(item[0] - topo) <= 10), None)
        if linha is None:
            linha = [topo, []]
            linhas.append(linha)
        linha[1].append((sum(ponto[0] for ponto in caixa) / 4, texto))
    resultado = {}
    for _, palavras in sorted(linhas, key=lambda item: item[0]):
        texto = " ".join(valor for _, valor in sorted(palavras))
        for numero, resposta in re.findall(r"\b(\d{1,3})\s*[-–:.)]?\s*([A-E])\b", texto):
            resultado[int(numero)] = resposta
    return resultado


def _extrair_gabaritos_ocr(
    caminho: str,
    cargo: str | None = None,
    indices_paginas: list[int] | None = None,
) -> dict[int, str]:
    """Lê tabelas de gabarito escaneadas usando OCR somente no ambiente Python."""
    try:
        import cv2
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        logger.warning("OCR não disponível no ambiente Python")
        return {}

    try:
        ocr = RapidOCR()
        resultado = {}
        with pdfplumber.open(caminho) as pdf:
            paginas = indices_paginas if indices_paginas is not None else list(range(len(pdf.pages)))
            for numero_pagina in paginas:
                pagina = pdf.pages[numero_pagina]
                texto_pagina = pagina.extract_text() or ""
                template = selecionar_template(caminho, texto_pagina)
                imagem = np.array(pagina.to_image(resolution=template.resolucao).original.convert("RGB"))
                deteccoes, _ = ocr(imagem)
                if not deteccoes:
                    continue
                if template.tipo != "grade":
                    for numero, resposta in _extrair_pares_ocr(deteccoes).items():
                        resultado.setdefault(numero, resposta)
                    continue
                cabecalho_y = _detectar_cabecalho_y(deteccoes)
                centros_y, centros_x = _detectar_grade(imagem, cabecalho_y)
                if centros_x:
                    offset = max(resultado, default=0)
                    for linha, centro_y in enumerate(centros_y):
                        for coluna, centro_x in enumerate(centros_x):
                            letra = _ler_celula(imagem, centro_y, centro_x, ocr)
                            if letra is not None:
                                resultado.setdefault(offset + linha * template.colunas + coluna + 1, letra)
                for numero, resposta in _extrair_pares_ocr(deteccoes).items():
                    resultado.setdefault(numero, resposta)
        logger.info("OCR de gabarito: %s itens reconhecidos", len(resultado))
        return resultado
    except (ImportError, RuntimeError, PDFSyntaxError):
        logger.exception("Falha ao executar OCR do gabarito %s", caminho)
        return {}


