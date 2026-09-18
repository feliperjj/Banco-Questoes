"""Itens de julgamento com recuos, texto-base e uma ou duas colunas.

O contrato é geométrico e textual, sem nome de banca. Não aceita números de
linha como itens e não completa lacunas. Falha fechada se a sequência divergir.
"""
import re
from statistics import median

JULGAMENTO = re.compile(r'\b(?:julgue|judge)\b', re.I)
SECAO = re.compile(r'CONHECIMENTOS\s+(GERAIS|B[ÁA]SICOS|COMPLEMENTARES|ESPEC[ÍI]FICOS)', re.I)


def extrair_recuado(pdf):
    from src.importador.pdf_texto import _pagina_sem_texto_rotacionado, _agrupar_palavras_por_linha
    amostra = '\n'.join(p.extract_text() or '' for p in pdf.pages[:2])
    if not JULGAMENTO.search(amostra) or not re.search(r'\b(?:CERTO|ERRADO|judge the following items)\b', amostra, re.I):
        return None
    if re.search(r'(?im)^\s*JUSTIFICATIVA\s*[-:–]', amostra):
        return None
    pontuado = bool(re.search(r'(?m)^\s*\d{1,3}\.\s+\S', amostra))
    itens, pendente, contexto, texto_base = [], [], '', ''
    atual = None
    disciplina = ''
    avisos = []
    for indice, original in enumerate(pdf.pages):
        texto = original.extract_text() or ''
        if not itens and re.search(r'INSTRU', texto, re.I) and not JULGAMENTO.search(texto):
            continue
        if re.search(r'(?im)^\s*(?:PROVA DISCURSIVA|RASCUNHO)\s*$', texto):
            break
        pagina = _pagina_sem_texto_rotacionado(original)
        words = pagina.extract_words(x_tolerance=2, y_tolerance=3)
        linhas = _agrupar_palavras_por_linha(words)
        # Localiza início da área útil sem amputar textos da primeira página.
        topo = 42
        for y, ws in linhas:
            t = ' '.join(w['text'] for w in ws)
            if re.search(r'PROVAS? OBJETIVAS', t, re.I):
                if not pontuado:
                    topo = max(topo, y + 13)
            m = SECAO.search(t)
            if m and (y < 100 or indice == 0):
                disciplina = 'Conhecimentos ' + m.group(1).capitalize()
                if not pontuado:
                    topo = max(topo, y + 13)
        # Marcadores numa segunda margem confirmam duas colunas. Números
        # internos nunca são primeiros tokens de uma linha recortada.
        direita = [w for w in words if re.fullmatch(r'\d{1,3}\.?', w['text'])
                   and pagina.width * .49 < w['x0'] < pagina.width * .56 and w['top'] > topo]
        cruzadas = sum(1 for w in words if w['x0'] < pagina.width/2 - 3 and w['x1'] > pagina.width/2 + 3 and w['top'] > topo)
        duas = len(direita) >= 2 and cruzadas < 5
        limites = [(0, pagina.width/2), (pagina.width/2, pagina.width)] if duas else [(0, pagina.width)]
        # Primeira página pode conter texto-base inteiro à esquerda e apenas
        # poucos itens à direita: a margem dos itens ainda confirma o formato.
        for esquerda, direita in limites:
            fundo = pagina.height * .94 if pontuado else pagina.height-28
            ws = pagina.crop((esquerda, topo, direita, fundo)).extract_words(x_tolerance=2, y_tolerance=3)
            ls = [(y, sorted(w, key=lambda v:v['x0'])) for y,w in _agrupar_palavras_por_linha(ws)]
            candidatos = [w[0] for _,w in ls if len(w)>1 and re.fullmatch(r'\d{1,3}\.?',w[0]['text'])
                          and esquerda <= w[0]['x0'] < esquerda + pagina.width*.085]
            margem = median(w['x0'] for w in candidatos) if candidatos else esquerda + 28
            if atual and re.search(r'[.!?][”"\')]*$', atual['linhas'][-1]):
                atual = None
            anterior_y = topo
            barreiras = [l['top'] for l in list(getattr(pagina, 'lines', ())) + list(getattr(pagina, 'rects', ()))
                         if abs(l['bottom']-l['top']) < 2 and l['x1']-l['x0'] > (direita-esquerda)*.7
                         and l['x0'] >= esquerda-2 and l['x1'] <= direita+2]
            for y, w in ls:
                if any(anterior_y < by <= y for by in barreiras):
                    atual = None
                anterior_y = y
                t = ' '.join(v['text'] for v in w)
                if re.fullmatch(r'(?:[A-Z][ ]+){3,}[A-Z]', t) or re.match(r'(?i)^Área livre\b', t):
                    continue
                if re.fullmatch(r'[-–— ]*(?:CONHECIMEN\w*|TOS\s+(?:GERAIS|COMPLEMENTARES|ESPEC[ÍI]FICOS|B[ÁA]SICOS))[-–— ]*', t, re.I):
                    continue
                if re.search(r'CEBRASPE|pcimarkpci|pciconcursos|PROVAS? OBJETIVAS|^Espaço livre',t,re.I) or SECAO.search(t):
                    continue
                n = re.fullmatch(r'\d{1,3}\.?',w[0]['text'])
                if n and len(w)>1 and abs(w[0]['x0']-margem)<4:
                    numero = int(n.group().rstrip('.'))
                    if numero != len(itens)+1:
                        return None
                    if pendente:
                        novo = '\n'.join(pendente).strip()
                        if JULGAMENTO.search(novo):
                            # Um comando referenciando texto prévio reutiliza o
                            # texto-base, mas não acumula comandos de outros temas.
                            cmd = list(JULGAMENTO.finditer(novo))[-1]
                            tem_texto = len(novo[:cmd.start()]) > 450
                            if tem_texto:
                                texto_base = novo
                                contexto = novo
                            elif re.search(r'\btexto\b|\btext\b',novo,re.I) and texto_base:
                                contexto = texto_base + '\n' + novo
                            else:
                                contexto = novo
                                texto_base = ''
                        else:
                            contexto = novo
                        pendente = []
                    if not JULGAMENTO.search(contexto):
                        return None
                    atual = {'numero':numero,'contexto':contexto,'linhas':[' '.join(v['text'] for v in w[1:])], 'disciplina':disciplina}
                    itens.append(atual)
                elif atual is not None and not pendente and w[0]['x0'] >= margem+7:
                    atual['linhas'].append(t)
                else:
                    pendente.append(t)
    if len(itens)<20:
        return None
    ano = re.search(r'Edital\s*:\s*(20\d{2})',amostra,re.I)
    # Metadados continuam extraídos do cabeçalho real, não do nome do perfil.
    cabecalho = '\n'.join(l for l in amostra.splitlines()[:6] if 'pcimarkpci' not in l)
    saida = [cabecalho, f'Edital: {ano.group(1)}' if ano else '']
    for q in itens:
        corpo = re.sub(r'(?<=\w)-\n(?=\w)', '', '\n'.join(q['linhas']))
        saida.append(f"{q['disciplina']}\nQUESTÃO {q['numero']}\nTEXTO DE APOIO\n{q['contexto']}\nITEM PARA JULGAMENTO\n{corpo}")
    return '\n'.join(saida)
