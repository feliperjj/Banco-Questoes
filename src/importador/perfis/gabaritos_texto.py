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
        proxima = indice + 1
        if re.fullmatch(r"(?i)(?:Gabarito|Respostas?)\s*:?\s*", linhas[proxima].strip()):
            proxima += 1
        if proxima >= len(linhas):
            continue
        respostas = re.findall(r"\b[CEX0]\b", linhas[proxima].upper())
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
        validos = set('ABCDEXVF') | {'CERTO', 'ERRADO', 'VERDADEIRO', 'FALSO', 'ANULADA', 'ANULADO', '0', '?', '*'}
        respostas_linha = None
        proxima_linha = indice + 1
        candidata = linhas[proxima_linha].strip()
        # A próxima sequência numérica inicia outro bloco: não atravesse-o.
        if re.fullmatch(r"(?i)(?:(?:Item|Questões|Questoes)\s+)?\d{1,3}(?:\s+\d{1,3})*", candidata):
            continue
        rotulo_embutido = bool(re.match(r"(?i)^(?:Gabarito|Respostas?)\s*:?\s+", candidata))
        if re.fullmatch(r"(?i)(?:Gabarito|Respostas?)\s*:?\s*", candidata):
            proxima_linha += 1
            if proxima_linha >= len(linhas):
                continue
            candidata = linhas[proxima_linha].strip()
        elif rotulo_embutido:
            candidata = re.sub(r"(?i)^(?:Gabarito|Respostas?)\s*:?\s+", "", candidata)
        # Sem rótulo de resposta, aceite apenas a sequência inteira e adjacente.
        # Pular texto ou linhas ambíguas pode vincular opções do caderno como gabarito.
        tokens = candidata.upper().split()
        if len(tokens) == len(numeros) and all(token in validos for token in tokens):
            respostas_linha = tokens
        if respostas_linha is None:
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
        from .documentos import normalizar_versao
        encontrado = re.fullmatch(r"(\d+)", normalizar_versao(self.codigo_prova))
        if not encontrado or not 1 <= int(encontrado.group(1)) <= 4:
            logger.warning("Grade multiprova exige seleção explícita de prova 1 a 4")
            return {}
        # Blocos empilhados têm um rótulo por linha e duas linhas adjacentes
        # de números/respostas. Não são colunas de pares número-alternativa.
        headers = [(i, re.findall(r'(?i)\b(?:PROVA\s+TIPO|PROVA|TIPO)\s*([1-4]|IV|III|II|I)\b', line))
                   for i, line in enumerate(linhas)]
        headers = [(i, labels) for i, labels in headers if labels]
        numeric_rows = any(re.fullmatch(r'\s*\d{1,3}(?:\s+\d{1,3}){2,}\s*', line) for line in linhas)
        if headers and numeric_rows and all(len(labels) == 1 for _, labels in headers):
            result = MapaGabarito()
            for index, (start, labels) in enumerate(headers):
                if normalizar_versao(labels[0]) != encontrado.group(1):
                    continue
                end = headers[index + 1][0] if index + 1 < len(headers) else len(linhas)
                result.incorporar(_extrair_duas_linhas(linhas[start + 1:end], '', ''))
            return result
        # Preservar a ordem física dos cabeçalhos. Ordenar por número pode
        # selecionar silenciosamente a coluna errada quando a extração textual
        # apresenta, por exemplo, "PROVA 2 PROVA 1".
        cabecalho = list(dict.fromkeys(
            int(normalizar_versao(n)) for linha in linhas for n in
            re.findall(r'(?i)\b(?:PROVA|TIPO|T)\s*([1-4]|IV|III|II|I)\b', linha)
        ))
        if int(encontrado.group(1)) not in cabecalho:
            return MapaGabarito()
        coluna = cabecalho.index(int(encontrado.group(1)))
        resultado = MapaGabarito()
        for pares_linha in pares:
            if not cabecalho or not pares_linha or len(pares_linha) % len(cabecalho):
                continue
            quantidade = len(pares_linha) // len(cabecalho)
            inicio = coluna * quantidade
            for numero, resposta in pares_linha[inicio:inicio + quantidade]:
                resultado.incorporar({int(numero): resposta})
        return resultado


class ExtratorItensCE(ExtratorBanca):
    """Perfil de grade de itens Certo/Errado/Anulado, independente da banca."""

    def extrair(self, linhas: list[str]) -> dict[int, str]:
        return _extrair_itens_certo_errado(linhas)


def selecionar_extrator(texto: str, codigo_prova: str = "", cargo_normalizado: str = "", *, perfil: str = "") -> ExtratorBanca:
    if perfil == "cex_itens_em_grade":
        return ExtratorItensCE()
    if perfil in {"multiprova_por_colunas", "matriz_multiversao"} or (
        re.search(r"PROVA\s*1\b", texto, re.IGNORECASE) and re.search(r"PROVA\s*2\b", texto, re.IGNORECASE)
    ):
        return ExtratorMultiprova(codigo_prova)
    return ExtratorPadrao(codigo_prova, cargo_normalizado)
