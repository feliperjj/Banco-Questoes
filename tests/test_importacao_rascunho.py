import pytest

import src.models.importacao_rascunho as rascunho
from src.models.importacao_rascunho import FonteRascunhoAlterada


def test_rascunho_reabre_com_fontes_integras_e_detecta_alteracao(tmp_path, monkeypatch):
    monkeypatch.setattr(rascunho, "RASCUNHO_PATH", tmp_path / "importacao.json")
    source = tmp_path / "caderno.pdf"
    source.write_bytes(b"conteudo original")
    payload = {"caminho_caderno": str(source), "caminho_gabarito": "",
               "questoes": [{"numero": 1, "enunciado": "Questão de teste"}],
               "salvas": {}, "etapa": 2}

    hashes = rascunho.salvar_rascunho(payload)
    payload["source_hashes"] = hashes

    assert rascunho.carregar_rascunho() == payload
    source.write_bytes(b"conteudo alterado")
    with pytest.raises(FonteRascunhoAlterada, match="mudou"):
        rascunho.carregar_rascunho()
    assert (tmp_path / "importacao.json").is_file()
