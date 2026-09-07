"""Normalizações locais acionadas por evidência, sem alterar texto livre."""
import re


def normalizar_formatos(texto):
    texto = re.sub(r'(?i)(quest(?:ões|oes) de)[ \t]*\n[ \t]*(n[úu]meros\s+\d)', r'\1 \2', texto)
    # Frações verticais exportadas na ordem numerador / letra / denominador.
    # Só reconhecer uma série completa de alternativas, nunca um número solto.
    fracao = re.compile(r'(?m)^(\d+)[ \t]*\n\(([A-E])\)[ \t]*([.;])[ \t]*\n(\d+)[ \t]*(?=\n|$)')
    achados = list(fracao.finditer(texto))
    sequencias = []
    for i in range(len(achados)-4):
        grupo = achados[i:i+5]
        if ''.join(m.group(2) for m in grupo) == 'ABCDE' and all(
                not texto[a.end():b.start()].strip() for a,b in zip(grupo,grupo[1:])):
            sequencias.extend(grupo)
    for m in reversed(sequencias):
        texto = texto[:m.start()] + f'({m.group(2)}) {m.group(1)}/{m.group(4)}{m.group(3)}' + texto[m.end():]
    texto = re.sub(r"(?im)^([ \t]*[A-E][.)][ \t]*)(?:SQUARE|□|☐|☑)[ \t]*", r"\1", texto)
    # Letras circuladas são marcadores somente se há uma sequência A/B.
    for alfabeto in ('ⒶⒷⒸⒹⒺ', 'ⓐⓑⓒⓓⓔ'):
        if all(re.search(r'(?m)^\s*'+c, texto) for c in alfabeto[:2]):
            for letra, simbolo in zip('ABCDE', alfabeto):
                texto = re.sub(r'(?m)^\s*'+simbolo+r'\s*', letra+') ', texto)
    # Algumas exportações põem apenas a letra na linha anterior ao conteúdo.
    encontrados = re.findall(r'(?m)^([A-E])[ \t]*$', texto)
    if len(encontrados) >= 3 and encontrados[:3] == list('ABC'):
        texto = re.sub(r'(?m)^([A-E])[ \t]*\n(?=\S)', r'\1) ', texto)
    # Questão com zero à esquerda, Nº e dois pontos é canonicalizada apenas
    # no marcador, sem mexer em números do enunciado.
    texto = re.sub(r'(?im)^[ \t]*(?:quest(?:ão|ao|�o)[ \t]+n[º°o.]?[ \t]*|q\.[ \t]*)(\d{1,3})[ \t]*[:.)–—-]?[ \t]*',
                   lambda m: 'QUESTÃO '+str(int(m.group(1)))+'\n', texto)
    return texto


def contextos_explicitos(texto):
    """Só vincula texto-base quando a fonte explicita o intervalo de questões."""
    padrao = re.compile(r'(?im)^([^\n]*(?:texto|text|enunciado|informa[çc][õo]es)[^\n]*quest(?:ões|oes)(?:[ \t]+de)?(?:[ \t]+n[úu]meros)?[ \t]+(\d{1,3})[ \t]+(a|até|ate|–|-|e)[ \t]+(\d{1,3})[^\n]*)\n')
    encontrados = {}
    for m in padrao.finditer(texto):
        inicio, fim = int(m.group(2)), int(m.group(4))
        restante = texto[m.end():]
        proxima = re.search(r'(?im)^QUEST(?:ÃO|AO)\s+0*'+str(inicio)+r'(?:[.)–—-]|[ \t]*\n|[ \t]+)', restante)
        if proxima is None:
            proxima = re.search(r'(?im)^0*'+str(inicio)+r'(?:[.)–—-]|[ \t]*\n)', restante)
        if proxima is None:
            continue
        corpo = texto[m.start():m.end()+proxima.start()].strip()
        if len(corpo) > 80 and 0 < inicio <= fim <= 200:
            numeros = (inicio, fim) if m.group(3).lower() == 'e' else range(inicio, fim+1)
            for n in numeros:
                encontrados[n] = corpo
    return encontrados


def textos_rotulados(texto):
    from .lexico import _INICIO_QUESTAO
    saida = {}
    for m in re.finditer(r'(?im)^Texto[ \t]+([A-Z0-9]+)[ \t]*\n', texto):
        fim = _INICIO_QUESTAO.search(texto, m.end())
        if fim and fim.start()-m.end() > 80:
            saida.setdefault(m.group(1).upper(), []).append((m.start(), texto[m.start():fim.start()].strip()))
    return saida
