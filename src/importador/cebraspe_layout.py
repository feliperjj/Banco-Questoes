"""Leitura de itens C/E com recuo tipográfico e contexto compartilhado.

Retorna None quando o documento não confirma o contrato de layout; o extrator
genérico continua disponível. Nenhuma decisão consulta respostas do gabarito.
"""
import re
from statistics import median


def extrair_layout_cebraspe(pdf):
    primeira = pdf.pages[0].extract_text() or ''
    if not re.search(r'CEBRASPE', primeira, re.I) or not re.search(r'\bjulgue\b', primeira, re.I):
        return None
    if re.search(r'(?im)^\s*(?:\(?[A-E]\)|JUSTIFICATIVA\s*[:–-])', primeira):
        return None
    from src.importador.pdf_texto import _pagina_sem_texto_rotacionado, _agrupar_palavras_por_linha
    itens, atual, contexto, pendente = [], None, '', []
    disciplina = ''
    for pagina in pdf.pages:
        texto = pagina.extract_text() or ''
        if re.search(r'CONHECIMENTOS\s+ESPEC[ÍI]FICOS', texto, re.I):
            disciplina = 'Conhecimentos Específicos'
        elif re.search(r'CONHECIMENTOS\s+B[ÁA]SICOS', texto, re.I):
            disciplina = 'Conhecimentos Básicos'
        if re.search(r'PROVA\s+DISCURSIVA|RASCUNHO', texto, re.I):
            break
        pagina = _pagina_sem_texto_rotacionado(pagina)
        linhas_pagina = _agrupar_palavras_por_linha(pagina.extract_words(x_tolerance=2, y_tolerance=3))
        faixas_cabecalho = [top for top, ws in linhas_pagina
                           if re.search(r'PROVAS? OBJETIVAS|CONHECIMENTOS', ' '.join(w['text'] for w in ws), re.I)
                           and top < 90]
        for esquerda, direita in [(0, pagina.width / 2), (pagina.width / 2, pagina.width)]:
            palavras = pagina.crop((esquerda, 42, direita, pagina.height - 20)).extract_words(x_tolerance=2, y_tolerance=3)
            linhas = [(top, sorted(ws, key=lambda w: w['x0'])) for top, ws in _agrupar_palavras_por_linha(palavras)]
            marcadores = [ws[0] for _, ws in linhas if len(ws) > 1 and re.fullmatch(r'\d{1,3}', ws[0]['text'])
                          and 1 <= int(ws[0]['text']) <= 200]
            if len(marcadores) < 2:
                return None
            margem = median(w['x0'] for w in marcadores)
            if not esquerda <= margem <= esquerda + pagina.width * .12:
                return None
            # Um novo texto na coluna seguinte não pode virar continuação do
            # item anterior, que já terminou com pontuação.
            if atual and re.search(r'[.!?][”"\')]*$', atual['linhas'][-1]):
                atual = None
            for top, ws in linhas:
                if any(abs(top - y) < 5 for y in faixas_cabecalho):
                    continue
                linha = ' '.join(w['text'] for w in ws)
                if re.search(r'CEBRASPE|pcimarkpci|pciconcursos|PROVAS? OBJETIVAS|CONHECIMENTOS|^B[ÁA]SICOS|^ESPEC[ÍI]FICOS', linha, re.I):
                    continue
                primeiro = ws[0]
                numero = re.fullmatch(r'\d{1,3}', primeiro['text'])
                if numero and len(ws) > 1 and abs(primeiro['x0'] - margem) < 4:
                    if pendente:
                        contexto = '\n'.join(pendente).strip()
                        pendente = []
                    atual = {'numero': int(numero.group()), 'contexto': contexto, 'disciplina': disciplina,
                             'linhas': [' '.join(w['text'] for w in ws[1:])]}
                    itens.append(atual)
                elif atual is not None and not pendente and primeiro['x0'] >= margem + 7:
                    atual['linhas'].append(linha)
                else:
                    pendente.append(linha)
    numeros = [q['numero'] for q in itens]
    if len(itens) < 20 or numeros != list(range(1, len(itens) + 1)):
        return None
    # Recusar resultados sem contexto de julgamento confirmado.
    if not all(re.search(r'julgue', q['contexto'], re.I) for q in itens):
        return None
    ano = re.search(r'Edital\s*:\s*(20\d{2})', primeira, re.I)
    saida = ['CEBRASPE', f'Edital: {ano.group(1)}' if ano else '']
    for q in itens:
        corpo = '\n'.join(q['linhas'])
        corpo = re.sub(r'(?<=\w)-\n(?=\w)', '', corpo)
        saida.append(f"{q['disciplina']}\nQUESTÃO {q['numero']}\nTEXTO DE APOIO\n{q['contexto']}\nITEM PARA JULGAMENTO\n{corpo}")
    return '\n'.join(saida)
