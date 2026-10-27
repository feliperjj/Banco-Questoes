from pathlib import Path
from unittest.mock import patch

from src.importador.pdf_fonte import extract_pdf_source


class _Crop:
    def __init__(self, text):
        self.text = text

    def extract_text(self, **kwargs):
        return self.text


class _Page:
    width, height = 600, 800

    def __init__(self, rows):
        self.rows = rows

    def extract_words(self, **kwargs):
        return [{"text": text, "x0": x, "x1": x + len(text) * 5,
                 "top": y, "bottom": y + 10, "fontname": "Arial-Bold",
                 "size": 11} for x, y, text in self.rows]

    def crop(self, bbox):
        return _Crop("\n".join(text for _, _, text in self.rows))


class _PDF:
    def __init__(self, pages):
        self.pages = pages

    def close(self):
        pass


def _source(tmp_path, rows):
    path = tmp_path / "source.pdf"
    path.write_bytes(b"synthetic-pdf")
    return path, _PDF([_Page(rows)])


def test_marker_number_is_physical_and_omitted_candidate_does_not_shift(tmp_path):
    source = tmp_path / "x.pdf"
    source, pdf = _source(tmp_path, [(40, 20, "QUESTÃO"), (40, 30, "10"),
                                     (40, 50, "Enunciado inequívoco da questão dez."),
                                     (40, 70, "A) uma alternativa"), (40, 90, "B) outra alternativa"),
                                     (40, 120, "QUESTÃO"), (40, 130, "12"),
                                     (40, 150, "Enunciado inequívoco da questão doze."),
                                     (40, 170, "A) uma alternativa"), (40, 190, "B) outra alternativa")])
    with patch("src.importador.pdf_fonte.pdfplumber.open", return_value=pdf):
        out = extract_pdf_source(source, expected_questions=[{"numero": 10, "texto": "Enunciado inequívoco"},
                                                              {"numero": 11, "texto": "não existe"}])
    assert [q["numero"] for q in out["questions"]] == [10, 12]
    assert 11 not in [q["numero"] for q in out["questions"]]


def test_columns_do_not_merge_questions(tmp_path):
    source = tmp_path / "columns.pdf"
    source, pdf = _source(tmp_path, [(40, 20, "68."), (40, 40, "Texto longo da coluna esquerda"), (40, 60, "A) x"),
                                     (320, 20, "70."), (320, 40, "Texto longo da coluna direita"), (320, 60, "A) y")])
    with patch("src.importador.pdf_fonte.pdfplumber.open", return_value=pdf):
        out = extract_pdf_source(source, expected_questions=[])
    assert {q["numero"] for q in out["questions"]} == {68, 70}
    assert all(q["regions"][0]["width"] < 400 for q in out["questions"])


def test_invalid_region_and_missing_anchor_are_fail_closed(tmp_path):
    source = tmp_path / "anchor.pdf"
    source, pdf = _source(tmp_path, [(40, 20, "QUESTÃO"), (40, 30, "1"),
                                     (40, 50, "Texto que não corresponde ao candidato")])
    with patch("src.importador.pdf_fonte.pdfplumber.open", return_value=pdf):
        out = extract_pdf_source(source, expected_questions=[{"numero": 1, "texto": "frase ausente completamente"}])
    assert not out["questions"]
    assert "ancora_nao_encontrada:1" in out["issues"]


def test_transpetro_profile_keeps_two_columns_independent(tmp_path):
    source = tmp_path / "TRANSPETRO.pdf"
    source.write_bytes(b"synthetic-transpetro")
    rows = [(28, 100, "1"), (28, 120, "Texto português da questão um."),
            (310, 100, "2"), (310, 120, "Texto português da questão dois.")]
    pdf = _PDF([_Page([]), _Page(rows)])
    with patch("src.importador.pdf_fonte.pdfplumber.open", return_value=pdf):
        out = extract_pdf_source(source, expected_questions=[
            {"numero": 1, "texto": "Texto português da questão um"},
            {"numero": 2, "texto": "Texto português da questão dois"},
        ])
    assert [q["numero"] for q in out["questions"]] == [1, 2]
    assert all(q["checks"]["anchor_confirmed"] for q in out["questions"])
    assert all(len(q["context_regions"]) == 2 for q in out["questions"])
