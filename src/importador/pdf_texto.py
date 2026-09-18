import logging
import re
import unicodedata

import pdfplumber
from pdfminer.pdfdocument import PDFSyntaxError



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

def _normalizar_pagina(texto: str) -> str:
    texto = _corrigir_encoding_ocr(texto)
    texto = texto.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    # Une palavras quebradas no fim da linha, sem destruir a separação de questões.
    texto = re.sub(r"(?<=\w)-\n(?=\w)", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    linhas = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or PADRAO_WATERMARK_PCI.search(linha):
            continue
        if re.fullmatch(r'(?i)(?:Área|Espaço) (?:livre|para rascunho)', linha):
            continue
        if PADRAO_TOKEN_WATERMARK.fullmatch(linha):
            continue
        linhas.append(linha)
    return "\n".join(linhas)


def _corrigir_encoding_ocr(texto: str) -> str:
    """Normaliza palavras afetadas pelo caractere de substituição do OCR."""
    for padrao, substituicao in (
        (r"l[�i]ngua", "lingua"),
        (r"inform[�a]tica", "informatica"),
        (r"racioc[�i]nio", "raciocinio"),
        (r"matem[�a]tica", "matematica"),
        (r"quest[�a]o", "questao"),
        (r"quest[�a]es", "questoes"),
    ):
        texto = re.sub(padrao, substituicao, texto, flags=re.IGNORECASE)
    return texto


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
        and not re.match(r'(?i)^(?:preencha|assinale|marque|selecione|indique)\b', linha)
    }


def _pagina_sem_texto_rotacionado(pagina):
    # Rodapés localizados na margem, identificados antes de dividir colunas.
    # Assim não sobra metade de um título anexada à última alternativa.
    faixas_rodape = []
    if hasattr(pagina, 'extract_words'):
        palavras = pagina.extract_words(x_tolerance=2, y_tolerance=3)
        for y, ws in _agrupar_palavras_por_linha(palavras):
            t = ' '.join(w['text'] for w in sorted(ws, key=lambda w:w['x0']))
            if y > pagina.height*.90 and re.search(r'(?i)\b(?:provas?\s+[IV]+\b|p[áa]gina\s+\d|www\.|pcimarkpci)', t):
                faixas_rodape.append((y-2, max(w['bottom'] for w in ws)+2))
    def legivel(obj):
        if obj.get('object_type') != 'char':
            return True
        if not obj.get('upright', True):
            return False
        if any(a <= obj.get('top', -1) <= b for a,b in faixas_rodape):
            return False
        # pdfminer pode marcar letras diagonais como upright. Marcas d'água
        # grandes e inclinadas não pertencem às linhas do corpo da prova.
        matriz = obj.get('matrix', (1, 0, 0, 1, 0, 0))
        return not (obj.get('size', 0) > 30 and
                    (abs(matriz[1]) > .1 or abs(matriz[2]) > .1))
    return pagina.filter(legivel)


def _extrair_texto_area(pagina, bbox) -> str:
    area = pagina.crop(bbox)
    return area.extract_text(x_tolerance=2, y_tolerance=3) or ""


def _extrair_texto_colunas(pagina, topo=0) -> str:
    metade = pagina.width / 2
    divisorias = [line['x0'] for line in list(pagina.lines) + list(pagina.rects)
                  if abs(line['x0'] - line['x1']) < 2
                  and abs(line['bottom'] - line['top']) > pagina.height * .45
                  and .45 * pagina.width < line['x0'] < .55 * pagina.width]
    if divisorias:
        metade = min(divisorias, key=lambda x: abs(x - metade))
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
        cabecalho_linguas = (quantidade_linguas >= 2 and len(texto) <= 100
                            and re.match(r"(?i)^l(?:í|i|�)ngua\b", texto))
        if PADRAO_SECAO_COM_CONTAGEM.search(texto) or cabecalho_linguas:
            return max(0, topo - 2)
    return None


def _parece_pagina_de_questoes(texto: str) -> bool:
    if len(re.findall(r"[a-e]\.\s*SQUARE\b", texto, re.I)) >= 3:
        return True
    if re.search(r"(?i)\bquest(?:ão|ao|�o)\s*\d{1,3}", texto):
        return True
    if re.search(r'(?i)CEBRASPE', texto) and re.search(r'(?i)\bjulgue\s+(?:os|o|cada|a)', texto) and len(PADRAO_MARCADOR_QUESTAO.findall(texto)) >= 3:
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
    # Marcadores de questões e alternativas alinhados às duas margens
    # confirmam colunas mesmo quando ambas ocupam as mesmas linhas (IESES).
    ancoras = []
    for minimo, maximo in ((0.025, 0.18), (0.48, 0.68)):
        lado = [p for p in palavras if minimo <= p["x0"] / largura_pagina <= maximo]
        questoes = sum(bool(re.fullmatch(r"\d{1,3}[.)–—-]", p.get("text", ""))) for p in lado)
        alternativas = sum(bool(re.fullmatch(r"[a-eA-E][)]", p.get("text", ""))) for p in lado)
        ancoras.append(questoes >= 1 and alternativas >= 2)
    if all(ancoras):
        return True
    nomeadas = [sum(w.get('text', '').upper() in ('QUESTÃO', 'QUESTAO')
                    and a <= w['x0']/largura_pagina <= b for w in palavras)
                for a, b in ((.02, .15), (.48, .65))]
    if min(nomeadas) >= 1:
        return True
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
    cruzadas = sum(p['x0'] < metade-3 and p.get('x1', p['x0']) > metade+3 for p in palavras)
    return (proporcao_bruta >= 0.20 and palavras_brutas_esquerda > 30 and palavras_brutas_direita > 30
            and cruzadas < 15)


def extrair_texto_pdf(caminho: str, *, usar_ocr=True) -> str:
    from .perfis.pdf_paginas import TextoExtraido, LeitorOCR, colunas_por_separadores
    paginas = []
    avisos, perfis_paginas = [], []
    leitor_ocr = LeitorOCR()
    modo_colunas = False
    with pdfplumber.open(caminho) as pdf:
        from src.importador.cebraspe_layout import extrair_layout_cebraspe
        estruturado = extrair_layout_cebraspe(pdf)
        if estruturado is not None:
            return TextoExtraido(estruturado, "pdf_recuado_contexto_v1")
        from src.importador.perfis.pdf_recuado import extrair_recuado
        estruturado = extrair_recuado(pdf)
        if estruturado is not None:
            return TextoExtraido(estruturado, "pdf_recuado_misto_v2", ["Confira tabelas e figuras na fonte; o texto pode não preservar sua disposição."])
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
                modo_colunas = True
                texto = _extrair_texto_colunas(pagina_filtrada)
            else:
                texto = texto_normal
            perfil_pagina = "pdf_duas_colunas_v1" if modo_colunas else "pdf_linear_v1"
            if not texto.strip():
                if usar_ocr:
                    texto, aviso = leitor_ocr.ler(pagina)
                    avisos.append(f"Página {numero}: {aviso}")
                    perfil_pagina = "pdf_ocr_v1"
                else:
                    avisos.append(f"Página {numero}: sem texto; OCR desativado.")
            elif not modo_colunas:
                separado = colunas_por_separadores(pagina_filtrada, topo_secao or 0)
                if separado:
                    corpo, perfil_pagina = separado
                    cabecalho = _extrair_texto_area(pagina_filtrada, (0, 0, pagina.width, topo_secao)) if topo_secao else ""
                    texto = cabecalho + "\n" + corpo
            perfis_paginas.append({"pagina": numero, "perfil": perfil_pagina})
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
    return TextoExtraido(texto_final, avisos=avisos, paginas=perfis_paginas)


