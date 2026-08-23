"""Templates de gabarito usados pelos layouts presentes em ``samples``.

O template descreve a geometria, não o conteúdo da prova. Isso evita espalhar
coordenadas calibradas pelo OCR e permite adicionar um novo layout sem alterar
o parser de questões.
"""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class GabaritoTemplate:
    nome: str
    tipo: str
    resolucao: int = 180
    colunas: int = 20
    linhas: int = 4
    marcador: str = ""


TEMPLATE_CEBRASPE = GabaritoTemplate(
    nome="cebraspe_grade_4x20", tipo="grade", resolucao=180, colunas=20, linhas=4,
)
TEMPLATE_PARES = GabaritoTemplate(nome="pares_textuais", tipo="pares")
TEMPLATE_TABELA_HORIZONTAL = GabaritoTemplate(nome="tabela_horizontal", tipo="tabela_horizontal")
TEMPLATE_TABELA_VERTICAL = GabaritoTemplate(nome="tabela_vertical", tipo="tabela_vertical")
TEMPLATE_MULTIPROVAS = GabaritoTemplate(nome="multiplas_provas", tipo="multiplas_provas")


def selecionar_template(caminho: str, texto: str = "") -> GabaritoTemplate:
    """Seleciona o layout por evidência do arquivo/cabeçalho.

    O nome do arquivo é apenas um fallback de layout; cargo e respostas nunca
    são inferidos por aproximação aqui.
    """
    contexto = f"{Path(caminho).name} {texto}".casefold()
    if "cebraspe" in contexto:
        return TEMPLATE_CEBRASPE
    if re.search(r"prova\s*1", contexto) and re.search(r"prova\s*2", contexto):
        return TEMPLATE_MULTIPROVAS
    if re.search(r"\bitem\b", contexto) and re.search(r"\b(?:certo|errado)\b", contexto):
        return TEMPLATE_TABELA_VERTICAL
    if "gabarito" in contexto and "resposta" in contexto:
        return TEMPLATE_TABELA_HORIZONTAL
    return TEMPLATE_PARES
