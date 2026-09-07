"""Perfis textuais de gabarito, independentes da leitura PDF."""
import re
import logging
logger=logging.getLogger(__name__)

def _extrair_pares_mesma_linha(linhas: list[str]) -> dict[int, str]:
    from .gabaritos_resultado import MapaGabarito
    resultado = MapaGabarito()
    padrao = re.compile(r"\b0*([1-9]\d{0,2})\s*(?:[-–:.)]\s*)?([A-EX])\b")
    for linha in linhas:
        linha = re.sub(r"(?i)^(?:quest(?:ão|ao)|item|gabarito)\s*:?\s*", "", linha.strip()).upper()
        pares = padrao.findall(linha)
        resto = padrao.sub('', linha)
        resto = re.sub(r'\b\d{1,3}\s*[:.)]\s*[*?]', '', resto)
        # Datas, intervalos (1 a 28), títulos e texto corrido não são respostas.
        if not pares or re.search(r'[A-Z0-9]', resto):
            continue
        for numero, resposta in pares:
            resultado.incorporar({int(numero): resposta})
    return resultado


def _extrair_itens_certo_errado(linhas: list[str]) -> dict[int, str]:
    resultado = {}
    for indice, linha in enumerate(linhas):
        if not re.match(r"^Item\s+", linha, re.IGNORECASE) or indice + 1 >= len(linhas):
            continue
        itens = [int(valor) for valor in re.findall(r"\d+", linha)]
        respostas = re.findall(r"\b[CEX0]\b", linhas[indice + 1].upper())
        if len(itens) != len(respostas):
            logger.warning('Linha de gabarito com quantidades divergentes; associação ignorada')
            continue
        for item, resposta in zip(itens, respostas):
            if item:
                if resposta in {'C', 'E', 'X'}:
                    resultado[item] = {'C': 'Certo', 'E': 'Errado', 'X': 'Anulada'}[resposta]
    return resultado


def _extrair_duas_linhas(linhas: list[str], codigo_prova: str, cargo_normalizado: str) -> dict[int, str]:
    resultado = {}
    cargo_selecionado = not codigo_prova or bool(cargo_normalizado)
    for indice, linha in enumerate(linhas):
        codigo_match = re.search(r"c[oó]digo\s*\d{3}", linha, re.IGNORECASE)
        if codigo_match:
            codigo = re.search(r"c[oó]digo\s*(\d{3})", linha, re.IGNORECASE).group(1)
            cargo_selecionado = not codigo_prova or codigo in codigo_prova
            continue
        numeros = re.findall(r"\d{1,3}", linha) if cargo_selecionado and re.fullmatch(r"(?i)(?:(?:Item|Questões|Questoes)\s+)?\d{1,3}(?:\s+\d{1,3})*", linha.strip()) else []
        if not numeros or indice + 1 >= len(linhas):
            continue
        proxima_linha = indice + 1
        respostas_linha = []
        while proxima_linha < len(linhas) and proxima_linha <= indice + 2:
            respostas_linha = re.findall(r"\b[A-EX]\b", linhas[proxima_linha].upper())
            if len(respostas_linha) == len(numeros):
                break
            proxima_linha += 1
        if len(respostas_linha) != len(numeros):
            continue
        for numero, resposta in zip(numeros, respostas_linha):
            resultado[int(numero)] = resposta
    return resultado


class ExtratorBanca:
    def extrair(self, linhas: list[str]) -> dict[int, str]:
        raise NotImplementedError


class ExtratorPadrao(ExtratorBanca):
    def __init__(self, codigo_prova: str, cargo_normalizado: str):
        self.codigo_prova = codigo_prova
        self.cargo_normalizado = cargo_normalizado

    def extrair(self, linhas: list[str]) -> dict[int, str]:
        explicitas = {}
        for linha in linhas:
            for n, r in re.findall(r"\b([1-9]\d{0,2})\s*[-:.)]?\s*(CERTO|ERRADO|VERDADEIRO|FALSO|ANULADA|ANULADO)\b", linha, re.I):
                explicitas[int(n)] = {"VERDADEIRO": "Certo", "FALSO": "Errado", "ANULADO": "Anulada"}.get(r.upper(), r.capitalize())
        if explicitas:
            resultado = _extrair_pares_mesma_linha(linhas)
            resultado.incorporar(explicitas)
            return resultado
        for i, linha in enumerate(linhas[:-1]):
            if re.fullmatch(r'(?:Item|Questões|Questoes)\s+(?:\d+\s*)+', linha, re.I):
                ns = [int(n) for n in re.findall(r'\d+', linha)]
                rs = re.findall(r'\b[VFX]\b', linhas[i+1].upper())
                if len(ns) == len(rs) and rs and any(r in {'V','F'} for r in rs):
                    return {n:{'V':'Certo','F':'Errado','X':'Anulada'}[r] for n,r in zip(ns,rs)}
        itens = _extrair_itens_certo_errado(linhas)
        if itens:
            itens.update(_extrair_duas_linhas(linhas, self.codigo_prova, self.cargo_normalizado))
            return itens
        resultado = _extrair_pares_mesma_linha(linhas)
        if resultado or getattr(resultado, "conflitos", None):
            return resultado
        # O layout CEBRASPE pode conter Item/Certo-Errado e, na mesma página,
        # uma sequência em duas linhas. A implementação anterior acumulava os
        # dois blocos; manter essa união é parte da paridade do parser.
        resultado = _extrair_itens_certo_errado(linhas)
        resultado.update(_extrair_duas_linhas(
            linhas, self.codigo_prova, self.cargo_normalizado,
        ))
        if not resultado:
            # Lista vertical: número sozinho, seguido de uma resposta sozinha.
            for i in range(len(linhas)-1):
                if re.fullmatch(r'[1-9]\d{0,2}', linhas[i]) and re.fullmatch(r'[A-EX]', linhas[i+1].upper()):
                    resultado[int(linhas[i])] = linhas[i+1].upper()
        return resultado


class ExtratorMultiprova(ExtratorBanca):
    def __init__(self, codigo_prova: str):
        self.codigo_prova = codigo_prova

    def extrair(self, linhas: list[str]) -> dict[int, str]:
        pares = [
            re.findall(r"\b(\d{1,3})\s*(?:[-–:.)]\s*)?([A-EX])\b", linha.upper())
            for linha in linhas
        ]
        encontrado = re.search(r"(?:PROVA\s*)?(\d+)", self.codigo_prova, re.IGNORECASE)
        if not encontrado or not 1 <= int(encontrado.group(1)) <= 4:
            logger.warning("Grade multiprova exige seleção explícita de prova 1 a 4")
            return {}
        coluna = int(encontrado.group(1)) - 1
        resultado = {}
        for pares_linha in pares:
            inicio = coluna * 2
            for numero, resposta in pares_linha[inicio:inicio + 2]:
                resultado[int(numero)] = resposta
        return resultado


def selecionar_extrator(texto: str, codigo_prova: str = "", cargo_normalizado: str = "") -> ExtratorBanca:
    if re.search(r"PROVA\s*1", texto, re.IGNORECASE) and re.search(r"PROVA\s*2", texto, re.IGNORECASE):
        return ExtratorMultiprova(codigo_prova)
    return ExtratorPadrao(codigo_prova, cargo_normalizado)
