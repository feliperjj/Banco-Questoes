from src.ui.components.statement import formatar_enunciado


def test_vf_separa_afirmacoes_e_comando_sem_mudar_conteudo():
    texto = ('Dê valores Verdadeiro (V) ou Falso (F). ( ) O navegador é o Edge. '
             '( ) Bing é uma ferramenta. ( ) Chrome é uma ferramenta. '
             'Assinale a alternativa correta.')
    resultado = formatar_enunciado(texto)
    assert len(resultado.split('\n\n')) == 5
    assert ''.join(resultado.split()) == ''.join(texto.split())
    assert formatar_enunciado(resultado) == resultado


def test_nao_interpreta_parenteses_comuns_ou_item_unico():
    for texto in ['Calcule f(x) = () + ().', 'Verdadeiro ou falso: ( ) Uma afirmação.',
                  'Julgue o item a seguir. <texto> & exemplo.']:
        assert formatar_enunciado(texto) == texto


def test_afirmacoes_romanas_separadas_sem_mudar_texto():
    texto = 'Avalie as afirmativas. I. Primeira afirmação. II. Segunda afirmação. III. Terceira afirmação. Está correto o que se afirma em'
    resultado = formatar_enunciado(texto)
    assert len(resultado.split('\n\n')) == 5
    assert ''.join(resultado.split()) == ''.join(texto.split())
