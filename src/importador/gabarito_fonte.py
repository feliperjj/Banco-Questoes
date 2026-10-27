"""Evidence-backed extraction of answers from a gabarito PDF.

This module is intentionally independent from the answer-map API.  Every answer
is returned with the physical page and a small bounding box containing the
question marker and answer token.  Ambiguous or conflicting observations are
reported and are never silently selected.
"""
from __future__ import annotations

import re
from typing import Any

import pdfplumber

from .perfis.gabaritos_contexto import FiltroContexto
from .pdf_texto import _corrigir_encoding_ocr

_ANSWER = {"A", "B", "C", "D", "E", "X", "CERTO", "ERRADO", "C", "E"}


def _word_lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    lines: list[list[dict[str, Any]]] = []
    for word in sorted(words or [], key=lambda w: (float(w.get("top", 0)), float(w.get("x0", 0)))):
        if not lines or abs(float(word.get("top", 0)) - float(lines[-1][0].get("top", 0))) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)
    for line in lines:
        line.sort(key=lambda w: float(w.get("x0", 0)))
    return lines


def _token(word: dict[str, Any]) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(word.get("text", ""))).upper()


def _box(words: list[dict[str, Any]], page) -> dict[str, float | int]:
    x0 = min(float(w.get("x0", 0)) for w in words)
    x1 = max(float(w.get("x1", w.get("x0", 0))) for w in words)
    top = min(float(w.get("top", 0)) for w in words)
    bottom = max(float(w.get("bottom", w.get("top", 0))) for w in words)
    return {"x0": x0, "top": top, "x1": x1, "bottom": bottom,
            "width": x1 - x0, "height": bottom - top, "rotation": 0}


def _answer(value: str) -> str | None:
    value = value.upper().strip()
    if value in {"CERTO", "ERRADO", "A", "B", "C", "D", "E", "X"}:
        return value
    return None


def _answer_word(word: dict[str, Any]) -> str | None:
    raw = str(word.get("text", "")).strip()
    value = _answer(_token(word))
    # Lowercase prose (notably the article ``a`` in page headers) is not a
    # physical answer token.  Official answer cells use uppercase glyphs.
    if value and raw != raw.upper():
        return None
    return value


def _grade_answer_word(word: dict[str, Any]) -> str | None:
    """Read an answer cell in a dense grade row, including lowercase OCR/text."""
    value = _answer(_token(word))
    return value


def _answer_after_marker(line: list[dict[str, Any]], marker_index: int) -> tuple[int, str] | None:
    """Find an answer immediately after a numbered marker on the same line.

    Published answer keys use several equivalent physical spellings (``01) B``,
    ``01. B`` and ``01 - B``).  Treat punctuation between the marker and token
    as layout noise, but stop at another number so a neighbouring cell cannot
    be borrowed.  Keeping the returned word preserves a real glyph-backed
    region for the evidence record.
    """
    for index in range(marker_index + 1, min(len(line), marker_index + 5)):
        token = _token(line[index])
        if token.isdigit():
            break
        raw = str(line[index].get("text", ""))
        if raw.strip(".)]:-–—") == "":
            continue
        answer = _answer_word(line[index])
        if answer:
            return index, answer
        # Any non-punctuation text means this is not a marker/answer pair.
        break
    return None


def _canonical_answer(answer: str, expected: str | None) -> str:
    if expected in {"CERTO", "ERRADO", "ANULADA"}:
        return {"C": "CERTO", "E": "ERRADO", "X": "ANULADA"}.get(answer, answer)
    return answer


def _header_columns(lines: list[list[dict[str, Any]]]) -> list[int]:
    """Return x-centres in the order of an explicit PROVA/TIPO header."""
    centres: list[int] = []
    # Some sheets put PROVA 4 on a separate line above PROVA 1..3.  Inspect
    # the complete header area, stopping only once the first dense answer row
    # begins, rather than assuming headers are among the first eight lines.
    for line in lines[:30]:
        toks = [(_token(w), w) for w in line]
        found = [(i, w) for i, (t, w) in enumerate(toks) if t in {"PROVA", "TIPO", "T1", "T2", "T3", "T4"}]
        for i, word in found:
            if _token(word) in {"PROVA", "TIPO"} and i + 1 < len(line):
                nxt = _token(line[i + 1])
                if nxt.isdigit():
                    centre = round((float(word.get("x0", 0)) + float(line[i + 1].get("x1", 0))) / 2)
                    if centre not in centres:
                        centres.append(centre)
            elif _token(word) in {"T1", "T2", "T3", "T4"}:
                centre = round((float(word.get("x0", 0)) + float(word.get("x1", 0))) / 2)
                if centre not in centres:
                    centres.append(centre)
        if not found and len([w for w in line if _token(w).isdigit()]) >= 4:
            break
    return sorted(centres)


def _wanted_column(codigo: str | None) -> int | None:
    m = re.search(r"(?:PROVA|TIPO|T)\s*([1-9])\b", (codigo or "").upper())
    return int(m.group(1)) - 1 if m else None


def _line_candidates(line, page, method: str, wanted_col: int | None, columns: list[int]):
    tokens = [_token(w) for w in line]
    out = []
    if wanted_col is not None:
        # Horizontal multiprova rows commonly repeat the same question number
        # once per column (``1 A 2 B 1 C 2 D``).  Select by occurrence, never
        # by matching the answer text.
        occurrences: dict[int, int] = {}
        for i, tok in enumerate(tokens):
            pair = _answer_after_marker(line, i) if tok.isdigit() and 1 <= int(tok) <= 300 else None
            if pair:
                answer_index, answer = pair
                number = int(tok)
                occurrence = occurrences.get(number, 0)
                occurrences[number] = occurrence + 1
                if occurrence == wanted_col:
                    out.append((number, answer, [line[i], line[answer_index]], "multiprova"))
        if out:
            return out
        if columns and wanted_col < len(columns):
            for i, tok in enumerate(tokens):
                if not tok.isdigit() or not 1 <= int(tok) <= 300:
                    continue
                pair = _answer_after_marker(line, i)
                if pair:
                    answer_index, value = pair
                    centre = (float(line[i].get("x0", 0)) + float(line[answer_index].get("x1", 0))) / 2
                    nearest = min(range(len(columns)), key=lambda idx: abs(centre - columns[idx]))
                    if nearest == wanted_col:
                        out.append((int(tok), value, [line[i], line[answer_index]], "multiprova"))
            return out
    # Explicit vertical rows: number followed by one answer per column.
    for i, tok in enumerate(tokens):
        if not tok.isdigit() or not 1 <= int(tok) <= 300:
            continue
        answers = []
        pair = _answer_after_marker(line, i)
        if pair:
            answers.append(pair)
        else:
            for j in range(i + 1, min(len(tokens), i + 8)):
                val = _answer_word(line[j])
                if val:
                    answers.append((j, val))
                elif tokens[j].isdigit():
                    break
        if not answers:
            continue
        # A marker with punctuation has already consumed its answer above;
        # otherwise retain the existing vertical-row handling.
        if pair:
            selected = answers[0]
        else:
            selected = answers[wanted_col] if wanted_col is not None and wanted_col < len(answers) else None
            if selected is None and len(answers) == 1:
                selected = answers[0]
        if selected is None:
            continue
        j, val = selected
        out.append((int(tok), val, [line[i], line[j]], method))
    return out


def _horizontal_candidates(lines, page):
    out = []
    for index, line in enumerate(lines):
        if any(_token(w) in {"PROVA", "TIPO"} for w in line):
            continue
        if any(_answer_word(w) for w in line):
            continue
        nums = [i for i, w in enumerate(line) if _token(w).isdigit() and 1 <= int(_token(w)) <= 300]
        if not nums or index + 1 >= len(lines):
            continue
        # A grade may place a subject label between the number row and answer
        # row (``1..5 / LÍNGUA PORTUGUESA / D C C B A``). Search a small
        # bounded window, stopping at another numeric row, and only accept a
        # line whose answer count exactly matches the markers.
        selected = None
        for offset in range(1, min(4, len(lines) - index)):
            next_line = lines[index + offset]
            if any(_token(w).isdigit() for w in next_line):
                if offset > 1:
                    break
                continue
            vals = [(i, _grade_answer_word(w)) for i, w in enumerate(next_line)]
            vals = [(i, v) for i, v in vals if v]
            if len(nums) == len(vals) and len(nums) >= 2:
                selected = (next_line, vals)
                break
        if selected is None:
            continue
        next_line, vals = selected
        for ni, (vi, val) in zip(nums, vals):
            out.append((int(_token(line[ni])), val, [line[ni], next_line[vi]], "grade_horizontal"))
    return out


def extract_answer_evidence(path, *, codigo_prova=None, cargo=None, expected_answers=None):
    """Extract physically bounded evidence for the requested answer map.

    ``expected_answers`` is mandatory in practice: it defines the question
    scope and prevents a coincidental number elsewhere in a PDF becoming an
    answer.  Missing, duplicate, and conflicting observations are issues.
    """
    expected = {int(k): str(v).upper() if v is not None else None for k, v in (expected_answers or {}).items()}
    result = {"answers": {}, "issues": []}
    context = FiltroContexto(codigo_prova, cargo)
    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:
        result["issues"].append(f"pdf_open:{exc}")
        return result
    observations: dict[int, list[dict[str, Any]]] = {}
    try:
        # Perfil documental confirmado da Prova 1/Administração. O quadro
        # básico é compartilhado; o específico contém dois subgrupos por
        # prova. Recortar o grupo antes de ler pares evita misturar os cargos.
        header = pdf.pages[0].extract_text() or ""
        if ("TRANSPETRO" in header.upper() and "TERRA" in header.upper()
                and re.search(r"PROVA\s*1\b", codigo_prova or "", re.I)
                and "administra" in (cargo or "").casefold() and len(pdf.pages) >= 2):
            specific = pdf.pages[1]
            scope_text = specific.crop((50, 110, 180, 195)).extract_text() or ""
            if "PROVA 1" in scope_text and "Administra" in scope_text:
                areas = [(1, pdf.pages[0], (0, 0, pdf.pages[0].width, pdf.pages[0].height), set(range(1, 21))),
                         (2, specific, (50, 180, 170, 710), set(range(21, 71)))]
                for page_no, page, bounds, numbers in areas:
                    for line in _word_lines(page.crop(bounds).extract_words(x_tolerance=2, y_tolerance=3)):
                        for index, word in enumerate(line):
                            if not str(word["text"]).isdigit() or int(word["text"]) not in numbers:
                                continue
                            number = int(word["text"])
                            for next_word in line[index + 1:index + 4]:
                                if str(next_word["text"]).isdigit():
                                    break
                                answer = _answer_word(next_word)
                                if answer:
                                    bbox = [word["x0"] - .5, min(word["top"], next_word["top"]) - .5,
                                            next_word["x1"] + .5, max(word["bottom"], next_word["bottom"]) + .5]
                                    if number in expected:
                                        result["answers"][number] = {"resposta": answer,
                                            "region": {"page": page_no, "bbox": bbox, "width": page.width, "height": page.height, "rotation": page.rotation or 0},
                                            "metodo": "transpetro_terra_prova1_quadro_confirmado", "scope_excerpt": scope_text}
                                        if expected[number] is not None and answer != expected[number]:
                                            result["issues"].append(f"reference_map_mismatch:{number}")
                                    break
                result["issues"].extend(f"answer_missing:{n}" for n in expected if n not in result["answers"])
                return result
        for page_no, page in enumerate(pdf.pages, 1):
            text = _corrigir_encoding_ocr(page.extract_text() or "")
            if text and not context.pagina_relevante(text):
                continue
            try:
                words = page.extract_words(x_tolerance=2, y_tolerance=3)
            except TypeError:
                words = page.extract_words()
            lines = _word_lines(words)
            # Reutiliza a seleção explícita de cargo/tipo sobre as próprias
            # linhas físicas. As strings retornadas são as mesmas instâncias,
            # portanto não confunde linhas de respostas iguais de outro cargo.
            physical_texts = [" ".join(str(word.get("text", "")) for word in line) for line in lines]
            selected_texts = context.linhas_do_cargo(physical_texts)
            if selected_texts != physical_texts:
                selected_ids = {id(value) for value in selected_texts}
                lines = [line for line, value in zip(lines, physical_texts) if id(value) in selected_ids]
            wanted_col = _wanted_column(codigo_prova)
            columns = _header_columns(lines)
            candidates = []
            for line in lines:
                candidates.extend(_line_candidates(line, page, "pair", wanted_col, columns))
            candidates += _horizontal_candidates(lines, page)
            # Restrict a selected multiprova to the physical column.  This is
            # deliberately applied after parsing, so two equal answers cannot
            # make the wrong column appear valid.
            if wanted_col is not None and columns and wanted_col < len(columns):
                candidates = [c for c in candidates if min(range(len(columns)), key=lambda idx:
                    abs(sum(float(w.get("x0", 0)) for w in c[2]) / len(c[2]) - columns[idx])) == wanted_col]
            for number, answer, evidence_words, method in candidates:
                if number not in expected:
                    continue
                answer = _canonical_answer(answer, expected[number])
                bbox = _box(evidence_words, page)
                excerpt = " ".join(str(w.get("text", "")) for w in evidence_words)
                observations.setdefault(number, []).append({"resposta": answer, "region": bbox,
                    "metodo": method, "scope_excerpt": excerpt, "page": page_no})
            # A few digitally generated PDFs expose the answer in text but
            # omit its glyph from extract_words.  Recover that exact textual
            # pair only when the explicit header identifies the requested
            # column; the region is the bounded cell around that column.
            if wanted_col is not None and columns:
                for raw_line in text.splitlines():
                    pairs = re.findall(r"(\d{1,3})\s*[-:]\s*([A-E])", raw_line, re.I)
                    seen: dict[int, int] = {}
                    for raw_number, raw_answer in pairs:
                        number, answer = int(raw_number), raw_answer.upper()
                        occurrence = seen.get(number, 0)
                        seen[number] = occurrence + 1
                        if occurrence != wanted_col or number not in expected or number in observations:
                            continue
                        if _canonical_answer(answer, expected[number]) != expected[number]:
                            continue
                        centre = columns[min(wanted_col, len(columns) - 1)]
                        top = next((float(w.get("top", 0)) for w in words if _token(w) == raw_number), 0.0)
                        bbox = {"x0": max(0.0, centre - 38), "top": top,
                                "x1": min(float(page.width), centre + 38), "bottom": top + 14,
                                "width": 76.0, "height": 14.0, "rotation": 0}
                        observations.setdefault(number, []).append({"resposta": answer, "region": bbox,
                            "metodo": "text_pair_geometry", "scope_excerpt": raw_line.strip(), "page": page_no})
    finally:
        try:
            pdf.close()
        except Exception:
            pass
    # A few official PDFs embed the same complete answer board twice (for
    # example once in each copy of a downloadable booklet).  Two physical
    # observations are safe to collapse only when the *entire* requested
    # board is present on both pages and every value agrees.  Partial or
    # conflicting boards remain ambiguous and fail closed below.
    page_maps: dict[int, dict[int, str]] = {}
    for number, found in observations.items():
        for item in found:
            page_maps.setdefault(item["page"], {})[number] = item["resposta"]
    duplicate_pages: set[int] = set()
    expected_keys = set(expected)
    pages = list(page_maps)
    for index, first in enumerate(pages):
        if set(page_maps[first]) != expected_keys:
            continue
        for second in pages[index + 1:]:
            if page_maps[second] == page_maps[first] and set(page_maps[second]) == expected_keys:
                duplicate_pages.update({first, second})
    for number, expected_value in expected.items():
        found = observations.get(number, [])
        values = {x["resposta"] for x in found}
        if values and (len(values) > 1 or (expected_value is not None and expected_value not in values)):
            result["issues"].append(f"answer_conflict:{number}")
            continue
        unique = {(x["page"], tuple(sorted(x["region"].items()))) for x in found}
        if not found:
            result["issues"].append(f"answer_missing:{number}")
        elif len(unique) != 1:
            found_pages = {x["page"] for x in found}
            if found_pages.issubset(duplicate_pages) and len(values) == 1:
                item = found[0].copy()
                item.pop("page", None)
                item["metodo"] = "duplicado_identico"
                raw = item["region"]
                item["region"] = {"page": found[0]["page"],
                                   "bbox": [raw["x0"], raw["top"], raw["x1"], raw["bottom"]],
                                   "width": raw["width"], "height": raw["height"],
                                   "rotation": raw["rotation"]}
                result["answers"][number] = item
            else:
                result["issues"].append(f"answer_ambiguous:{number}")
        else:
            item = found[0].copy()
            item.pop("page", None)
            raw = item["region"]
            item["region"] = {"page": found[0]["page"],
                               "bbox": [raw["x0"], raw["top"], raw["x1"], raw["bottom"]],
                               "width": raw["width"], "height": raw["height"],
                               "rotation": raw["rotation"]}
            result["answers"][number] = item
    return result
