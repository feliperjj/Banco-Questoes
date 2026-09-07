"""Leitura DOCX em ordem documental, incluindo tabelas intercaladas."""
import docx
from docx.table import Table
from docx.text.paragraph import Paragraph


def extrair_texto_docx(caminho):
    documento = docx.Document(caminho)
    def blocos(parent):
        elemento = parent.element.body if hasattr(getattr(parent, 'element', None), 'body') else parent._tc
        for filho in elemento.iterchildren():
            if filho.tag.endswith('}p'):
                texto = Paragraph(filho, parent).text.strip()
                if texto:
                    yield texto
            elif filho.tag.endswith('}tbl'):
                vistos = set()
                for linha in Table(filho, parent).rows:
                    for celula in linha.cells:
                        if celula._tc in vistos:
                            continue
                        vistos.add(celula._tc)
                        yield from blocos(celula)
    return '\n'.join(blocos(documento))
