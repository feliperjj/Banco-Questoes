from src.importador.parser import extrair_metadados_prova, parsear_questoes


def test_parseia_marcadores_questao_nomeados():
    texto = """
CEBRASPE Concurso publico 2026
QUESTAO 1
Texto sintetico da primeira pergunta para validar alternativas.
A) Alternativa alfa
B) Alternativa beta
C) Alternativa gama
D) Alternativa delta
E) Alternativa epsilon
QUESTAO 2
Texto sintetico da segunda pergunta para validar alternativas.
A) Uma escolha
B) Outra escolha
C) Terceira escolha
D) Quarta escolha
E) Quinta escolha
"""

    questoes = parsear_questoes(texto)

    assert len(questoes) == 2
    assert questoes[0]["tipo"] == "multipla_escolha"
    assert len(questoes[0]["alternativas"]) == 5
    assert questoes[0]["banca"] == "CESPE/CEBRASPE"
    assert questoes[0]["ano"] == 2026


def test_parseia_itens_cespe_sem_marcador_nomeado():
    texto = """
CEBRASPE
1 O sistema sintetico deve validar eventos administrativos com registro claro.
JUSTIFICATIVA - Explicacao sintetica.
2 A politica sintetica de backup pode dispensar verificacao periodica.
JUSTIFICATIVA: Explicacao sintetica.
"""

    questoes = parsear_questoes(texto)

    assert len(questoes) == 2
    assert [questao["tipo"] for questao in questoes] == ["certo_errado", "certo_errado"]
    assert all(questao["alternativas"] is None for questao in questoes)
    assert questoes[0]["banca"] == "CESPE/CEBRASPE"


def test_parseia_blocos_por_disciplina():
    texto = """
L\u00edngua Portuguesa
1
Texto sintetico da primeira questao com alternativas suficientes.
A) Opcao A
B) Opcao B
C) Opcao C
D) Opcao D
E) Opcao E
Inform\u00e1tica
2
Texto sintetico da segunda questao com alternativas suficientes.
A) Opcao A
B) Opcao B
C) Opcao C
D) Opcao D
E) Opcao E
"""

    questoes = parsear_questoes(texto)

    assert len(questoes) == 2
    assert questoes[0]["disciplina"] == "L\u00edngua Portuguesa"
    assert questoes[1]["disciplina"] == "Inform\u00e1tica"


def test_parseia_marcador_questao_com_caractere_substituto():
    texto = """
QUEST\uFFFDO 1
Texto sintetico com marcador corrompido no inicio da questao.
A) Opcao A
B) Opcao B
C) Opcao C
D) Opcao D
E) Opcao E
"""

    questoes = parsear_questoes(texto)

    assert len(questoes) == 1
    assert questoes[0]["tipo"] == "multipla_escolha"
    assert questoes[0]["enunciado"].startswith("Texto sintetico")


def test_ignora_grade_do_canhoto_e_aceita_numero_colado():
    texto = """
Instrucoes gerais
Transcreva suas respostas neste canhoto.
01 02 03 04 05 06 07 08 09 10
11 12 13 14 15 16 17 18 19 20
Língua Portuguesa | 2 QUESTÕES
1) Este é o enunciado completo da primeira questão de certo ou errado.
2) Este é o enunciado completo da segunda questão de certo ou errado.
"""

    questoes = parsear_questoes(texto)

    assert len(questoes) == 2
    assert questoes[0]["enunciado"].startswith("Este é o enunciado")
    assert all(questao["disciplina"] == "Língua Portuguesa" for questao in questoes)


def test_detecta_disciplina_no_marcador_com_contagem():
    metadados = extrair_metadados_prova(
        "Língua Portuguesa | 1 QUESTÃO\n1) Enunciado de teste suficientemente longo."
    )

    assert metadados["disciplinas"] == {1: "Língua Portuguesa"}


def test_infere_banca_pelo_nome_do_arquivo_quando_texto_nao_tem_a_marca():
    metadados = extrair_metadados_prova(
        "1) Enunciado de teste suficientemente longo.",
        "samples/prova-IBFC-agente.pdf",
    )

    assert metadados["banca"] == "IBFC"


def test_reconhece_conhecimentos_basicos_e_nocoes_de_informatica():
    questoes = parsear_questoes(
        "Conhecimentos Básicos\n1) Questão de teste suficientemente longa para o parser.\n"
        "Noções de Informática\n2) Outra questão de teste suficientemente longa para o parser."
    )

    assert [q["disciplina"] for q in questoes] == ["Conhecimentos Básicos", "Noções de Informática"]


def test_confianca_alta_para_item_certo_errado_longo():
    questoes = parsear_questoes(
        "CEBRASPE\n1) Este enunciado de certo ou errado é deliberadamente longo "
        "para representar uma questão bem extraída do documento original."
    )

    assert questoes[0]["tipo"] == "certo_errado"
    assert questoes[0]["confianca"] == "alta"


def test_recompõe_sequencia_numerada_intercalada_por_duas_colunas():
    texto = "\n".join(
        [
            "CEBRASPE",
            "1) Primeiro enunciado longo o bastante para uma questão válida.",
            "2) Segundo enunciado longo o bastante para uma questão válida.",
            "4) Quarto enunciado longo o bastante para uma questão válida.",
            "3) Terceiro enunciado longo o bastante para uma questão válida.",
            "5) Quinto enunciado longo o bastante para uma questão válida.",
            "1) Bloco posterior que não deve duplicar as questões.",
        ]
    )

    questoes = parsear_questoes(texto)

    assert len(questoes) == 5
    assert [questao["enunciado"][0] for questao in questoes] == ["P", "S", "T", "Q", "Q"]


def test_nao_confunde_referencia_numerada_dentro_de_alternativa():
    texto = """
1) Qual alternativa apresenta a relação correta?
(A) Confissão (parágrafo 7) e andar (parágrafo 8)
(B) Rodeios (parágrafo 4) e gaguejar (parágrafo 6)
(C) Cabecinha (parágrafo 7) e mudar (parágrafo 8)
(D) Sepultura (parágrafo 3) e renegar (parágrafo 7)
(E) Severidade (parágrafo 7) e esquecer (parágrafo 5)
2) Segunda questão com enunciado suficientemente longo para o teste.
(A) Primeira opção
(B) Segunda opção
(C) Terceira opção
(D) Quarta opção
(E) Quinta opção
"""

    questoes = parsear_questoes(texto)

    assert len(questoes) == 2
    assert len(questoes[0]["alternativas"]) == 5
