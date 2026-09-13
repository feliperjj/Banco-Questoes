"""Perfis textuais de gabarito, independentes da leitura PDF."""
import re
import logging
from .gabaritos_resultado import MapaGabarito
logger=logging.getLogger(__name__)

def _extrair_pares_mesma_linha(linhas: list[str]) -> dict[int, str]:
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
    resultado = MapaGabarito()
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
                    resultado.incorporar({item: {'C': 'Certo', 'E': 'Errado', 'X': 'Anulada'}[resposta]})
    return resultado


def _extrair_duas_linhas(linhas: list[str], codigo_prova: str, cargo_normalizado: str) -> dict[int, str]:
    resultado = MapaGabarito()
    padrao_codigo = re.compile(r'c[oó]digo\s*[:\-]?\s*(\d{3})\b', re.I)
    # Códigos completos e tipos já são filtrados pelo contexto da página.
    # O seletor local só atua no layout que declara "Código 123" por bloco.
    cargo_selecionado = not codigo_prova or bool(cargo_normalizado) or not any(padrao_codigo.search(l) for l in linhas)
    for indice, linha in enumerate(linhas):
        codigo_match = padrao_codigo.search(linha)
        if codigo_match:
            codigo = codigo_match.group(1)
            cargo_selecionado = not codigo_prova or codigo in {c.strip() for c in codigo_prova.split(';')}
            continue
        numeros = re.findall(r"\d{1,3}", linha) if cargo_selecionado and re.fullmatch(r"(?i)(?:(?:Item|Questões|Questoes)\s+)?\d{1,3}(?:\s+\d{1,3})*", linha.strip()) else []
        if not numeros or indice + 1 >= len(linhas):
            continue
        proxima_linha = indice + 1
        # Pular apenas um rótulo vazio, nunca outro bloco ou resposta parcial.
        if re.fullmatch(r'(?i)(?:Gabarito|Respostas?)\s*:?\s*', linhas[proxima_linha]):
            proxima_linha += 1
        if proxima_linha >= len(linhas):
            continue
        resposta_texto = re.sub(r'(?i)^(?:Gabarito|Respostas?)\s*:?\s*', '', linhas[proxima_linha].strip())
        respostas_linha = resposta_texto.upper().split()
        validos = set('ABCDEXVF') | {'CERTO', 'ERRADO', 'VERDADEIRO', 'FALSO', 'ANULADA', 'ANULADO', '0', '?', '*'}
        if any(r not in validos for r in respostas_linha):
            continue
        if len(respostas_linha) != len(numeros):
            continue
        for numero, resposta in zip(numeros, respostas_linha):
            if int(numero) and resposta not in {'0', '?', '*'}:
                normalizadas = {'V': 'Certo', 'F': 'Errado', 'CERTO': 'Certo', 'ERRADO': 'Errado',
                                'VERDADEIRO': 'Certo', 'FALSO': 'Errado', 'ANULADA': 'Anulada', 'ANULADO': 'Anulada'}
                if any(r in {'V', 'F', 'VERDADEIRO', 'FALSO'} for r in respostas_linha):
                    normalizadas['X'] = 'Anulada'
                resultado.incorporar({int(numero): normalizadas.get(resposta, resposta)})
    return resultado


class ExtratorBanca:
    def extrair(self, linhas: list[str]) -> dict[int, str]:
        raise NotImplementedError


class ExtratorExtenso(ExtratorBanca):
    """Respostas por extenso e notas explícitas de anulação."""

    def extrair(self, linhas: list[str]) -> dict[int, str]:
        resultado = MapaGabarito()
        padrao = re.compile(r"\b([1-9]\d{0,2})\s*[-–:.)]?\s*(CERTO|ERRADO|VERDADEIRO|FALSO|ANULADA|ANULADO)\b", re.I)
        for linha in linhas:
            limpa = re.sub(r'(?i)\b(?:questão|questao|item|gabarito)\s*:?\s*', '', linha)
            if re.search(r'\w', padrao.sub('', limpa)):
                continue
            for numero, resposta in padrao.findall(limpa):
                normalizada = {'VERDADEIRO': 'Certo', 'FALSO': 'Errado', 'ANULADO': 'Anulada'}.get(resposta.upper(), resposta.capitalize())
                resultado.incorporar({int(numero): normalizada})
        return resultado


class ExtratorHorizontal(ExtratorBanca):
    """Blocos número/resposta, incluindo listas verticais unitárias."""

    def __init__(self, codigo_prova: str, cargo_normalizado: str):
        self.codigo_prova = codigo_prova
        self.cargo_normalizado = cargo_normalizado

    def extrair(self, linhas: list[str]) -> dict[int, str]:
        return _extrair_duas_linhas(linhas, self.codigo_prova, self.cargo_normalizado)


class ExtratorPadrao(ExtratorHorizontal):
    """Compõe perfis por bloco, sem descartar o restante da página."""

    def extrair(self, linhas: list[str]) -> dict[int, str]:
        resultado = _extrair_pares_mesma_linha(linhas)
        resultado.incorporar(ExtratorExtenso().extrair(linhas))
        resultado.incorporar(super().extrair(linhas))
        return resultado


class ExtratorMultiprova(ExtratorBanca):
    def __init__(self, codigo_prova: str):
        self.codigo_prova = codigo_prova

    def extrair(self, linhas: list[str]) -> dict[int, str]:
        pares = [
            re.findall(r"\b(\d{1,3})\s*(?:[-–:.)]\s*)?([A-EX])\b", linha.upper())
            for linha in linhas
        ]
        encontrado = re.fullmatch(r"(?:PROVA\s*)?(\d+)", self.codigo_prova.strip(), re.IGNORECASE)
        if not encontrado or not 1 <= int(encontrado.group(1)) <= 4:
            logger.warning("Grade multiprova exige seleção explícita de prova 1 a 4")
            return {}
        cabecalho = next((re.findall(r'(?i)\bPROVA\s*([1-4])\b', l) for l in linhas
                         if len(re.findall(r'(?i)\bPROVA\s*([1-4])\b', l)) >= 2), [])
        if len(set(cabecalho)) != len(cabecalho) or encontrado.group(1) not in cabecalho:
            return MapaGabarito()
        coluna = cabecalho.index(encontrado.group(1))
        resultado = MapaGabarito()
        for pares_linha in pares:
            if len(pares_linha) != 2 * len(cabecalho):
                continue
            inicio = coluna * 2
            for numero, resposta in pares_linha[inicio:inicio + 2]:
                resultado.incorporar({int(numero): resposta})
        return resultado


def selecionar_extrator(texto: str, codigo_prova: str = "", cargo_normalizado: str = "") -> ExtratorBanca:
    if re.search(r"PROVA\s*1\b", texto, re.IGNORECASE) and re.search(r"PROVA\s*2\b", texto, re.IGNORECASE):
        return ExtratorMultiprova(codigo_prova)
    return ExtratorPadrao(codigo_prova, cargo_normalizado)
