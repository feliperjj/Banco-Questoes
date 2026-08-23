import src.importador.extrator as extrator
from src.importador.extrator import FiltroContexto, _extrair_gabaritos_tabelas, _tem_duas_colunas
from scripts.reimportar_samples import _aplicar_gabarito_validado


def test_gabarito_so_e_aplicado_com_sequencia_completa():
    questoes = [{}, {}, {}]
    assert _aplicar_gabarito_validado(questoes, {1: "A", 2: "B"}) == 2
    assert questoes[0]["gabarito"] == "A"
    assert questoes[1]["gabarito"] == "B"
    assert _aplicar_gabarito_validado(questoes, {1: "A", 2: "B", 3: "X"}) == 3
    assert questoes[2]["gabarito"] == "Anulada"


def _palavras_linha(top, inicio, quantidade, passo=10, largura=8):
    return [
        {"top": top, "x0": inicio + indice * passo, "x1": inicio + indice * passo + largura}
        for indice in range(quantidade)
    ]


def test_nao_trata_linhas_de_largura_total_como_duas_colunas():
    palavras = []
    for topo in range(10, 90, 8):
        palavras.extend(_palavras_linha(topo, 20, 12, passo=35))

    assert not _tem_duas_colunas(palavras, 800)


def test_detecta_duas_colunas_por_linhas_confinadas():
    palavras = []
    for topo in range(10, 90, 8):
        palavras.extend(_palavras_linha(topo, 20, 6, passo=25))
        palavras.extend(_palavras_linha(topo, 430, 6, passo=25))

    assert _tem_duas_colunas(palavras, 800)


def test_extrai_tabela_apenas_com_numero_e_resposta():
    class Pagina:
        def extract_tables(self):
            return [[['Código', 'Resposta'], ['12', 'B'], ['2026', 'A'], ['13', 'X']]]

    assert _extrair_gabaritos_tabelas(Pagina()) == {12: 'B', 13: 'X'}


class _PdfFalso:
    def __init__(self, paginas):
        self.pages = paginas

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class _PaginaGabarito:
    def extract_text(self):
        return "1 A 2 B"

    def extract_tables(self):
        return []


def test_ocr_nao_roda_quando_gabarito_curto_ja_esta_completo(monkeypatch):
    monkeypatch.setattr(extrator.pdfplumber, "open", lambda caminho: _PdfFalso([_PaginaGabarito()]))
    chamadas = []
    monkeypatch.setattr(extrator, "_extrair_gabaritos_ocr", lambda *args, **kwargs: chamadas.append(1) or {})

    resultado = extrator.extrair_gabaritos_pdf("gab.pdf")

    assert resultado == {1: "A", 2: "B"}
    assert chamadas == []


def test_ocr_completa_somente_numeros_esperados(monkeypatch):
    monkeypatch.setattr(extrator.pdfplumber, "open", lambda caminho: _PdfFalso([_PaginaGabarito()]))
    monkeypatch.setattr(extrator, "_extrair_gabaritos_ocr", lambda *args, **kwargs: {3: "C", 4: "D"})

    resultado = extrator.extrair_gabaritos_pdf("gab.pdf", numeros_esperados={1, 2, 3})

    assert resultado == {1: "A", 2: "B", 3: "C"}


def test_filtro_contexto_preserva_cargo_selecionado():
    contexto = FiltroContexto("prova-1", "Analista de Sistemas")

    assert contexto.pagina_relevante("Código: prova_1\nCargo: Analista de Sistemas")
    assert contexto.pagina_relevante("1 A 2 B")
    assert not contexto.pagina_relevante("Cargo: Auditor\n1 C 2 D")
    assert not contexto.pagina_relevante("1 C 2 D")
