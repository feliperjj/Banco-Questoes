import logging
import os
import re
import unicodedata

import docx
import pdfplumber

from src.importador.templates import selecionar_template


logger = logging.getLogger(__name__)


PADRAO_WATERMARK_PCI = re.compile(r"\bpcimarkpci\b", re.IGNORECASE)
PADRAO_TOKEN_WATERMARK = re.compile(r"^[A-Za-z0-9+/=:]{40,}$")
PADRAO_SECAO_CONTEUDO = re.compile(
    r"(?i)(l(?:í|i|�)ngua|conhecimentos|direito|inform(?:á|a|�)tica|"
    r"racioc(?:í|i|�)nio|matem(?:á|a|�)tica|contabilidade|auditoria|"
    r"legisla|atualidades)"
)
PADRAO_SECAO_COM_CONTAGEM = re.compile(r"\|\s*\d+\s*quest(?:ão|ões|ao|oes|�o|�es)", re.IGNORECASE)
PADRAO_MARCADOR_QUESTAO = re.compile(r"(?im)^\s*(?:quest(?:ão|ao|�o)\s*)?\d{1,3}(?:[.\-):]\s*|\s+)")
PADRAO_ALTERNATIVA = re.compile(r"(?im)^\s*\(?[A-Ea-e]\)?[.\-):]\s+")

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


def _normalizar_pagina(texto: str) -> str:
    texto = texto.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    # Une palavras quebradas no fim da linha, sem destruir a separação de questões.
    texto = re.sub(r"(?<=\w)-\n(?=\w)", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    linhas = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or PADRAO_WATERMARK_PCI.search(linha):
            continue
        if PADRAO_TOKEN_WATERMARK.fullmatch(linha):
            continue
        linhas.append(linha)
    return "\n".join(linhas)


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


def _pagina_sem_texto_rotacionado(pagina):
    return pagina.filter(lambda obj: obj.get("object_type") != "char" or obj.get("upright", True))


def _extrair_texto_area(pagina, bbox) -> str:
    area = pagina.crop(bbox)
    return area.extract_text(x_tolerance=2, y_tolerance=3) or ""


def _extrair_texto_colunas(pagina, topo=0) -> str:
    metade = pagina.width / 2
    partes = [
        _extrair_texto_area(pagina, (0, topo, metade, pagina.height)),
        _extrair_texto_area(pagina, (metade, topo, pagina.width, pagina.height)),
    ]
    return "\n".join(parte for parte in partes if parte)


def _agrupar_palavras_por_linha(palavras):
    linhas = []
    for palavra in sorted(palavras, key=lambda item: (item["top"], item["x0"])):
        if not linhas or abs(palavra["top"] - linhas[-1][0]) > 4:
            linhas.append([palavra["top"], []])
        linhas[-1][1].append(palavra)
    return linhas


def _topo_primeira_secao(palavras):
    for topo, linha_palavras in _agrupar_palavras_por_linha(palavras):
        texto = " ".join(palavra["text"] for palavra in sorted(linha_palavras, key=lambda item: item["x0"]))
        quantidade_linguas = len(re.findall(r"l(?:í|i|�)ngua", texto, re.IGNORECASE))
        if PADRAO_SECAO_COM_CONTAGEM.search(texto) or quantidade_linguas >= 2:
            return max(0, topo - 2)
    return None


def _parece_pagina_de_questoes(texto: str) -> bool:
    if re.search(r"(?i)\bquest(?:ão|ao|�o)\s*\d{1,3}", texto):
        return True
    return len(PADRAO_MARCADOR_QUESTAO.findall(texto)) >= 2 and len(PADRAO_ALTERNATIVA.findall(texto)) >= 2


def _tem_duas_colunas(palavras, largura_pagina, topo=0) -> bool:
    """Retorna se há duas colunas reais abaixo de ``topo``.

    Contar palavras por metade da página não é suficiente: uma linha de
    instruções em largura total naturalmente põe palavras nos dois lados e
    pode ser confundida com uma página em colunas. Consideramos somente
    linhas cujo conteúdo inteiro fica dentro de uma metade; isso também
    permite que instruções em uma coluna e questões em duas colunas convivam
    na mesma página.
    """
    palavras = [palavra for palavra in palavras if palavra["top"] >= topo]
    if len(palavras) < 60:
        return False
    metade = largura_pagina / 2
    palavras_brutas_esquerda = sum(1 for palavra in palavras if palavra["x0"] < metade)
    palavras_brutas_direita = len(palavras) - palavras_brutas_esquerda
    proporcao_bruta = min(palavras_brutas_esquerda, palavras_brutas_direita) / len(palavras)
    linhas = _agrupar_palavras_por_linha(palavras)
    linhas_esquerda = 0
    linhas_direita = 0
    palavras_esquerda = 0
    palavras_direita = 0
    lacunas_centrais = []
    for _, linha in linhas:
        palavras_lado_esquerdo = [palavra for palavra in linha if palavra["x0"] < metade]
        palavras_lado_direito = [palavra for palavra in linha if palavra["x0"] >= metade]
        if palavras_lado_esquerdo and palavras_lado_direito:
            fim_esquerda = max(palavra.get("x1", palavra["x0"]) for palavra in palavras_lado_esquerdo)
            inicio_direita = min(palavra["x0"] for palavra in palavras_lado_direito)
            lacunas_centrais.append(inicio_direita - fim_esquerda)
        minimo = min(palavra["x0"] for palavra in linha)
        maximo = max(palavra.get("x1", palavra["x0"]) for palavra in linha)
        if maximo <= metade:
            linhas_esquerda += 1
            palavras_esquerda += len(linha)
        elif minimo >= metade:
            linhas_direita += 1
            palavras_direita += len(linha)
        elif palavras_lado_esquerdo and palavras_lado_direito:
            # Colunas sobrepostas verticalmente são uma linha de cada coluna;
            # contabiliza-as dos dois lados somente quando há um vão central
            # claro entre elas. Linhas corridas não passam neste teste.
            if lacunas_centrais[-1] >= largura_pagina * 0.08:
                linhas_esquerda += 1
                linhas_direita += 1
                palavras_esquerda += len(palavras_lado_esquerdo)
                palavras_direita += len(palavras_lado_direito)

    total = palavras_esquerda + palavras_direita
    if not total or linhas_esquerda < 3 or linhas_direita < 3:
        return False
    detectou_por_linhas = (
        (not lacunas_centrais or sorted(lacunas_centrais)[len(lacunas_centrais) // 2] >= largura_pagina * 0.08)
        and
        palavras_esquerda > 20
        and palavras_direita > 20
        and min(palavras_esquerda, palavras_direita) / total >= 0.30
    )
    if detectou_por_linhas:
        return True

    # Alguns cadernos FGV/Cesgranrio usam colunas assimétricas ou quebram a
    # mesma linha das duas colunas no mesmo y. Nesses casos a análise por
    # linhas é conservadora demais, mas a distribuição bruta ainda é um
    # sinal confiável. O limite de 20% preserva páginas essencialmente de uma
    # coluna, como a última página curta do caderno TRANSPETRO.
    return proporcao_bruta >= 0.20 and palavras_brutas_esquerda > 30 and palavras_brutas_direita > 30


def extrair_texto_pdf(caminho: str) -> str:
    paginas = []
    modo_colunas = False
    with pdfplumber.open(caminho) as pdf:
        for numero, pagina in enumerate(pdf.pages, start=1):
            pagina_filtrada = _pagina_sem_texto_rotacionado(pagina)
            palavras = pagina_filtrada.extract_words(x_tolerance=2, y_tolerance=3, extra_attrs=["upright"])
            texto_normal = pagina_filtrada.extract_text(x_tolerance=2, y_tolerance=3) or ""
            topo_secao = _topo_primeira_secao(palavras)
            modo_colunas_anterior = modo_colunas
            if topo_secao is not None:
                modo_colunas = True
                if modo_colunas_anterior and _tem_duas_colunas(palavras, pagina.width):
                    texto = _extrair_texto_colunas(pagina_filtrada)
                elif _tem_duas_colunas(palavras, pagina.width, topo_secao):
                    texto_topo = _extrair_texto_area(pagina_filtrada, (0, 0, pagina.width, topo_secao))
                    texto_corpo = _extrair_texto_colunas(pagina_filtrada, topo_secao)
                    texto = "\n".join(parte for parte in (texto_topo, texto_corpo) if parte)
                else:
                    texto = texto_normal
            elif (modo_colunas or _parece_pagina_de_questoes(texto_normal)) and _tem_duas_colunas(palavras, pagina.width):
                texto = _extrair_texto_colunas(pagina_filtrada)
            else:
                texto = texto_normal
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


def _texto_comparavel(texto: str) -> str:
    """Normaliza acentos e ruído de OCR para comparar cabeçalhos de PDFs."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    texto = texto.replace("�", "")
    return re.sub(r"\s+", " ", texto).strip().casefold()


def _extrair_gabaritos_tabelas(pagina) -> dict[int, str]:
    """Extrai pares de células sem confundir códigos ou anos com questões."""
    resultado = {}
    try:
        tabelas = pagina.extract_tables() or []
    except Exception:
        logger.exception("Falha ao extrair tabela de gabarito")
        return resultado
    for tabela in tabelas:
        for linha in tabela:
            celulas = [re.sub(r"\s+", " ", str(c or "")).strip().upper() for c in linha]
            for indice, celula in enumerate(celulas):
                numero = re.fullmatch(r"([1-9]\d{0,2})", celula)
                if not numero or int(numero.group(1)) > 200:
                    continue
                for resposta in celulas[indice + 1:indice + 3]:
                    token = re.fullmatch(r"([A-E]|CERTO|ERRADO|X)", resposta)
                    if token:
                        resultado.setdefault(int(numero.group(1)), token.group(1))
                        break
    return resultado


def extrair_gabaritos_pdf(
    caminho: str,
    codigo_prova: str | None = None,
    cargo: str | None = None,
    *,
    usar_ocr: bool = True,
    numeros_esperados: set[int] | None = None,
) -> dict[int, str]:
    """Extrai o mapa questão -> resposta, respeitando cargo/código quando informado.

    PDFs de concursos frequentemente juntam vários cargos no mesmo arquivo de
    gabarito. ``cargo`` funciona como seletor de contexto e impede que a
    resposta de outro cargo sobrescreva a resposta do caderno importado.
    ``codigo_prova`` mantém compatibilidade com o fluxo da UI.
    """
    gabaritos = {}
    paginas_relevantes = []
    cargo_ativo = not bool(cargo)
    codigo_prova = (codigo_prova or "").lower().replace("-", "_")
    codigo_ativo = not bool(codigo_prova)
    cargo_normalizado = _texto_comparavel(cargo)

    def linhas_do_cargo(linhas):
        if not cargo_normalizado:
            return linhas
        comparaveis = [_texto_comparavel(linha) for linha in linhas]
        inicio = next((i for i, linha in enumerate(comparaveis) if cargo_normalizado in linha), None)
        if inicio is None:
            return linhas
        fim = len(linhas)
        # Um mesmo PDF traz vários cargos em sequência. Disciplinas não são
        # cabeçalhos de cargo e, por isso, não encerram o bloco.
        for i in range(inicio + 1, len(linhas)):
            linha = comparaveis[i]
            if re.search(r"\b(?:prova\s+tipo|ibfc[_ ]\d+|cargo\s*[:\-]|agente|analista|administrador|auditor|assistente)\b", linha):
                if not re.search(r"\b(?:lingua|raciocinio|nocoes|principios|conhecimentos|direito|informatica)\b", linha):
                    fim = i
                    break
        return linhas[inicio:fim]
    with pdfplumber.open(caminho) as pdf:
        for numero_pagina, pagina in enumerate(pdf.pages):
            texto = pagina.extract_text() or ""
            texto_normalizado = texto.lower().replace("-", "_")
            pagina_especifica = not codigo_prova or codigo_prova in texto_normalizado
            pagina_comum_superior = "dpf14_cbns01" in texto_normalizado
            if pagina_especifica:
                codigo_ativo = True
            outro_codigo = re.search(r"c[oó]digo\s*[:\-]?\s*([a-z0-9_]+)", texto_normalizado)
            if codigo_ativo and outro_codigo and codigo_prova and codigo_prova not in outro_codigo.group(1):
                codigo_ativo = False
                continue
            if codigo_prova and not codigo_ativo and not pagina_comum_superior:
                continue
            linhas = [re.sub(r"\s+", " ", linha).strip() for linha in texto.splitlines()]
            texto_pagina_normalizado = re.sub(r"\s+", " ", texto).casefold()
            if cargo_normalizado and cargo_normalizado not in texto_pagina_normalizado and not cargo_ativo:
                # Não agregue uma tabela de outro cargo. O comportamento
                # anterior aceitava qualquer página com pares numéricos e
                # sobrescrevia respostas do bloco selecionado.
                continue
            if cargo_normalizado in texto_pagina_normalizado:
                cargo_ativo = True
            # Um cabeçalho inequívoco de outro cargo encerra o bloco atual.
            if cargo_ativo and cargo_normalizado and re.search(r"\b(?:cargo|agente|analista|administrador|auditor)\b", texto_pagina_normalizado) and cargo_normalizado not in texto_pagina_normalizado:
                cargo_ativo = False
                continue
            paginas_relevantes.append(numero_pagina)
            linhas = linhas_do_cargo(linhas)
            pagina_multiprovas = bool(re.search(r"PROVA\s+1", texto, re.IGNORECASE) and re.search(r"PROVA\s+2", texto, re.IGNORECASE))
            pares_na_mesma_linha = [
                re.findall(r"\b(\d{1,3})\s*(?:[-–:.)]\s*)?([A-EX])\b", linha.upper())
                for linha in linhas
            ]
            if pagina_multiprovas:
                # O gabarito do nível superior imprime quatro provas lado a
                # lado. Cada linha traz dois pares por prova (21/46, 22/47,
                # ...). Para este caderno, PROVA 1 é Administração e é a
                # coluna usada quando nenhum código específico foi informado.
                coluna = 0
                if codigo_prova:
                    encontrado = re.search(r"(?:PROVA\s*)?(\d+)", codigo_prova, re.IGNORECASE)
                    if encontrado:
                        coluna = max(0, min(int(encontrado.group(1)) - 1, 3))
                for pares in pares_na_mesma_linha:
                    inicio = coluna * 2
                    for numero, resposta in pares[inicio:inicio + 2]:
                        gabaritos[int(numero)] = resposta
                if any(pares_na_mesma_linha):
                    continue

            # Alguns gabaritos simples colocam todos os pares na mesma linha,
            # por exemplo: "1 - E 2 - B 3 - B ...".
            encontrou_pares = False
            for pares in pares_na_mesma_linha:
                for numero, resposta in pares:
                    gabaritos[int(numero)] = resposta
                    encontrou_pares = True
            if encontrou_pares:
                continue

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
            cargo_selecionado = not codigo_prova or bool(cargo_normalizado)
            for indice, linha in enumerate(linhas):
                if re.search(r"c[oó]digo\s*\d{3}", linha, re.IGNORECASE):
                    codigo = re.search(r"c[oó]digo\s*(\d{3})", linha, re.IGNORECASE).group(1)
                    cargo_selecionado = not codigo_prova or codigo in codigo_prova
                    continue
                numeros = re.findall(r"\d{1,3}", linha) if cargo_selecionado else []
                if not numeros or indice + 1 >= len(linhas):
                    continue
                proxima_linha = indice + 1
                # Alguns gabaritos inserem a disciplina entre a linha dos
                # números e a linha das respostas (1 2 3 / Português / D C B).
                while proxima_linha < len(linhas) and proxima_linha <= indice + 2:
                    respostas_linha = re.findall(r"\b[A-EX]\b", linhas[proxima_linha].upper())
                    if len(respostas_linha) == len(numeros):
                        break
                    proxima_linha += 1
                if len(respostas_linha) != len(numeros):
                    continue
                for numero, resposta in zip(numeros, respostas_linha):
                    gabaritos[int(numero)] = resposta
            if len(gabaritos) >= 120 and codigo_prova:
                break
    logger.info("Gabarito extraído: %s itens de %s", len(gabaritos), caminho)
    # Tabelas complementam o texto; nunca substituem uma resposta textual.
    with pdfplumber.open(caminho) as pdf:
        for numero_pagina in paginas_relevantes:
            for numero, resposta in _extrair_gabaritos_tabelas(pdf.pages[numero_pagina]).items():
                gabaritos.setdefault(numero, resposta)
    faltantes = set(numeros_esperados or ()) - set(gabaritos)
    # Sem números esperados, OCR é fallback apenas para extração vazia. Isso
    # evita completar um gabarito curto e íntegro com ruído de outras páginas.
    precisa_ocr = usar_ocr and (not gabaritos or bool(faltantes))
    if precisa_ocr:
        for numero, resposta in _extrair_gabaritos_ocr(
            caminho, cargo=cargo, indices_paginas=paginas_relevantes,
        ).items():
            if numeros_esperados is not None and numero not in numeros_esperados:
                continue
            gabaritos.setdefault(numero, resposta)
    return gabaritos


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
