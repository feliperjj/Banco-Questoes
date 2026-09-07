"""Seleção exata de contexto antes de extrair qualquer gabarito."""
import re
import unicodedata
from src.importador.pdf_texto import _corrigir_encoding_ocr

def _texto_comparavel(texto: str) -> str:
    """Normaliza acentos e ruído de OCR para comparar cabeçalhos de PDFs."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    texto = _corrigir_encoding_ocr(texto).replace("�", "")
    return re.sub(r"\s+", " ", texto).strip().casefold()


def _cabecalho_cargo(linhas, i):
    linha = linhas[i].strip()
    comparavel = _texto_comparavel(linha)
    if re.match(r'(?i)^\d{1,3}\s*[-–:.]\s*[A-EX](?:\s+\d{1,3}\s*[-–:.]|\s*$)', linha):
        return False
    if re.match(r"(?i)^(?:[a-z]{2,}[_-]\d{2,4}[_-]|\d{1,4}\s*[-–]\s*[a-z]|cargo\s*:)", linha):
        return True
    if i+1 >= len(linhas) or not linha.isupper() or len(linha)<5:
        return False
    if re.search(r"\b(?:lingua|portugues|matematica|raciocinio|nocoes|conhecimentos|direito|informatica|legislacao|contabilidade)\b", comparavel):
        return False
    return bool(re.match(r"\s*0?1(?:\s*[:.)-]\s*[A-EX]\b|\s+2\b)", linhas[i+1], re.I))


class FiltroContexto:
    def __init__(self, codigo_prova: str | None = None, cargo: str | None = None):
        self.codigo_prova = (codigo_prova or "").lower().replace("-", "_")
        self.cargo_normalizado = _texto_comparavel(cargo)
        self.cargo_ativo = not bool(cargo)
        self.codigo_ativo = not bool(self.codigo_prova)

    def pagina_relevante(self, texto: str) -> bool:
        if re.fullmatch(r'(?i)prova\s*\d{1,2}', self.codigo_prova) and re.search(r'(?i)CONHECIMENTOS\s+B[ÁA]SICOS', texto) and not re.search(r'(?i)\bPROVA\s+\d', texto):
            return True
        linhas = texto.splitlines()
        cabecalhos = [linha for i, linha in enumerate(linhas) if _cabecalho_cargo(linhas, i)]
        if self.cargo_normalizado and cabecalhos:
            if self.cargo_normalizado not in _texto_comparavel(texto):
                self.cargo_ativo = False
                return False
        # Uma página pode reunir vários cargos. Selecionar um cabeçalho
        # compatível, em vez de rejeitar pela primeira linha de outro cargo.
        tipos = []
        for linha in linhas:
            m = re.search(r"(?i)\bprova\s+tipo\s+(\d+)\b", linha)
            if m:
                titulo = _texto_comparavel(linha[:m.start()]).strip(" -–—:|")
                titulo = re.sub(r"^cargo\s*:\s*", "", titulo)
                tipos.append((titulo, m.group(1)))
        if tipos:
            compativeis = [(t,n) for t,n in tipos if not self.cargo_normalizado or not t or t == self.cargo_normalizado]
            pedido = re.search(r"(?i)(?:prova\s+tipo|tipo|prova|t)\s*(\d+)", self.codigo_prova)
            if not compativeis or pedido and not any(n == pedido.group(1) for _,n in compativeis):
                self.cargo_ativo = self.codigo_ativo = False
                return False
            if pedido:
                self.codigo_ativo = True
        texto_normalizado = texto.lower().replace("-", "_")
        codigos_cebraspe = set(re.findall(r'\b\d{3}_[a-z0-9]+_[a-z0-9]+_\d{2}\b', texto_normalizado))
        if re.search(r'\b\d{3}_[a-z0-9]+_[a-z0-9]+_\d{2}\b', self.codigo_prova) and not codigos_cebraspe:
            return False
        if self.codigo_prova and codigos_cebraspe:
            selecionados = {c.strip() for c in self.codigo_prova.split(';') if c.strip()}
            self.codigo_ativo = bool(selecionados & codigos_cebraspe)
            if not self.codigo_ativo:
                return False
        if not self.codigo_prova or self.codigo_prova in texto_normalizado:
            self.codigo_ativo = True
        outro_codigo = re.search(r"c[oó]digo\s*[:\-]?\s*([a-z0-9_]+)", texto_normalizado)
        if self.codigo_ativo and outro_codigo and self.codigo_prova and self.codigo_prova not in outro_codigo.group(1):
            self.codigo_ativo = False
            return False
        if self.codigo_prova and not self.codigo_ativo and "dpf14_cbns01" not in texto_normalizado:
            return False
        comparavel = _texto_comparavel(texto)
        if self.cargo_normalizado and self.cargo_normalizado not in comparavel and not self.cargo_ativo:
            return False
        if self.cargo_normalizado in comparavel:
            self.cargo_ativo = True
        if self.cargo_ativo and self.cargo_normalizado and re.search(
            r"\b(?:cargo|agente|analista|administrador|auditor)\b", comparavel
        ) and self.cargo_normalizado not in comparavel:
            self.cargo_ativo = False
            return False
        return True

    def linhas_do_cargo(self, linhas: list[str]) -> list[str]:
        if not self.cargo_normalizado:
            return linhas
        comparaveis = [_texto_comparavel(linha) for linha in linhas]
        inicio = next((i for i, linha in enumerate(comparaveis) if self.cargo_normalizado in linha), None)
        if inicio is None:
            return linhas
        fim = len(linhas)
        viu_resposta = False
        for i in range(inicio + 1, len(linhas)):
            linha = comparaveis[i]
            if re.match(r"^\d{1,3}(?:\s*[:.)-]|\s+\d)", linha):
                viu_resposta = True
            if viu_resposta and _cabecalho_cargo(linhas, i):
                fim = i
                break
            if re.search(r"\b(?:prova\s+tipo|ibfc[_ ]\d+|cargo\s*[:\-]|agente|analista|administrador|auditor|assistente)\b", linha):
                if not re.search(r"\b(?:lingua|raciocinio|nocoes|principios|conhecimentos|direito|informatica)\b", linha):
                    fim = i
                    break
        return linhas[inicio:fim]
