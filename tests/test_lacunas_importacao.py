"""Regressões com expectativas de conteúdo, não apenas hashes do parser."""
from pathlib import Path
import pytest

from src.importador.parser import parsear_questoes
from src.importador.perfis.normalizacao import normalizar_formatos
from src.importador.pdf_texto import _pagina_sem_texto_rotacionado, _tem_duas_colunas


def alternativas():
    return '\n'.join(f'{l}) Resposta {l}.' for l in 'ABCDE')


def test_texto_longo_nao_descarta_primeira_disciplina():
    texto = 'LÍNGUA PORTUGUESA\n' + 'Uma linha do texto de apoio.\n'*30
    texto += '1) Primeiro enunciado completo.\n'+alternativas()
    texto += '\nMATEMÁTICA\n2) Segundo enunciado completo.\n'+alternativas()
    qs = parsear_questoes(texto)
    assert [q['numero'] for q in qs] == [1, 2]
    assert qs[0]['enunciado'] == 'Primeiro enunciado completo.'


def test_numero_de_figura_nao_substitui_numero_oficial():
    texto = '\n'.join(f'{n}\nEnunciado da questão {n}.\n'+
                      ('1\nOs símbolos abaixo representam alternativas.\n' if n==3 else '')+
                      alternativas() for n in range(1, 5))
    qs = parsear_questoes(texto)
    assert [q['numero'] for q in qs] == [1, 2, 3, 4]
    assert 'símbolos' in qs[2]['enunciado']


def test_fracoes_verticais_preservam_valores_e_proxima_questao():
    fr = '\n'.join(f'{n}\n({l}) .\n{d}' for n,l,d in zip([1,2,3,5,7],'ABCDE',[2,5,8,12,15]))
    texto = '33\nCalcule a probabilidade descrita.\n'+fr+'\n34\nCecília treinou durante abril.\n'+alternativas()
    qs = parsear_questoes(texto)
    assert [q['numero'] for q in qs] == [33,34]
    assert [a['texto'] for a in qs[0]['alternativas']] == ['1/2.','2/5.','3/8.','5/12.','7/15.']
    assert normalizar_formatos('1\n(A) .\n2') == '1\n(A) .\n2'


def test_contexto_nomeado_ignora_numeros_de_linhas():
    apoio = 'Texto para as questões de 1 a 2.\n1 Uma passagem longa sobre comunicação.\n'+'Outra linha da passagem.\n'*5
    qs = parsear_questoes(apoio+'QUESTÃO 1\nAvalie a passagem apresentada.\n'+alternativas()+
                         '\nQUESTÃO 2 Na mesma passagem, avalie a conclusão.\n'+alternativas())
    assert [q['numero'] for q in qs] == [1,2]
    assert all('Uma passagem longa' in q['enunciado'] for q in qs)


def test_contexto_duas_questoes_nao_vaza_para_alternativa_anterior():
    texto = 'QUESTÃO 17\nPrimeiro enunciado independente.\n'+alternativas()
    texto += '\nEnunciado para a resolução das questões 18 e 19.\n'+'Dados contábeis da empresa.\n'*5
    texto += '\nQUESTÃO 18\nQual o custo da produção?\n'+alternativas()
    texto += '\nQUESTÃO 19\nQual o total de vendas?\n'+alternativas()
    qs = parsear_questoes(texto)
    assert 'Dados contábeis' not in qs[0]['alternativas'][-1]['texto']
    assert all('Dados contábeis' in q['enunciado'] for q in qs[1:])


def test_marca_diagonal_upright_nao_contamina_corpo():
    class Pagina:
        def filter(self, fn):
            return [c for c in self.chars if fn(c)]
    p=Pagina()
    p.chars=[dict(object_type='char',upright=True,size=70,matrix=(.7,.7,-.7,.7,0,0)),
             dict(object_type='char',upright=True,size=10,matrix=(1,0,0,1,0,0))]
    assert _pagina_sem_texto_rotacionado(p) == [p.chars[1]]


def test_variavel_logica_nao_vira_alternativa():
    texto = 'QUESTÃO 1\nA expressão XOR pode ser escrita como:\n(A) (a and not b) or (not a and b)\n(B) a or b\n(C) not a\n(D) not b\n(E) not a and not b'
    q = parsear_questoes(texto)[0]
    assert [a['letra'] for a in q['alternativas']] == list('ABCDE')
    assert q['alternativas'][0]['texto'] == '(a and not b) or (not a and b)'
    from src.importador.validacao import problemas_estrutura
    assert not problemas_estrutura(q)


def test_lista_interna_permanece_no_enunciado():
    texto = 'QUESTÃO 12\nConsidere os seguintes tributos:\na) COFINS 3%;\nb) ICMS 10%;\nc) IR 25%;\nd) PIS 2%;\ne) Reserva legal 5%.\nCalcule o lucro líquido.\n'+alternativas()
    q = parsear_questoes(texto)[0]
    assert len(q['alternativas']) == 5
    assert 'COFINS 3%' in q['enunciado']
    assert 'Calcule o lucro líquido' in q['enunciado']


@pytest.mark.parametrize('arquivo,total', [
    ('analista_analise_de_sistema_desenvolvimento_de_sistema.pdf',120),
    ('TRANSPETRO.pdf',70),
    ('lote_2026_08_22/agente_administrativo_i-3.pdf',55),
    ('lote_2026_08_22/analista_administrativo_iii_analista_de_sistemas.pdf',80),
    ('lote_2026_08_22/analista_analista_de_sistemas.pdf',50),
    ('lote_2026_08_22/analista_adm_desenvolvimento_sistemas.pdf',40),
    ('lote_2026_08_22/analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf',70),
    ('lote_2026_08_22/analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf',50),
    ('lote_2026_08_22/auditor_fiscal.pdf',40),
    ('lote_2026_08_22/provas_2e3_auditor_fiscal.pdf',70),
    ('lote_2026_08_22/prova1_auditor_fiscal.pdf',45),
])
def test_cadernos_lacunas_sequencia_oficial(arquivo,total):
    from src.importador.extrator import extrair_texto
    fonte = Path(__file__).resolve().parents[1]/'samples'/arquivo
    if not fonte.exists():
        pytest.skip('PDF de integração não disponível')
    qs = parsear_questoes(extrair_texto(str(fonte)))
    assert [q['numero'] for q in qs] == list(range(1,total+1))
    if total==120:
        assert 'Na longa e inconclusiva busca' in qs[0]['enunciado']
        assert 'Cresci brincando' not in qs[8]['enunciado']
        assert 'Cresci brincando' in qs[9]['enunciado']
        assert all('PÁGINA' not in q['enunciado'] for q in qs)
    if arquivo=='TRANSPETRO.pdf':
        assert 'demanda média diária' in qs[47]['enunciado']
        assert 'empréstimo' in qs[69]['enunciado']
