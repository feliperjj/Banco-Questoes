"""Regras lexicais compartilhadas; não escolhem um perfil."""
import re

_INICIO_QUESTAO = re.compile(
    # Alguns PDFs exportam "QUESTÃO" como "QUEST�O" (caractere de
    # substituição). O marcador precisa continuar reconhecível mesmo assim.
    r"(?im)^((?:quest(?:ão|ao|�o)[ \t]*)?\d{1,3}(?:[ \t]*[.\-):][ \t]*|[ \t]+|[ \t]*\n))"
)


_INICIO_ALTERNATIVA = re.compile(r"(?im)^[ \t]*\(?([A-E])\)?\s*[.\-):]\s+")


_INICIO_NUMERADO = re.compile(r"(?im)^[ \t]*(\d{1,3})(?:[.\-):][ \t]*|[ \t]+).+$")


_INICIO_QUESTAO_NOMEADA = re.compile(
    r"(?im)^((?:quest(?:ão|ao|�o)[ \t]+\d{1,3})(?:[ \t]*[.\-):]|[ \t]*\n|[ \t]+))"
)


_MARCADOR_QUESTAO = re.compile(r"(?i)^(?:quest(?:ão|ao|�o)[ \t]*)?(\d{1,3})(?:[ \t]*[.\-):][ \t]*|[ \t]+|[ \t]*\n)")


_MARCADOR_INLINE = re.compile(
    r"(?<!^)(?<!\n)[ \t]+(?=(?:(?i:quest(?:ão|ao|�o))[ \t]*)?\d{1,3}[)\-.:][ \t]+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ�])",
)


def _juntar_linhas(texto: str) -> str:
    if '\nITEM PARA JULGAMENTO\n' in texto:
        contexto, item = texto.split('\nITEM PARA JULGAMENTO\n', 1)
        item = re.sub(r'\nConhecimentos (?:Básicos|Específicos|Gerais|Complementares)\s*$', '', item)
        contexto = re.sub(r'\s+', ' ', contexto).strip()
        item = re.sub(r'\s+', ' ', item).strip()
        return f'{contexto}\n\nITEM PARA JULGAMENTO\n{item}'
    return re.sub(r"\s+", " ", texto).strip()


def _separar_alternativas_horizontais(texto):
    linhas = []
    for linha in texto.splitlines():
        marcadores = list(re.finditer(r'(?<!\w)\(?([A-Ea-e])\)\s+', linha))
        letras = [m.group(1).upper() for m in marcadores]
        mesma_caixa = len({m.group(1).islower() for m in marcadores}) == 1
        if len(letras) >= 2 and letras == sorted(set(letras)) and mesma_caixa:
            linha = re.sub(r'(?<!\w)(\(?[A-Ea-e]\)\s+)', r'\n\1', linha)
        linhas.append(linha)
    return '\n'.join(linhas)


def _partes_alternativas(texto):
    partes = _INICIO_ALTERNATIVA.split(_separar_alternativas_horizontais(texto))
    letras = [l.upper() for l in partes[1::2]]
    for i in range(len(letras)-2, 1, -1):
        if letras[i:] == list('ABCDE'[:len(letras)-i]) and len(letras[i:]) >= 2 and len(set(letras[:i])) >= 2:
            # Listas de associação/tributos no enunciado podem usar A–E;
            # a sequência final de respostas reinicia em A.
            prefixo = partes[0] + ''.join(f'\n({partes[j]}) {partes[j+1]}' for j in range(1,1+2*i,2))
            return [prefixo] + partes[1+2*i:]
    return partes


def _parece_grade_respostas(linha: str) -> bool:
    numeros = re.findall(r"\b\d{1,3}\b", linha)
    palavras = re.findall(r"[A-Za-zÀ-ÿ�]{3,}", linha)
    return len(numeros) >= 5 and not palavras
