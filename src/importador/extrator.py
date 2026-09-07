"""API pública de importação; implementações separadas por etapa e formato."""
import os
import pdfplumber  # Compatibilidade para integrações que injetam o leitor PDF.
from . import gabaritos
from .pdf_texto import (
    _normalizar_pagina,
    _corrigir_encoding_ocr,
    _linhas_repetidas,
    _pagina_sem_texto_rotacionado,
    _extrair_texto_area,
    _extrair_texto_colunas,
    _agrupar_palavras_por_linha,
    _topo_primeira_secao,
    _parece_pagina_de_questoes,
    _tem_duas_colunas,
    extrair_texto_pdf,
)
from .gabaritos import (
    _texto_comparavel,
    _extrair_gabaritos_tabelas,
    _extrair_pares_mesma_linha,
    _extrair_itens_certo_errado,
    _extrair_duas_linhas,
    ExtratorBanca,
    ExtratorPadrao,
    ExtratorMultiprova,
    selecionar_extrator,
    FiltroContexto,
    _extrair_grade_identificada,
    _agrupar_indices_consecutivos,
    _detectar_cabecalho_y,
    _detectar_grade,
    _ler_celula,
    _extrair_pares_ocr,
    _extrair_gabaritos_ocr,
)
from .docx_texto import extrair_texto_docx

def extrair_gabaritos_pdf(caminho, codigo_prova=None, cargo=None, *, usar_ocr=True, numeros_esperados=None):
    return gabaritos.extrair_gabaritos_pdf(caminho, codigo_prova, cargo,
        usar_ocr=usar_ocr, numeros_esperados=numeros_esperados, _ocr=_extrair_gabaritos_ocr)


def extrair_texto(caminho: str) -> str:
    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".pdf":
        return extrair_texto_pdf(caminho)
    if ext == ".docx":
        return extrair_texto_docx(caminho)
    raise ValueError(f"Formato não suportado: {ext}. Use PDF ou DOCX.")
