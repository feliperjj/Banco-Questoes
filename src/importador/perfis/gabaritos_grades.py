from .gabaritos_contexto import _texto_comparavel
"""Grades de gabarito: cargo, tipo, seções e tabelas de células."""
import re
import logging
from pdfminer.pdfdocument import PDFSyntaxError
logger = logging.getLogger(__name__)

def _extrair_gabaritos_tabelas(pagina) -> dict[int, str]:
    """Extrai pares de células sem confundir códigos ou anos com questões."""
    resultado = {}
    try:
        tabelas = pagina.extract_tables() or []
    except (PDFSyntaxError, ValueError, TypeError, AttributeError):
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


def _extrair_grade_identificada(pagina, texto, codigo_prova, cargo):
    """Grades com seleção explícita: coluna de tipo ou linha exata de cargo.

    None indica outro layout; {} indica grade reconhecida sem seleção segura.
    """
    ids = set(re.findall(r'(?i)\bPROVA\s+(\d{1,2})\b', texto))
    if len(ids) >= 2:
        pedido = re.fullmatch(r'(?i)(?:PROVA\s*)?(\d{1,2})', (codigo_prova or '').strip())
        if not pedido or pedido.group(1) not in ids or pagina is None:
            return {}
        words = pagina.extract_words(x_tolerance=2, y_tolerance=3)
        cabecalhos = []
        for w in words:
            if w['text'].upper() != 'PROVA':
                continue
            numeros = [n for n in words if re.fullmatch(r'\d{1,2}', n['text'])
                       and abs(n['top']-w['top']) < 4 and 0 <= n['x0']-w['x1'] < 35]
            if len(numeros) == 1:
                cabecalhos.append((w['x0'], numeros[0]['text']))
        ordem = [n for _,n in sorted(cabecalhos)]
        if len(ordem) != len(ids) or set(ordem) != ids:
            return {}
        coluna = ordem.index(pedido.group(1))
        resultado = {}
        for linha in texto.splitlines():
            pares = re.findall(r'\b(\d{1,3})\s*[-–:]\s*([A-EX])\b', linha, re.I)
            if len(pares) == len(ordem)*2:
                for n,r in pares[coluna*2:coluna*2+2]:
                    resultado[int(n)] = r.upper()
        return resultado
    secoes = list(re.finditer(r'(?im)^Provas?\s+[IVX]+(?:\s+e\s+[IVX]+)*\s*$', texto))
    if len(secoes) >= 2:
        selecao = _texto_comparavel(codigo_prova or cargo or '')
        for i, secao in enumerate(secoes):
            if _texto_comparavel(secao.group(0)) != selecao:
                continue
            fim = secoes[i + 1].start() if i + 1 < len(secoes) else len(texto)
            bloco = texto[secao.end():fim]
            return {int(n): r.upper() for n, r in re.findall(r'\b(\d{1,3})\s*[-–]\s*([A-EX])\b', bloco, re.I)}
        return {}
    if re.search(r"(?im)^Qst\s+T1\s+T2\s+T3\s+T4\s*$", texto):
        tipo = re.fullmatch(r"(?:T|TIPO\s*|PROVA\s*)([1-4])", (codigo_prova or "").upper())
        if not tipo or not cargo or _texto_comparavel(cargo) not in _texto_comparavel(texto):
            return {}
        coluna = int(tipo.group(1))
        return {int(m.group(1)): m.group(coluna + 1) for m in re.finditer(
            r"(?im)^\s*(\d{1,3})\s+([A-EX])\s+([A-EX])\s+([A-EX])\s+([A-EX])\s*$", texto)}
    if not re.search(r"(?im)^CARGO(?:\s+\d{1,3}){3,}\s*$", texto):
        return None
    if not cargo:
        return {}
    for tabela in pagina.extract_tables() or []:
        cabecalho = next((linha for linha in tabela if linha and str(linha[0]).strip() == "CARGO"), None)
        if cabecalho is None:
            continue
        numeros = [re.sub(r"[^0-9]", "", str(c or "")) for c in cabecalho[1:]]
        if not all(n for n in numeros):
            continue
        numeros = [int(n) for n in numeros]
        if len(set(numeros)) != len(numeros) or any(n < 1 or n > 200 for n in numeros):
            continue
        linhas = [linha for linha in tabela if linha and _texto_comparavel(linha[0]) == _texto_comparavel(cargo)]
        if len(linhas) != 1 or len(linhas[0]) != len(cabecalho):
            continue
        respostas = [str(c or "").strip().upper() for c in linhas[0][1:]]
        return {n: r for n, r in zip(numeros, respostas) if re.fullmatch(r"[A-EX]", r)}
    return {}


