from src.db.database import init_db
from src.models import questoes_repo as repo
from src.importador.parser import parsear_questoes
from src.importador.validacao import problemas_estrutura
from src.importador.extrator import _extrair_texto_colunas, _linhas_repetidas
from src.importador.extrator import _extrair_grade_identificada


def test_alternativas_horizontais_e_numero_no_meio_da_frase():
    texto = '14) Um código deve ser múltiplo de 3. Para que seja válido, complete a lacuna.\na) 6 b) 5 c) 3 d) 1'
    questoes = parsear_questoes(texto)
    assert len(questoes) == 1 and questoes[0]['numero'] == 14
    assert questoes[0]['enunciado'].startswith('Um código')
    assert [a['texto'] for a in questoes[0]['alternativas']] == ['6', '5', '3', '1']


def test_rodape_nao_faz_parte_da_ultima_alternativa():
    q = parsear_questoes('1\nAssinale a resposta correta.\nA) Uma\nB) Outra TIPO Branca – PÁGINA 4')[0]
    assert q['alternativas'][-1]['texto'] == 'Outra'


def test_nova_prova_exclui_fusao_lacuna_e_alternativa_unica(tmp_path):
    init_db(str(tmp_path/'qualidade.db'))
    ids = []
    for letras, textos in [('A', ['6 b) 5 c) 3 d) 1']), ('ABDE', ['Uma','Outra c) perdida','Quarta','Quinta']), ('AB', ['Uma','Outra'])]:
        ids.append(repo.criar_questao(dict(enunciado='Assinale a alternativa correta.', tipo='multipla_escolha',gabarito='A',
                    alternativas=[dict(letra=l,texto=t) for l,t in zip(letras,textos)])))
    assert repo.contar_questoes_elegiveis() == 1
    pid = repo.criar_prova('Segura',{},10,0)
    assert [q['id'] for q in repo.buscar_questoes_da_prova(pid)] == [ids[2]]


def test_detecta_rodape_e_comando_incompleto():
    assert problemas_estrutura(dict(enunciado='Assinale a alternativa que',tipo='certo_errado'))
    assert problemas_estrutura(dict(enunciado='Texto TIPO Branca – PÁGINA 4',tipo='certo_errado'))


def test_divisoria_retangular_define_corte_das_colunas(monkeypatch):
    import src.importador.pdf_texto as mod
    class Pagina:
        width, height = 600, 800
        lines = []
        rects = [dict(x0=310, x1=311, top=60, bottom=750)]
    cortes = []
    monkeypatch.setattr(mod, '_extrair_texto_area', lambda p, bbox: cortes.append(bbox) or 'Texto')
    _extrair_texto_colunas(Pagina())
    assert cortes[0][2] == 310 and cortes[1][0] == 310


def test_comando_repetido_nao_e_rodape():
    assert 'preencha corretamente a lacuna.' not in _linhas_repetidas([
        'Cabeçalho\npreencha corretamente a lacuna.\nRodapé'] * 4)


def test_gabarito_prova_i_nao_recebe_resposta_da_prova_ii():
    texto = 'Prova I\n01 - C 30 - B\nProvas II e III\n01 - E 30 - A'
    assert _extrair_grade_identificada(None,texto,None,'Prova I') == {1:'C',30:'B'}
    assert _extrair_grade_identificada(None,texto,None,'Provas II e III') == {1:'E',30:'A'}
    assert _extrair_grade_identificada(None,texto,None,None) == {}


def test_navegacao_reinicia_scroll_e_restabelece_selecao(tmp_path, qt_application):
    from PySide6.QtTest import QTest
    from src.ui.pages.execucao_prova import ExecucaoProvaPage
    init_db(str(tmp_path/'scroll.db'))
    for n in range(2):
        repo.criar_questao(dict(enunciado=f'Questão {n}',tipo='multipla_escolha',gabarito='A',
             alternativas=[dict(letra=l,texto=('Texto longo para forçar rolagem. '*30)) for l in 'ABCDE']))
    pid=repo.criar_prova('Rolagem',{},2,0)
    page=ExecucaoProvaPage()
    page.resize(760,640)
    page.show()
    page.iniciar(pid,'Rolagem')
    # Aguarda o layout calculado, sem depender da velocidade da máquina.
    for _ in range(100):
        QTest.qWait(20)
        if page.alternativas_scroll.verticalScrollBar().maximum() > 0:
            break
    primeiro=page.questoes[0]['id']
    page.respostas_memoria[primeiro]='A'
    barra=page.alternativas_scroll.verticalScrollBar()
    barra.setValue(barra.maximum())
    assert barra.value()>0
    page.proxima_questao()
    qt_application.processEvents()
    assert barra.value()==0
    page.questao_anterior()
    qt_application.processEvents()
    assert page.alternativas_layout.itemAt(0).widget().property('selected')
    assert barra.value()==0
    page.timer.stop()
