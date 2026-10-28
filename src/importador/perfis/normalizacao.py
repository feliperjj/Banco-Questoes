"""Normalizações locais acionadas por evidência, sem alterar texto livre."""
import re


def normalizar_formatos(texto):
    texto = re.sub(r'(?im)^Legisla[çc][aã]o Acerca de Seguran[çc]a da\s+Informa[çc][aã]o e Prote[çc][aã]o de Dados[ \t]*$',
                   lambda match: re.sub(r'\s+', ' ', match.group()), texto)
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
    texto = re.sub(r"(?im)^([ \t]*[A-E][.)][ \t]*)(?:Check-square|SQUARE|□|☐|☑)[ \t]*", r"\1", texto)
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
    for m in re.finditer(r'(?im)^Text(?:o)?[ \t]+([A-Z0-9]+)[ \t]*\n', texto):
        fim = _INICIO_QUESTAO.search(texto, m.end())
        if fim and fim.start()-m.end() > 80:
            saida.setdefault(m.group(1).upper(), []).append((m.start(), texto[m.start():fim.start()].strip()))
    return saida


CONTEXTO_RELATIVO = re.compile(
    r'(?im)^(?:ATEN[ÇC][AÃ]O:\s*O texto a seguir refere-se [àa]s\s+(duas|tr[eê]s|\d+)\s+pr[óo]ximas quest[õo]es[^\n]*|'
    r'READ TEXT\s+[IVX]+\s+AND ANSWER NEXT\s+(TWO|THREE|SEVEN|\d+)\s+QUESTIONS[^\n]*)\n')


def contextos_relativos(texto, candidatos):
    """Usa a contagem impressa e os marcadores reais dos blocos já reconhecidos."""
    from .lexico import _INICIO_QUESTAO, _MARCADOR_QUESTAO, _juntar_linhas
    from .segmentacao import partes_bloco
    stems = {}
    for block in candidatos:
        marker = _MARCADOR_QUESTAO.match(block.strip())
        parts = partes_bloco(block)
        if marker and len(parts) >= 5:
            stems[int(marker[1])] = _juntar_linhas(parts[0])[:60]
    markers = []
    for marker in _INICIO_QUESTAO.finditer(texto):
        parsed = _MARCADOR_QUESTAO.match(marker[1])
        number = int(parsed[1]) if parsed else None
        if number in stems and _juntar_linhas(texto[marker.end():marker.end() + 600]).startswith(stems[number]):
            markers.append((number, marker.start()))
    declarations = list(CONTEXTO_RELATIVO.finditer(texto))
    result = {}
    words = {'duas': 2, 'tres': 3, 'três': 3, 'two': 2, 'three': 3, 'seven': 7}
    for index, declaration in enumerate(declarations):
        raw_count = (declaration[1] or declaration[2]).casefold()
        count = int(raw_count) if raw_count.isdigit() else words[raw_count]
        end = declarations[index + 1].start() if index + 1 < len(declarations) else len(texto)
        following = [(number, pos) for number, pos in markers if declaration.end() <= pos < end][:count]
        if not 0 < count <= 20 or len(following) != count or len({number for number, _ in following}) != count:
            continue
        passage = texto[declaration.start():following[0][1]].strip()
        for number, _ in following:
            result[number] = passage
    return result
