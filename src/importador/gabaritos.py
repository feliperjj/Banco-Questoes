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
    ExtratorItensCE,
    ExtratorPadrao,
    _extrair_duas_linhas,
    _extrair_itens_certo_errado,
    _extrair_pares_mesma_linha,
    selecionar_extrator,
)
from .perfis.documentos import classificar_gabarito, segmentar_blocos_gabarito
import logging
import re
import unicodedata

import pdfplumber


logger = logging.getLogger(__name__)


from .pdf_texto import _corrigir_encoding_ocr


def diagnosticar_gabarito_pdf(caminho: str) -> dict:
    """Classifica o layout de cada página e lista os blocos identificáveis."""
    paginas = []
    textos = []
    with pdfplumber.open(caminho) as pdf:
        for indice, pagina in enumerate(pdf.pages):
            texto = _corrigir_encoding_ocr(pagina.extract_text() or "")
            if not texto.strip():
                continue
            textos.append(texto)
            perfil = classificar_gabarito(texto)
            blocos = segmentar_blocos_gabarito(texto)
            paginas.append({
                "pagina": indice + 1,
                "perfil": perfil.padrao,
                "familia": perfil.familia,
                "evidencias": list(perfil.evidencias),
                "codigos": list(perfil.identificadores),
                "metadados": perfil.metadados or {},
                "intervalo_questoes": list(perfil.intervalo_questoes),
                "quantidade_respostas": perfil.quantidade_respostas,
                "blocos": [b.identificador for b in blocos if b.identificador],
            })
    perfil_completo = classificar_gabarito("\n".join(textos))
    perfis = sorted({p["perfil"] for p in paginas})
    return {
        "arquivo": caminho,
        "perfis": perfis,
        "padrao_predominante": perfil_completo.padrao,
        "familia": perfil_completo.familia,
        "codigos": list(perfil_completo.identificadores),
        "metadados": perfil_completo.metadados or {},
        "intervalo_questoes": list(perfil_completo.intervalo_questoes),
        "quantidade_respostas": perfil_completo.quantidade_respostas,
        "paginas": paginas,
    }


def extrair_gabaritos_pdf(
    caminho: str,
    codigo_prova: str | None = None,
    cargo: str | None = None,
    *,
    usar_ocr: bool = True,
    numeros_esperados: set[int] | None = None,
    perfil_escolhido: str | None = None,
    perfis_paginas: dict[int, str] | None = None,
    versao: str | None = None,
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
    escolhas_paginas = {int(n): perfil for n, perfil in (perfis_paginas or {}).items()}
    perfis_paginas = []
    textos = []
    tabelas = MapaGabarito()
    contexto = FiltroContexto(codigo_prova, cargo, versao)
    with pdfplumber.open(caminho) as pdf:
        for numero_pagina, pagina in enumerate(pdf.pages):
            texto = _corrigir_encoding_ocr(pagina.extract_text() or "")
            if not texto.strip():
                grade = _extrair_grade_identificada(pagina, texto, codigo_prova, cargo)
                perfis_paginas.append({"pagina": numero_pagina + 1, "perfil": "sem_texto", "selecionado": "sem_texto"})
                # A seleção de páginas escaneadas depende do cabeçalho lido
                # pelo OCR; não descartar antes de poder verificar o contexto.
                paginas_relevantes.append(numero_pagina)
                if grade is not None:
                    gabaritos.incorporar(grade)
                continue
            textos.append(texto)
            if not contexto.pagina_relevante(texto):
                continue
            grade = _extrair_grade_identificada(pagina, texto, codigo_prova, cargo)
            # A leitura geométrica pode capturar só as marcações anuladas em
            # gabaritos tabulares. Mantê-la como complemento permite que o
            # extrator textual do perfil complete primeiro a sequência inteira.
            perfil_pagina = classificar_gabarito(texto)
            escolhido = escolhas_paginas.get(numero_pagina + 1) or perfil_escolhido
            perfis_paginas.append({"pagina": numero_pagina + 1, "perfil": perfil_pagina.padrao,
                                   "selecionado": escolhido or perfil_pagina.padrao})
            if escolhido and escolhido != perfil_pagina.padrao:
                gabaritos.avisos.append(
                    f"Perfil {escolhido} incompatível com a estrutura da página {numero_pagina + 1}; página mantida pendente."
                )
                continue
            if grade is not None:
                tabelas.incorporar(grade)
            linhas = [re.sub(r"\s+", " ", linha).strip() for linha in texto.splitlines()]
            paginas_relevantes.append(numero_pagina)
            linhas_filtradas = contexto.linhas_do_cargo(linhas)
            # Tabelas da página inteira não podem reintroduzir outro cargo.
            if linhas_filtradas == linhas:
                tabelas.incorporar(_extrair_gabaritos_tabelas(pagina))
            linhas = linhas_filtradas
            resultado = selecionar_extrator(
                texto, "Prova " + contexto.versao if contexto.versao else contexto.codigo_prova, contexto.cargo_normalizado,
                perfil=escolhido or perfil_pagina.padrao,
            ).extrair(linhas)
            if resultado or getattr(resultado, "conflitos", None):
                gabaritos.incorporar(resultado)
                continue
    logger.info("Gabarito extraído: %s itens de %s", len(gabaritos), caminho)
    # Tabelas complementam o texto; nunca substituem uma resposta textual.
    gabaritos.complementar(tabelas)
    faltantes = set(numeros_esperados or ()) - set(gabaritos) - set(gabaritos.conflitos)
    perfil_documento = classificar_gabarito("\n".join(textos)) if textos else None
    metadata = perfil_documento.metadados or {} if perfil_documento else {}
    from .perfis.documentos import versao_da_selecao
    selecoes = {"cargo": cargo, "codigo": codigo_prova, "versao": versao or versao_da_selecao(codigo_prova)}
    escopo_pendente = any(len(values) > 1 and not selecoes.get(name) for name, values in metadata.items()
                          if name in selecoes)
    # Sem números esperados, OCR é fallback apenas para extração vazia. Isso
    # evita completar um gabarito curto e íntegro com ruído de outras páginas.
    precisa_ocr = usar_ocr and bool(paginas_relevantes) and not escopo_pendente and (
        not gabaritos and not gabaritos.conflitos or bool(faltantes))
    if precisa_ocr:
        resultado_ocr = (_ocr or _extrair_gabaritos_ocr)(
            caminho, cargo=cargo, codigo_prova=codigo_prova, indices_paginas=paginas_relevantes,
        )
        gabaritos.complementar(resultado_ocr, numeros_esperados)
    gabaritos.perfis_paginas = perfis_paginas
    gabaritos.perfil_documento = perfil_documento
    gabaritos.perfil_escolhido = perfil_escolhido
    gabaritos.selecao_escopo = {"codigo": codigo_prova or "", "cargo": cargo or "", "versao": contexto.versao}
    return gabaritos


