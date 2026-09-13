from .perfis.gabaritos_contexto import FiltroContexto, _texto_comparavel
from .perfis.gabaritos_ocr import (
    _agrupar_indices_consecutivos,
    _detectar_cabecalho_y,
    _detectar_grade,
    _ler_celula,
    _extrair_pares_ocr,
    _extrair_gabaritos_ocr,
)
from .perfis.gabaritos_grades import _extrair_grade_identificada, _extrair_gabaritos_tabelas
from .perfis.gabaritos_texto import (
    ExtratorBanca,
    ExtratorMultiprova,
    ExtratorPadrao,
    _extrair_duas_linhas,
    _extrair_itens_certo_errado,
    _extrair_pares_mesma_linha,
    selecionar_extrator,
)
import logging
import re
import unicodedata

import pdfplumber


logger = logging.getLogger(__name__)


from .pdf_texto import _corrigir_encoding_ocr


def extrair_gabaritos_pdf(
    caminho: str,
    codigo_prova: str | None = None,
    cargo: str | None = None,
    *,
    usar_ocr: bool = True,
    numeros_esperados: set[int] | None = None,
    _ocr=None,
) -> dict[int, str]:
    """Extrai o mapa questão -> resposta, respeitando cargo/código quando informado.

    PDFs de concursos frequentemente juntam vários cargos no mesmo arquivo de
    gabarito. ``cargo`` funciona como seletor de contexto e impede que a
    resposta de outro cargo sobrescreva a resposta do caderno importado.
    ``codigo_prova`` mantém compatibilidade com o fluxo da UI.
    """
    from .perfis.gabaritos_resultado import MapaGabarito
    gabaritos = MapaGabarito()
    paginas_relevantes = []
    tabelas = MapaGabarito()
    contexto = FiltroContexto(codigo_prova, cargo)
    with pdfplumber.open(caminho) as pdf:
        for numero_pagina, pagina in enumerate(pdf.pages):
            texto = _corrigir_encoding_ocr(pagina.extract_text() or "")
            if not texto.strip():
                # A seleção de páginas escaneadas depende do cabeçalho lido
                # pelo OCR; não descartar antes de poder verificar o contexto.
                paginas_relevantes.append(numero_pagina)
                continue
            grade = _extrair_grade_identificada(pagina, texto, codigo_prova, cargo)
            if grade is not None:
                gabaritos.incorporar(grade)
                continue
            if not contexto.pagina_relevante(texto):
                continue
            linhas = [re.sub(r"\s+", " ", linha).strip() for linha in texto.splitlines()]
            paginas_relevantes.append(numero_pagina)
            linhas_filtradas = contexto.linhas_do_cargo(linhas)
            # Tabelas da página inteira não podem reintroduzir outro cargo.
            if linhas_filtradas == linhas:
                tabelas.incorporar(_extrair_gabaritos_tabelas(pagina))
            linhas = linhas_filtradas
            resultado = selecionar_extrator(
                texto, contexto.codigo_prova, contexto.cargo_normalizado,
            ).extrair(linhas)
            if resultado or getattr(resultado, "conflitos", None):
                gabaritos.incorporar(resultado)
                continue
    logger.info("Gabarito extraído: %s itens de %s", len(gabaritos), caminho)
    # Tabelas complementam o texto; nunca substituem uma resposta textual.
    gabaritos.complementar(tabelas)
    faltantes = set(numeros_esperados or ()) - set(gabaritos)
    # Sem números esperados, OCR é fallback apenas para extração vazia. Isso
    # evita completar um gabarito curto e íntegro com ruído de outras páginas.
    precisa_ocr = usar_ocr and (not gabaritos or bool(faltantes))
    if precisa_ocr:
        resultado_ocr = (_ocr or _extrair_gabaritos_ocr)(
            caminho, cargo=cargo, codigo_prova=codigo_prova, indices_paginas=paginas_relevantes,
        )
        gabaritos.complementar(resultado_ocr, numeros_esperados)
    return gabaritos


