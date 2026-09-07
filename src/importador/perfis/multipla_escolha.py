"""Segmentação de múltipla escolha, versão 1."""
import re

def _blocos_multipla_escolha(texto):
    """Prefere o formato predominante e mantém enumerações no enunciado."""
    from src.importador.perfis.lexico import _INICIO_ALTERNATIVA
    formatos = [r"(?m)^\d{1,3}[ \t]*\n", r"(?m)^\d{1,3}[.)][ \t]+"]
    candidatos = [list(re.finditer(formato, texto)) for formato in formatos]
    marcadores = max(candidatos, key=len)
    if len(marcadores) < 3:
        return []
    inicios = []
    for marcador in marcadores:
        if not inicios or len(_INICIO_ALTERNATIVA.findall(texto[inicios[-1]:marcador.start()])) >= 2:
            inicios.append(marcador.start())
    return [texto[inicio:fim] for inicio, fim in zip(inicios, inicios[1:] + [len(texto)])]


def _qualidade_numeracao(blocos):
    from src.importador.perfis.lexico import _MARCADOR_QUESTAO, _INICIO_ALTERNATIVA, _juntar_linhas
    numeros = []
    for bloco in blocos:
        marcador = _MARCADOR_QUESTAO.match(bloco.strip())
        if not marcador:
            continue
        conteudo = bloco.strip()[marcador.end():]
        partes = _INICIO_ALTERNATIVA.split(conteudo)
        if len(_juntar_linhas(partes[0])) >= 10 and len(partes) >= 3:
            numeros.append(int(marcador.group(1)))
    amplitude = max(numeros) - min(numeros) if numeros else 0
    return len(set(numeros)), -(len(numeros) - len(set(numeros))), -amplitude


