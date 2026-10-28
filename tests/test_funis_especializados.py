from pathlib import Path

from src.importador.associacao_documental import associar_documentos
from src.importador.perfis.documentos import PerfilDocumento
from src.importador.perfis.registro import obter_perfil
from src.importador.perfis.segmentacao import segmentar
from src.importador.pdf_fonte import extract_pdf_source
from src.importador.servico import importar_caderno


def test_perfis_de_multiplas_escolhas_executam_somente_o_selecionado():
    texto = """QUESTÃO 1
Enunciado completo e verificável da questão número um.
A) opção alfa
B) opção beta
C) opção gama
D) opção delta
E) opção epsilon
QUESTÃO 2
Outro enunciado completo e verificável da questão número dois.
A) opção alfa
B) opção beta
C) opção gama
D) opção delta
E) opção epsilon
"""

    nomeado = segmentar(texto, texto, perfil_escolhido="questoes_nomeadas_v2")
    assert nomeado.perfil == "questoes_nomeadas_v2"
    assert len(nomeado.candidatos) == 2
    assert {item["perfil"] for item in nomeado.diagnostico} == {"questoes_nomeadas_v2"}

    isolado = """1
Enunciado completo e verificável da questão número um.
A) opção alfa
B) opção beta
C) opção gama
D) opção delta
E) opção epsilon
2
Outro enunciado completo e verificável da questão número dois.
A) opção alfa
B) opção beta
C) opção gama
D) opção delta
E) opção epsilon
3
Terceiro enunciado completo e verificável da questão número três.
A) opção alfa
B) opção beta
C) opção gama
D) opção delta
E) opção epsilon
"""
    resultado = segmentar(isolado, isolado, perfil_escolhido="multipla_escolha_sequencia_isolada_v3")
    assert resultado.perfil == "multipla_escolha_sequencia_isolada_v3"
    assert len(resultado.candidatos) == 3


def test_perfil_ce_preserva_texto_compartilhado_e_recusa_assinatura_ausente():
    texto = """TEXTO DE APOIO
Passagem compartilhada suficientemente longa para servir de contexto.
ITEM PARA JULGAMENTO
1. Primeiro item de julgamento com enunciado completo e verificável.
JUSTIFICATIVA - item um
2. Segundo item de julgamento com enunciado completo e verificável.
JUSTIFICATIVA - item dois
"""
    resultado = segmentar(texto, texto, perfil_escolhido="certo_errado_contexto_v1")
    assert resultado.perfil == "certo_errado_contexto_v1"
    assert len(resultado.candidatos) == 2
    assert "Passagem compartilhada" in texto

    incompatível = segmentar("1. enunciado sem bloco de contexto", "1. enunciado sem bloco de contexto",
                             perfil_escolhido="certo_errado_contexto_v1")
    assert not incompatível.candidatos
    assert incompatível.aviso


def test_registro_distingue_perfis_de_caderno_e_rotulos_de_gabarito():
    assert obter_perfil("multipla_escolha_sequencia_isolada_v3").papel == "caderno"
    assert obter_perfil("certo_errado_contexto_v1").familia == "certo_errado"
    assert obter_perfil("cex_itens_em_grade").papel == "gabarito"


def test_codigo_digitado_nao_confirma_identidade_documental():
    caderno = PerfilDocumento(
        "caderno", "multipla_escolha_numero_isolado_v2", ("marcadores",),
        familia="multipla_escolha", metadados={}, intervalo_questoes=(1, 2),
    )
    gabarito = PerfilDocumento(
        "gabarito", "pares_numero_resposta", ("pares",),
        familia="multipla_escolha", metadados={}, intervalo_questoes=(1, 2),
    )
    resultado = associar_documentos(caderno, gabarito, numeros_caderno={1, 2},
                                    respostas={1: "A", 2: "B"}, codigo="123_CARGO_01", cargo="Analista")
    assert resultado["estado"] == "ambiguo"


def test_perfil_reconhecido_roda_no_caderno_real_do_corpus():
    caminho = Path(__file__).resolve().parents[1] / "samples" / "agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf"
    lote = importar_caderno(str(caminho))
    perfil = lote.relatorio["reconhecimento"]["perfil_usado"]

    assert len(lote) == 50
    assert perfil == "multipla_escolha_numerada_v1"
    assert lote.relatorio["imagens_extraidas"] > 0
    assert all(Path(q["imagem_path"]).is_file() for q in lote if q.get("imagem_path"))

    reprocessado = importar_caderno(str(caminho), perfil_escolhido=perfil)
    assert len(reprocessado) == 50


def test_contexto_em_coluna_paralela_tem_regiao_fisica_completa():
    caminho = Path(__file__).resolve().parents[1] / "samples" / "agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf"
    lote = importar_caderno(str(caminho))
    fonte = extract_pdf_source(str(caminho), expected_questions=list(lote), asset_dir=None)
    por_numero = {item["numero"]: item for item in fonte["questions"]}

    assert all(por_numero[numero]["context_regions"] for numero in (1, 2, 3))
    assert not any("contexto_necessario_nao_encontrado" in por_numero[numero]["issues"]
                   for numero in (1, 2, 3))
