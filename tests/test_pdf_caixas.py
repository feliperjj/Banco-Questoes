"""Referências físicas do caderno EPAGRI/S201, sem usar o gabarito como texto."""
from pathlib import Path

from src.importador.pdf_texto import extrair_texto_pdf
from src.importador.parser import parsear_questoes
from src.importador.pdf_fonte import extract_pdf_source
from src.models.provenance_service import _norm_source_text


def test_barra_de_secao_e_identificada_antes_de_dividir_colunas(tmp_path):
    import pdfplumber
    from test_importacao_lote_verificado import _write_text_pdf
    from src.importador.perfis.pdf_paginas import limpar_cabecalhos_julgamento
    source = _write_text_pdf(tmp_path / 'heading.pdf', [
        'CEBRASPE - Edital: 2024', 'O candidato precisa de conhecimentos gerais completos.'
    ], graphics=b'BT /F1 15 Tf 200 600 Td (-- CONHECIMENTOS GERAIS --) Tj ET')
    with pdfplumber.open(source) as pdf:
        page, body_top = limpar_cabecalhos_julgamento(pdf.pages[0])
        text = page.extract_text()
        assert body_top > 170
        assert 'CONHECIMENTOS GERAIS' not in text
        assert 'conhecimentos gerais completos' in text


def test_marca_de_download_na_borda_e_removida_antes_das_colunas(tmp_path):
    import pdfplumber
    from test_importacao_lote_verificado import _write_text_pdf
    from src.importador.pdf_texto import _pagina_sem_texto_rotacionado
    source = _write_text_pdf(tmp_path / 'download.pdf', ['Texto completo que deve permanecer.'],
        graphics=b'BT /F1 8 Tf 10 785 Td (pcimarkpci METADADOS_DO_DOWNLOAD) Tj ET')
    with pdfplumber.open(source) as pdf:
        clean = _pagina_sem_texto_rotacionado(pdf.pages[0])
        assert 'METADADOS_DO_DOWNLOAD' not in clean.extract_text()
        assert 'Texto completo que deve permanecer.' in clean.extract_text()


def test_contexto_com_dois_comandos_exige_identificador_e_ordem_exatos():
    from src.importador.pdf_fonte import _context_with_repeated_command
    passage = 'Texto X123\n' + 'Passagem completa com informações para julgamento. ' * 12
    first = passage + 'Julgue os itens referentes ao texto X123.'
    second = 'Julgue os seguintes itens, relativos ao texto X123.'
    pool = [{'text': first, 'raw_text': first}, {'text': second, 'raw_text': second}]
    hit = _context_with_repeated_command(first + '\n' + second, pool)
    assert hit and hit[0] == pool
    assert _context_with_repeated_command(first + '\n' + second.replace('X123', 'X999'), pool) is None
    assert _context_with_repeated_command(first + '\n' + second, list(reversed(pool))) is None
    assert _context_with_repeated_command(first + '\n' + second, pool[:1]) is None
    wrapped = second.replace('texto X123.', '\ntexto X123.')
    assert _context_with_repeated_command(first + '\n' + second,
        [pool[0], {'text': wrapped, 'raw_text': wrapped}]) is not None


def test_ocr_nao_reintroduz_cabecalho_repetido_na_pagina_final(tmp_path, monkeypatch):
    from test_importacao_continuacao import write_pages
    from src.importador.perfis.pdf_paginas import LeitorOCR
    header = 'INSTITUTO ' + 'I' * 125
    pages = []
    for number in (1, 2):
        pages.append([header, f'QUESTAO {number}', 'Enunciado completo para esta pergunta.'] +
                     [f'{letter}) Opcao {letter}.' for letter in 'ABCDE'])
    pages.append([header])
    path = write_pages(tmp_path / 'repeated.pdf', pages)
    crops = []
    monkeypatch.setattr(LeitorOCR, 'ler', lambda self, page: (crops.append(page.bbox) or '', 'Pagina vazia no teste.'))
    text = extrair_texto_pdf(str(path))
    assert header not in text
    assert len(crops) == 1 and crops[0][1] > 50
    questions = parsear_questoes(text)
    assert [q['numero'] for q in questions] == [1, 2]
    assert questions[-1]['alternativas'][-1]['texto'] == 'Opcao E.'


def test_pagina_ocr_so_e_identificacao_quando_todas_as_linhas_sao_metadados():
    from src.importador.pdf_texto import _apenas_identificacao
    footer = 'AGENTEADMINISTRATIVOI\nPagina 12 de 12\nwww.pciconcursos.com.br'
    assert _apenas_identificacao(footer, ('Agente Administrativo I',))
    assert not _apenas_identificacao(footer, ('Analista',))
    assert not _apenas_identificacao(footer + '\nQUESTAO 40\nEnunciado que deve ser preservado.', ('Agente Administrativo I',))


def test_remover_bordas_preserva_metadados_e_nao_anexa_rodape(tmp_path):
    from test_importacao_continuacao import write_pages
    header = 'CONCURSO PUBLICO 2024 FGV'
    footer = 'EXECUCAO DO CONCURSO FGV'
    pages = []
    for number in (1, 2, 3):
        # A quantidade de linhas coloca o rodapé na margem inferior.
        pages.append([header, f'QUESTAO {number}', 'Complete statement for this question.'] +
                     [f'{a}) Option {a}.' for a in 'ABCDE'] + [''] * 30 + [footer])
    text = extrair_texto_pdf(str(write_pages(tmp_path / 'metadata.pdf', pages)), usar_ocr=False)
    questions = parsear_questoes(text)
    assert len(questions) == 3
    assert all(q['banca'] == 'FGV' and q['ano'] == 2024 for q in questions)
    assert all(q['alternativas'][-1]['texto'] == 'Option E.' for q in questions)


def test_numero_interno_nao_reclassifica_questao_anterior():
    from src.importador.parser import extrair_metadados_prova
    data = extrair_metadados_prova('Língua Portuguesa\nQUESTÃO 1\nEnunciado original.\n'
        'Raciocínio Lógico Matemático\nQUESTÃO 2\nAnalise:\n1\nUma afirmação numerada interna.')
    assert data['disciplinas'][1] == 'Língua Portuguesa'
    assert data['disciplinas'][2] == 'Raciocínio Lógico e Matemática'


def test_apoio_relativo_depois_de_outra_questao_tem_limites_proprios(tmp_path):
    from test_importacao_continuacao import write_pages
    passage = 'READ TEXT II AND ANSWER NEXT TWO QUESTIONS.\nTEXT II\nShared article with complete original information.'
    lines = ['QUESTAO 1', 'Previous unrelated statement.'] + [f'{a}) Previous {a}.' for a in 'ABCDE']
    lines += passage.splitlines() + ['QUESTAO 2', 'Choose according to the shared article.']
    lines += [f'{a}) Second {a}.' for a in 'ABCDE']
    path = write_pages(tmp_path / 'relative.pdf', [lines])
    questions = [{'numero': 1, 'enunciado': 'Previous unrelated statement.'},
                 {'numero': 2, 'enunciado': 'Choose according to the shared article.', 'texto_apoio': passage}]
    geometry = extract_pdf_source(path, expected_questions=questions)
    item = next(q for q in geometry['questions'] if q['numero'] == 2)
    assert len(item['context_regions']) == 1
    assert 'Shared article with complete original information.' in item['texto_apoio']
    assert 'Previous unrelated statement' not in item['texto_apoio']
    assert 'Choose according' not in item['texto_apoio']


def test_caderno_caixas_preserva_50_itens_sem_cabecalho_redacao_ou_cortes():
    source = Path(__file__).resolve().parents[1] / 'samples/agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf'
    text = extrair_texto_pdf(str(source))
    assert text.perfil == 'pdf_caixas_duas_colunas_v1'
    questions = parsear_questoes(text)
    assert [q['numero'] for q in questions] == list(range(1, 51))
    assert len(text.paginas) == 10  # A redação começa na página 11.
    geometry = extract_pdf_source(source, expected_questions=questions)
    assert geometry['issues'] == []
    by_number = {q['numero']: q for q in geometry['questions']}
    for question in questions:
        item = by_number[question['numero']]
        assert item['checks']['anchor_confirmed']
        original = _norm_source_text(item['enunciado_original'])
        for term in [question['enunciado']] + [a['texto'] for a in question['alternativas']]:
            assert _norm_source_text(term) in original, (question['numero'], term)
        assert [a['letra'] for a in question['alternativas']] == list('ABCDE')
        assert all('Check-square' not in a['texto'] and 'cód. vaga' not in a['texto'] for a in question['alternativas'])
    assert questions[11]['enunciado'].endswith('Logo, o número de pessoas no referido grupo é:')
    assert questions[13]['enunciado'].endswith('Logo, esse número é:')
    assert questions[9]['alternativas'][-1]['texto'].endswith('usucapião.')
    assert questions[19]['alternativas'][-1]['texto'] == '80.'
    assert questions[-1]['alternativas'][-1]['texto'] == 'Os projetistas devem evitar depender de coisas que não usam.'
    assert all('Fragmento adaptado.' in questions[n-1]['texto_apoio'] for n in (1, 2, 3))
