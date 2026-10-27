from types import SimpleNamespace
from unittest.mock import patch

from src.importador.gabarito_fonte import extract_answer_evidence


class _Page:
    width, height = 600, 800

    def __init__(self, rows, text=None):
        self.rows = rows
        self._text = text if text is not None else " ".join(t for _, _, t in rows)

    def extract_text(self, **kwargs):
        return self._text

    def extract_words(self, **kwargs):
        return [{"text": t, "x0": x, "x1": x + max(5, len(t) * 5),
                 "top": y, "bottom": y + 10} for x, y, t in self.rows]


class _Pdf:
    def __init__(self, pages):
        self.pages = pages

    def close(self):
        pass


def test_pairs_return_small_physical_regions(tmp_path):
    path = tmp_path / "g.pdf"
    path.write_bytes(b"pdf")
    pdf = _Pdf([_Page([(40, 20, "1"), (60, 20, "A"), (40, 40, "2"), (60, 40, "C")])])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, expected_answers={1: "A", 2: "C"})
    assert not out["issues"]
    assert out["answers"][1]["region"]["page"] == 1
    assert len(out["answers"][1]["region"]["bbox"]) == 4
    assert out["answers"][1]["region"]["width"] < 100


def test_numero_sem_resposta_esperada_le_o_valor_fisico_sem_escolher_letra(tmp_path):
    path = tmp_path / "sem-referencia.pdf"
    path.write_bytes(b"pdf")
    pdf = _Pdf([_Page([(40, 20, "1"), (60, 20, "D"), (40, 40, "2"), (60, 40, "B")])])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, expected_answers={1: None, 2: None})
    assert {n: value["resposta"] for n, value in out["answers"].items()} == {1: "D", 2: "B"}
    assert not out["issues"]


def test_horizontal_grade_keeps_number_alignment(tmp_path):
    path = tmp_path / "grade.pdf"
    path.write_bytes(b"pdf")
    pdf = _Pdf([_Page([(40, 20, "1"), (60, 20, "2"), (80, 20, "3"),
                       (40, 40, "A"), (60, 40, "C"), (80, 40, "E")])])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, expected_answers={1: "A", 2: "C", 3: "E"})
    assert set(out["answers"]) == {1, 2, 3}


def test_multiprova_selects_requested_occurrence_even_equal_answer(tmp_path):
    path = tmp_path / "multi.pdf"
    path.write_bytes(b"pdf")
    rows = [(40, 10, "PROVA"), (75, 10, "1"), (180, 10, "PROVA"), (215, 10, "2"),
            (40, 30, "1"), (60, 30, "A"), (180, 30, "1"), (200, 30, "B")]
    pdf = _Pdf([_Page(rows, "PROVA 1 PROVA 2\n1 A 1 B")])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, codigo_prova="PROVA 2", expected_answers={1: "B"})
    assert not out["issues"]
    assert out["answers"][1]["resposta"] == "B"


def test_conflicting_physical_answers_fail_closed(tmp_path):
    path = tmp_path / "conflict.pdf"
    path.write_bytes(b"pdf")
    pdf = _Pdf([_Page([(40, 20, "1"), (60, 20, "A"), (40, 40, "1"), (60, 40, "B")])])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, expected_answers={1: "A"})
    assert 1 not in out["answers"]
    assert "answer_conflict:1" in out["issues"]


def test_cebraspe_grade_normalizes_c_e_to_domain_words(tmp_path):
    path = tmp_path / "ce.pdf"
    path.write_bytes(b"pdf")
    pdf = _Pdf([_Page([(40, 20, "Item"), (80, 20, "1"), (100, 20, "2"),
                       (40, 40, "Gabarito"), (80, 40, "C"), (100, 40, "E")])])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, expected_answers={1: "CERTO", 2: "ERRADO"})
    assert not out["issues"]
    assert out["answers"][1]["resposta"] == "CERTO"


def test_punctuated_markers_keep_glyph_backed_regions(tmp_path):
    path = tmp_path / "punctuated.pdf"
    path.write_bytes(b"pdf")
    pdf = _Pdf([_Page([(40, 20, "01)"), (65, 20, "B"),
                       (110, 20, "11."), (135, 20, "D")])])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, expected_answers={1: "B", 11: "D"})
    assert not out["issues"]
    assert out["answers"][1]["resposta"] == "B"
    assert out["answers"][1]["region"]["bbox"][0] < 65


def test_identical_complete_duplicate_boards_use_one_representative(tmp_path):
    path = tmp_path / "duplicate.pdf"
    path.write_bytes(b"pdf")
    rows = [(40, 20, "1"), (60, 20, "A"), (40, 40, "2"), (60, 40, "B")]
    pdf = _Pdf([_Page(rows), _Page(rows)])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, expected_answers={1: "A", 2: "B"})
    assert not out["issues"]
    assert {item["metodo"] for item in out["answers"].values()} == {"duplicado_identico"}


def test_conflicting_duplicate_boards_remain_ambiguous(tmp_path):
    path = tmp_path / "duplicate-conflict.pdf"
    path.write_bytes(b"pdf")
    pdf = _Pdf([_Page([(40, 20, "1"), (60, 20, "A")]),
               _Page([(40, 20, "1"), (60, 20, "B")])])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, expected_answers={1: "A"})
    assert 1 not in out["answers"]
    assert "answer_conflict:1" in out["issues"]


def test_grade_skips_bounded_subject_label_between_rows(tmp_path):
    path = tmp_path / "label-grade.pdf"
    path.write_bytes(b"pdf")
    pdf = _Pdf([_Page([(40, 20, "1"), (60, 20, "2"), (80, 20, "3"),
                       (40, 30, "LÍNGUA"), (75, 30, "PORTUGUESA"),
                       (40, 40, "D"), (60, 40, "C"), (80, 40, "B")])])
    with patch("src.importador.gabarito_fonte.pdfplumber.open", return_value=pdf):
        out = extract_answer_evidence(path, expected_answers={1: "D", 2: "C", 3: "B"})
    assert not out["issues"]
    assert [out["answers"][n]["resposta"] for n in (1, 2, 3)] == ["D", "C", "B"]
