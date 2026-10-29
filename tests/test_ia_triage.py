import threading
import pytest

from src.models.ia_triage import triage_questions, validate_triage_row


def test_triage_cancelada_preserva_lote_sem_chamar_fontes():
    event = threading.Event()
    event.set()
    seen = []
    result = triage_questions([1, 2], cancel_event=event,
                              progress=lambda current, total: seen.append((current, total)))
    assert result == {"rows": [], "counts": {"liberada": 0, "bloqueada": 0,
                                                "conferir": 0, "proposta": 0,
                                                "revisao": 0, "erro": 0},
                      "cancelled": True}
    assert seen == []


def test_validate_triage_row_rejeita_shape_incompleto():
    with pytest.raises(ValueError):
        validate_triage_row({})

