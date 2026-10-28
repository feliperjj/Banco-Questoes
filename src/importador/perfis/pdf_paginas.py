"""Perfis de leitura de página: separadores geométricos e imagem digitalizada."""
import re


def limpar_cabecalhos_julgamento(pagina):
    """Retira barras de seção que cruzam a medianiz antes de ler colunas."""
    if not hasattr(pagina, 'extract_words') or not hasattr(pagina, 'filter'):
        return pagina, 0.0
    from ..pdf_texto import _agrupar_palavras_por_linha
    bands, body_top = [], 0.0
    for top, words in _agrupar_palavras_por_linha(pagina.extract_words(x_tolerance=2, y_tolerance=3)):
        text = ' '.join(word['text'] for word in sorted(words, key=lambda word: word['x0']))
        section = re.fullmatch(r'[-–— ]*CONHECIMENTOS\s+(GERAIS|B[ÁA]SICOS|COMPLEMENTARES|ESPEC[ÍI]FICOS)[-–— ]*', text)
        spans = min(word['x0'] for word in words) < pagina.width / 2 < max(word['x1'] for word in words)
        if section and spans and top < pagina.height * .35:
            bottom = max(word['bottom'] for word in words)
            bands.append((top - 1, bottom + 1))
            body_top = max(body_top, bottom + 1)
        elif top < pagina.height * .06 and re.match(r'^CEBRASPE\b', text) and re.search(r'(?i)edital', text):
            bands.append((top - 1, max(word['bottom'] for word in words) + 1))
    if bands:
        pagina = pagina.filter(lambda obj: obj.get('object_type') != 'char'
            or not any(top <= obj.get('top', -1) <= bottom for top, bottom in bands))
    return pagina, body_top


class TextoExtraido(str):
    def __new__(cls, texto, perfil='pdf_adaptativo_v2', avisos=(), paginas=()):
        obj = super().__new__(cls, texto)
        obj.perfil, obj.avisos, obj.paginas = perfil, tuple(avisos), tuple(paginas)
        return obj


def colunas_por_separadores(pagina, topo=0):
    """Aceita 2/3 colunas apenas com separadores longos e sem texto atravessado."""
    linhas = list(getattr(pagina, 'lines', ())) + list(getattr(pagina, 'rects', ()))
    candidatos = sorted({round(l['x0'], 1) for l in linhas
                         if abs(l['x0']-l['x1']) < 2 and l['bottom']-l['top'] > pagina.height*.4
                         and .2*pagina.width < l['x0'] < .8*pagina.width})
    cortes=[]
    for x in candidatos:
        if not cortes or x-cortes[-1]>5:
            cortes.append(x)
    if len(cortes) not in (1,2):
        return None
    words=pagina.extract_words(x_tolerance=2,y_tolerance=3)
    if any(w['top'] >= topo and w['x0'] < x-3 and w['x1'] > x+3 for w in words for x in cortes):
        return None
    limites=[0]+cortes+[pagina.width]
    if min(b-a for a,b in zip(limites,limites[1:])) < pagina.width*.2:
        return None
    textos=[pagina.crop((a,topo,b,pagina.height)).extract_text(x_tolerance=2,y_tolerance=3) or ''
            for a,b in zip(limites,limites[1:])]
    marcadores=sum(len(re.findall(r'(?im)^\s*(?:QUEST(?:ÃO|AO)\s*)?\d{1,3}(?:[.)\s])',t)) for t in textos)
    if marcadores<3:
        return None
    return '\n'.join(textos), f'pdf_{len(textos)}_colunas_separadas_v1'


class LeitorOCR:
    """Instância local reutilizada; só é criada se houver página sem texto."""
    def __init__(self):
        self.motor = None

    def ler(self, pagina):
        try:
            import numpy as np
            from rapidocr_onnxruntime import RapidOCR
            if self.motor is None:
                self.motor = RapidOCR()
            from src.importador.pdf_render import render_page_image
            imagem=np.array(render_page_image(pagina, resolution=180))
            deteccoes,_=self.motor(imagem)
            if not deteccoes:
                return '', 'OCR não reconheceu texto nesta página.'
            # Não intercalar colunas: para imagens sem geometria PDF, a saída
            # é conservadora e explicitamente requer revisão de leitura.
            linhas=sorted(deteccoes,key=lambda d:(round(min(p[1] for p in d[0])/10),min(p[0] for p in d[0])))
            texto='\n'.join(str(d[1]) for d in linhas)
            return texto, 'Página lida por OCR; confira caracteres, colunas e numeração no PDF.'
        except (ImportError, RuntimeError, ValueError, OSError) as exc:
            return '', f'OCR indisponível ou falhou ({type(exc).__name__}); página requer revisão.'
