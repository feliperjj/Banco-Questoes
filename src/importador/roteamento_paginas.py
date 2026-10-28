"""Inspeção e roteamento explícito de páginas, preservando blocos contínuos."""
import pdfplumber
import re

from .perfis.documentos import classificar_caderno
from .pdf_texto import _normalizar_pagina, _tem_duas_colunas, _extrair_texto_colunas
from .parser import QuestoesExtraidas, parsear_questoes


def inspecionar_paginas(caminho):
    result = []
    with pdfplumber.open(caminho) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            if text.strip():
                words = page.extract_words(x_tolerance=2, y_tolerance=3)
                if _tem_duas_colunas(words, page.width):
                    text = _extrair_texto_colunas(page)
            text = _normalizar_pagina(text)
            profile = classificar_caderno(text) if text else None
            strong = bool(profile and (
                profile.familia == "multipla_escolha" and len(re.findall(r"(?im)^\s*\(?[A-E][).:-]\s", text)) >= 4
                or profile.familia == "certo_errado" and re.search(r"(?i)TEXTO\s+DE\s+APOIO", text)
                and re.search(r"(?i)ITEM\s+PARA\s+JULGAMENTO", text)))
            result.append({"pagina": number, "perfil": profile.padrao if profile else "sem_texto",
                "familia": profile.familia if profile else "desconhecida", "texto": text,
                "candidatos": list(profile.candidatos) if profile else [],
                "assinatura_forte": strong,
                "aviso": profile.aviso if profile else "Página sem texto; conferir OCR e original."})
    return result


def parsear_paginas(pages, source, selections):
    known = {page["pagina"] for page in pages}
    if set(selections) - known:
        raise ValueError("A seleção de leitura referencia uma página inexistente.")
    groups = []
    warnings = []
    initial = next((page["perfil"] for page in pages if page.get("assinatura_forte")), None)
    for page in pages:
        if not page["texto"]:
            warnings.append(f"Página {page['pagina']}: sem texto; não foi considerada íntegra pelo roteamento.")
            continue
        selected = selections.get(page["pagina"]) or page["perfil"]
        if page["pagina"] in selections and page.get("assinatura_forte"):
            from .perfis.segmentacao import segmentar
            from .perfis.registro import obter_perfil
            registered = obter_perfil(selected)
            compatible = registered and registered.familia == page["familia"]
            segmented = segmentar(page["texto"], page["texto"], perfil_escolhido=selected) if compatible else None
            if not segmented or not segmented.candidatos:
                warnings.append(f"Página {page['pagina']}: perfil escolhido incompatível; conteúdo mantido pendente para conferência.")
                continue
        # Continuação sem novo marcador acompanha o bloco anterior. Não
        # recomeçar a numeração nem perder uma alternativa na quebra de página.
        if not page.get("assinatura_forte") and page["pagina"] not in selections:
            selected = groups[-1][0] if groups else initial or selected
        if groups and groups[-1][0] == selected:
            groups[-1][1].append(page)
        else:
            groups.append((selected, [page]))
    questions, instructions = [], []
    for profile, group in groups:
        parsed = parsear_questoes("\n".join(page["texto"] for page in group), source,
                                  perfil_escolhido=profile)
        if not parsed:
            warnings.append(f"Páginas {', '.join(str(p['pagina']) for p in group)}: leitura escolhida não reconheceu questões; confira o perfil e o original.")
        for question in parsed:
            question["paginas_importacao"] = [page["pagina"] for page in group]
        questions.extend(parsed)
        if parsed.instrucoes_prova:
            instructions.append(parsed.instrucoes_prova)
    return QuestoesExtraidas(questions, instrucoes_prova="\n\n".join(dict.fromkeys(instructions))), warnings
