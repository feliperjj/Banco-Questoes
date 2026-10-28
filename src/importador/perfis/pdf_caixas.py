"""Cadernos em colunas com alternativas acompanhadas de caixas de seleção."""
import re


CAIXA = re.compile(r"(?im)^[ \t]*[a-e][.)]\s*(?:SQUARE|Check-square)\b")


def extrair_caixas(pdf):
    from ..pdf_texto import (_pagina_sem_texto_rotacionado, _agrupar_palavras_por_linha,
                             _extrair_texto_colunas, _normalizar_pagina)
    from .pdf_paginas import TextoExtraido
    texts = [page.extract_text() or "" for page in pdf.pages]
    if sum(len(CAIXA.findall(text)) for text in texts) < 10:
        return None
    # Identificar os cabeçalhos na página inteira antes de cortar as colunas;
    # metades de uma mesma linha deixam de ser reconhecíveis como repetição.
    occurrences = {}
    header_rows = []
    for page in pdf.pages:
        rows = []
        for y, words in _agrupar_palavras_por_linha(page.extract_words()):
            line = " ".join(word['text'] for word in sorted(words, key=lambda word: word['x0']))
            if y < page.height * .075:
                rows.append((line, y - 1, max(word['bottom'] for word in words) + 1))
                occurrences.setdefault(line, set()).add(page.page_number)
        header_rows.append(rows)
    repeated = {line for line, pages in occurrences.items() if len(pages) >= 3}
    pages, profiles = [], []
    started = False
    for page, raw, rows in zip(pdf.pages, texts, header_rows):
        has_boxes = len(CAIXA.findall(raw)) >= 3
        if started and not has_boxes and re.search(r"(?im)^\s*(?:Reda[çc][aã]o|PROVA DISCURSIVA)\s*$", raw):
            break
        filtered = _pagina_sem_texto_rotacionado(page)
        if has_boxes:
            started = True
            bands = [(top, bottom) for line, top, bottom in rows if line in repeated]
            filtered = filtered.filter(lambda obj: obj.get('object_type') != 'char'
                or not any(top <= obj.get('top', -1) <= bottom for top, bottom in bands))
            text = _extrair_texto_colunas(filtered)
            # Seção impressa: conservar para classificação, com separação
            # explícita da contagem que não pertence à alternativa anterior.
            text = re.sub(r"(?im)^([^\n]+?)\s+(\d+\s+quest[õo]es)\s*$", r"\1 | \2", text)
            profile = 'pdf_caixas_duas_colunas_v1'
        else:
            text = filtered.extract_text(x_tolerance=2, y_tolerance=3) or ''
            profile = 'pdf_linear_v1'
        pages.append(_normalizar_pagina(text))
        profiles.append({'pagina': page.page_number, 'perfil': profile})
    return TextoExtraido('\n'.join(pages), 'pdf_caixas_duas_colunas_v1',
        ['Confira tabelas e fórmulas nos recortes da fonte.'], profiles)
