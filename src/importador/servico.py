"""Fluxo híbrido de importação, sem acesso ao banco de dados."""
from collections import Counter
from .extrator import extrair_texto
from .parser import parsear_questoes, quantidade_declarada
from .validacao import problemas_estrutura


class LoteImportado(list):
    def __init__(self, questoes, relatorio):
        super().__init__(questoes)
        self.relatorio = relatorio
        self.avisos = relatorio['avisos']


def importar_caderno(caminho):
    texto = extrair_texto(caminho)
    qs = parsear_questoes(texto, caminho)
    contagem = Counter(q['numero'] for q in qs)
    duplicados = sorted(n for n,c in contagem.items() if c>1)
    declarada = quantidade_declarada(texto)
    faltantes = sorted(set(range(1, (declarada or max(contagem,default=0))+1))-set(contagem))
    avisos = list(getattr(texto,'avisos',()))
    if duplicados:
        avisos.append('Numeração repetida: '+', '.join(map(str,duplicados)))
    if faltantes:
        avisos.append('Números não reconhecidos (ou ausentes neste recorte): '+', '.join(map(str,faltantes)))
    if declarada and len(qs)!=declarada:
        avisos.append(f'A fonte declara {declarada} questões; foram reconhecidas {len(qs)}.')
    for q in qs:
        problemas = problemas_estrutura(q)
        if problemas:
            q['aviso_importacao'] = ' '.join(filter(None,[q.get('aviso_importacao'), *problemas]))
            q['confianca'] = 'baixa'
    relatorio = dict(arquivo=str(caminho), quantidade=len(qs), declarada=declarada,
        perfis=sorted({q['perfil_importacao'] for q in qs}),
        extracao=getattr(texto,'perfil','docx_documental_v2'),
        paginas=list(getattr(texto,'paginas',())), duplicados=duplicados, faltantes=faltantes,
        avisos=list(dict.fromkeys(avisos)),
        questoes_com_avisos=[q['numero'] for q in qs if q.get('aviso_importacao')])
    return LoteImportado(qs,relatorio)
