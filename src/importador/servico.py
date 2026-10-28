"""Fluxo híbrido de importação, sem acesso ao banco de dados."""
from collections import Counter
from pathlib import Path
from src.config import ROOT_DIR, TEST_MODE, TEST_ROOT
from .extrator import extrair_texto
from .parser import parsear_questoes, quantidade_declarada
from .validacao import problemas_estrutura


class LoteImportado(list):
    def __init__(self, questoes, relatorio, instrucoes_prova="", perfil_documento=None):
        super().__init__(questoes)
        self.relatorio = relatorio
        self.avisos = relatorio['avisos']
        self.instrucoes_prova = instrucoes_prova
        self.perfil_documento = perfil_documento


def importar_caderno(caminho, *, perfil_escolhido=None, perfis_paginas=None):
    texto = extrair_texto(caminho)
    from .perfis.documentos import classificar_caderno
    reconhecimento = classificar_caderno(texto)
    paginas, avisos_roteamento = [], []
    escolhas = {int(n): value for n, value in (perfis_paginas or {}).items()}
    if Path(caminho).suffix.lower() == ".pdf":
        # A remoção de cabeçalhos repetidos do corpo pode também retirar o
        # cargo da capa. Inspecionar a capa original preserva sua identidade.
        from dataclasses import replace
        import pdfplumber
        from .perfis.documentos import _metadados
        with pdfplumber.open(caminho) as document:
            header = _metadados(document.pages[0].extract_text() or '') if document.pages else {}
        merged = {key: tuple(sorted(set((reconhecimento.metadados or {}).get(key, ())) | set(header.get(key, ()))))
                  for key in set(reconhecimento.metadados or {}) | set(header)}
        reconhecimento = replace(reconhecimento, metadados=merged)
        from .roteamento_paginas import inspecionar_paginas, parsear_paginas
        paginas = inspecionar_paginas(caminho)
    familias = {page["familia"] for page in paginas if page["assinatura_forte"]}
    misto = len(familias) > 1
    if escolhas or (misto and not perfil_escolhido):
        qs, avisos_roteamento = parsear_paginas(paginas, caminho, escolhas)
    else:
        qs = parsear_questoes(texto, caminho, perfil_escolhido=perfil_escolhido)
    perfis_extraidos = [q.get("perfil_importacao") for q in qs if q.get("perfil_importacao")]
    perfil_usado = perfil_escolhido or (max(set(perfis_extraidos), key=perfis_extraidos.count) if perfis_extraidos else reconhecimento.padrao)
    imagens_extraidas = 0
    if Path(caminho).suffix.lower() == ".pdf":
        from .imagens import anexar_imagens_referenciadas
        raiz = TEST_ROOT if TEST_MODE else ROOT_DIR
        imagens_extraidas = anexar_imagens_referenciadas(caminho, qs, raiz)
    contagem = Counter(q['numero'] for q in qs)
    duplicados = sorted(n for n,c in contagem.items() if c>1)
    declarada = quantidade_declarada(texto)
    faltantes = sorted(set(range(1, (declarada or max(contagem,default=0))+1))-set(contagem))
    avisos = list(getattr(texto,'avisos',())) + avisos_roteamento
    if perfil_escolhido and not qs:
        avisos.append("O perfil escolhido não reconheceu questões verificáveis. Confira a leitura por página e o PDF original.")
    if misto:
        avisos.append("O caderno apresenta famílias diferentes por página. Confira as leituras e os limites dos blocos.")
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
        reconhecimento={"papel": reconhecimento.tipo, "perfil": reconhecimento.padrao,
            "perfil_usado": perfil_usado, "familia": reconhecimento.familia,
            "candidatos": list(reconhecimento.candidatos), "evidencias": list(reconhecimento.evidencias),
            "estado": "nao_suportado" if not qs or perfil_usado == "generico_v1" else "ambiguo" if reconhecimento.aviso or reconhecimento.familia == "desconhecida" else "reconhecido",
            "aviso": reconhecimento.aviso},
        extracao=getattr(texto,'perfil','docx_documental_v2'),
        imagens_extraidas=imagens_extraidas,
        paginas=list(getattr(texto,'paginas',())), duplicados=duplicados, faltantes=faltantes,
        leitura_paginas=[{k: v for k, v in page.items() if k != "texto"} for page in paginas],
        perfis_paginas_escolhidos=escolhas,
        avisos=list(dict.fromkeys(avisos)),
        questoes_com_avisos=[q['numero'] for q in qs if q.get('aviso_importacao')])
    return LoteImportado(qs, relatorio, getattr(qs, "instrucoes_prova", ""), reconhecimento)
