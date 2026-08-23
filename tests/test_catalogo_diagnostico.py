import pytest

from src.importador.catalogo import selecionar_associacao, validar_catalogo
from src.importador.diagnostico import diagnosticar_caderno


def test_catalogo_rejeita_registro_sem_evidencia():
    with pytest.raises(ValueError, match="evidência"):
        validar_catalogo({"prova.pdf": {"gabarito": "gab.pdf", "cargo": "X", "confirmado": True, "evidencia": ""}})


def test_catalogo_detecta_arquivo_ausente(tmp_path):
    with pytest.raises(FileNotFoundError):
        validar_catalogo({"prova.pdf": {"gabarito": "gab.pdf", "cargo": "X", "confirmado": True, "evidencia": "capa"}}, base_dir=tmp_path, exigir_arquivos=True)


def test_catalogo_preserva_diretorio_e_normaliza_separadores():
    catalogo = validar_catalogo({
        "Lote/Prova.pdf": {"gabarito": "gab.pdf", "cargo": "X", "confirmado": True, "evidencia": "capa"}
    })
    assert selecionar_associacao(catalogo, "lote\\prova.pdf")["cargo"] == "X"


def test_catalogo_permite_arquivo_unico_sem_cargo():
    catalogo = validar_catalogo({
        "prova.pdf": {"gabarito": "gab.pdf", "cargo": "", "arquivo_unico": True, "confirmado": True, "evidencia": "arquivo dedicado"}
    })
    assert selecionar_associacao(catalogo, "prova.pdf")["arquivo_unico"] is True


def test_diagnostico_eh_estruturado_e_nao_persiste():
    relatorio = diagnosticar_caderno("prova.pdf", [{"numero": 1}, {"numero": 2}], {1: "A"}, motivos=["texto_parcial"])
    assert relatorio["respostas_extraidas"] == 1
    assert relatorio["respostas_vinculadas"] == 1
    assert "gabaritos_faltantes" in relatorio["motivos"]
    assert relatorio["revisao_manual"]
    assert relatorio["cobertura_final"] == 50.0
    assert relatorio["ganho_potencial"] == 1
