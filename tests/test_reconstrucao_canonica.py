from pathlib import Path
import json

from src.models.reconstrucao_canonica import _proof_numbers, prepare_canonical


def test_conjunto_fisico_exige_1_a_n_sem_duplicatas():
    geometry = {"questions": [{"numero": 1}, {"numero": 2}, {"numero": 3}], "issues": []}
    assert _proof_numbers(geometry, 3) == ([1, 2, 3], None)
    assert _proof_numbers({"questions": [{"numero": 1}, {"numero": 3}], "issues": []}, 3)[1]
    assert _proof_numbers({"questions": [{"numero": 1}, {"numero": 1}, {"numero": 2}], "issues": []}, 3)[1]


def test_conjunto_fisico_dup_marcador_falha_fechado():
    geometry = {"questions": [{"numero": 1}, {"numero": 2}], "issues": ["marcador_duplicado:2"]}
    assert _proof_numbers(geometry, 2)[1] == "marcador_fisico_duplicado"


def test_apply_nao_toca_banco_incompleto(tmp_path):
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({"provas": [{"conjunto_completo": False}], "pendencias": []}), encoding="utf-8")
    from src.models.reconstrucao_canonica import apply_canonical
    result = apply_canonical(proposal, db_path=tmp_path / "db.sqlite")
    assert result["aplicado"] is False
    assert result["motivo"] == "conjunto_fisico_incompleto"
