import os
from pathlib import Path

import pytest

from src.importador.extrator import (
    _extrair_itens_certo_errado, _parece_pagina_de_questoes,
    FiltroContexto, extrair_texto_pdf, extrair_gabaritos_pdf,
)
from src.importador.parser import parsear_questoes
from src.importador.validacao import associar_gabaritos
from src.importador.cebraspe_layout import extrair_layout_cebraspe


def test_palavra_justificativa_nao_descarta_demais_itens():
    texto = '\n'.join(f'{n} A justificativa do procedimento está correta.' if n in [2,4]
                      else f'{n} O procedimento administrativo é obrigatório.' for n in range(1,7))
    assert [q['numero'] for q in parsear_questoes(texto)] == list(range(1,7))


def test_anulacao_nao_desloca_respostas_e_zeros_nao_viram_itens():
    linhas=['Item 95 96 97 98 99 100 0 0', 'Gabarito C X X E C E 0 0']
    assert _extrair_itens_certo_errado(linhas) == {95:'Certo',96:'Anulada',97:'Anulada',98:'Errado',99:'Certo',100:'Errado'}
    assert _extrair_itens_certo_errado(['Item 1 2 3', 'Gabarito C E']) == {}


def test_codigo_exato_nao_vaza_para_outro_cargo_ou_discursiva():
    filtro = FiltroContexto('094_PF_CB2_01;094_PF_015_01')
    assert filtro.pagina_relevante('Nível médio\n094_PF_CB2_01')
    assert not filtro.pagina_relevante('Nível superior\n094_PF_CB1_01')
    assert filtro.pagina_relevante('Agente\n094_PF_015_01')
    assert not filtro.pagina_relevante('Agente\nProva discursiva')


def test_regra_colunas_cebraspe_nao_ativa_para_iades():
    texto = 'Julgue os itens.\n1 Primeiro enunciado.\n2 Segundo enunciado.\n3 Terceiro enunciado.'
    assert not _parece_pagina_de_questoes('IADES\n'+texto)
    assert _parece_pagina_de_questoes('CEBRASPE\n'+texto)


def test_titulo_tardio_nao_descarta_questoes_nomeadas_anteriores():
    texto='Língua Portuguesa\n' + ('Texto de apoio longo.\n' * 20)
    texto+='QUESTÃO 1\nAssinale a resposta correta.\nA) Uma\nB) Outra\n'
    texto+='Informática\nQUESTÃO 2\nAssinale a resposta correta.\nA) Uma\nB) Outra'
    assert [q['numero'] for q in parsear_questoes(texto)] == [1,2]


def test_recuos_preservam_contexto_e_nao_anexam_comando_ao_item():
    words=[]
    def linha(texto,x,y):
        for palavra in texto.split():
            words.append(dict(text=palavra,x0=x,x1=x+len(palavra)*4,top=y))
            x+=len(palavra)*4+4
    for coluna in range(2):
        x=28+coluna*300
        linha('Julgue os itens do texto de apoio.',x,70)
        for i in range(10):
            n=coluna*10+i+1
            linha(str(n)+' A justificativa é válida.',x,100+i*40)
            linha('Segundo os autores.',x+18,113+i*40)
    class Area:
        def __init__(self, bbox):self.bbox=bbox
        def extract_words(self,**kwargs):
            return [w for w in words if self.bbox[0]<=w['x0']<self.bbox[2]]
    class Pagina:
        width,height=600,850
        def extract_text(self):return 'CEBRASPE Edital: 2025\nJulgue os itens.'
        def filter(self,fn):return self
        def crop(self,bbox):return Area(bbox)
        def extract_words(self,**kwargs):return words
    class Pdf:pages=[Pagina()]
    texto=extrair_layout_cebraspe(Pdf())
    assert texto is not None
    qs=parsear_questoes(texto)
    assert len(qs)==20
    for q in qs:
        contexto,item=q['enunciado'].split('\n\nITEM PARA JULGAMENTO\n')
        assert 'Julgue os itens do texto de apoio.' in contexto
        assert item=='A justificativa é válida. Segundo os autores.'


def test_pdf_enviado_120_itens_contextos_e_gabaritos():
    downloads=Path(os.environ.get('USERPROFILE',''))/'Downloads'
    caderno=downloads/'agente_administrativo.pdf cebraspe 2025.pdf'
    gabarito=downloads/'gabarito_definitivo.pdf 2025cebraspe.pdf'
    if not caderno.exists() or not gabarito.exists():
        pytest.skip('PDFs fornecidos pelo usuário disponíveis apenas no ambiente local')
    qs=parsear_questoes(extrair_texto_pdf(str(caderno)),str(caderno))
    assert [q['numero'] for q in qs] == list(range(1,121))
    assert all(q['tipo']=='certo_errado' and not q['alternativas'] for q in qs)
    assert 'Imaginar é um dom' in qs[0]['enunciado']
    assert 'inteligência artificial' not in qs[7]['enunciado']
    assert 'inteligência artificial' in qs[8]['enunciado']
    assert 'Julgue os itens seguintes com base no Manual' in qs[19]['enunciado']
    assert 'Não quero debate' in qs[20]['enunciado']
    assert '60 pessoas' in qs[23]['enunciado']
    assert all('RASCUNHO' not in q['enunciado'] for q in qs)
    assert all(not q['enunciado'].endswith(('Conhecimentos Básicos','Conhecimentos Específicos')) for q in qs)
    g=extrair_gabaritos_pdf(str(gabarito),'094_PF_CB2_01;094_PF_015_01',usar_ocr=False)
    resultado=associar_gabaritos(qs,g)
    assert resultado['vinculados']==120 and not resultado['revisao_manual']
    assert [q['numero'] for q in qs if q['gabarito']=='Anulada']==[96,97]
    assert qs[0]['gabarito']=='Errado' and qs[50]['gabarito']=='Certo'
