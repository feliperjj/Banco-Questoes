"""Extração geométrica de questões diretamente da fonte PDF.

Este módulo deliberadamente não usa o gabarito nem a posição na lista de
candidatos para inventar números. O número de uma questão somente é aceito
quando existe um marcador físico no PDF e o texto do candidato confirma a
âncora encontrada.
"""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path
from typing import Any

import pdfplumber

from .pdf_render import render_region


_MARKER = re.compile(r"^(?:(?:QUEST(?:ÃO|AO|AO|ÃO)|Q)\s*)?(\d{1,3})[.)\-:]?\s*$", re.I)
_MARKER_INLINE = re.compile(r"^(?:QUEST(?:ÃO|AO|ÃO)|Q)\s*(\d{1,3})[.)\-:]?$", re.I)
_ALT = re.compile(r"^\(?([A-Ea-e])\)?[.)\-:]?\s+")


def readable_source_page(page):
    """Texto digital sem sobreimpressão/rodapé; os pixels originais são preservados."""
    if hasattr(page, "dedupe_chars"):
        page = page.dedupe_chars(tolerance=.3)
    if hasattr(page, "filter"):
        from .pdf_texto import _pagina_sem_texto_rotacionado
        page = _pagina_sem_texto_rotacionado(page)
    return page


def _norm(value: str) -> str:
    import unicodedata
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value or "")
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", value)).strip()


def _words(page):
    cached = getattr(page, "_source_words_cache", None)
    if cached is not None:
        return cached
    try:
        result = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
    except TypeError:
        result = page.extract_words(x_tolerance=2, y_tolerance=3)
    page._source_words_cache = result
    return result


def _lines(words):
    out = []
    for word in sorted(words, key=lambda w: (w.get("top", 0), w.get("x0", 0))):
        if not out or abs(float(word.get("top", 0)) - out[-1][0]) > 3:
            out.append([float(word.get("top", 0)), []])
        out[-1][1].append(word)
    return [(y, sorted(ws, key=lambda w: w.get("x0", 0))) for y, ws in out]


def _marker(line):
    text = " ".join(str(w.get("text", "")) for w in line)
    # A physical marker is either a standalone number token or QUESTÃO N.
    first = str(line[0].get("text", "")) if line else ""
    m = _MARKER.fullmatch(text) or _MARKER_INLINE.fullmatch(text)
    if not m and len(line) == 1:
        m = _MARKER.fullmatch(first)
    if not m:
        return None
    return int(m.group(1))


def _bbox(line, page):
    return {
        "x0": min(float(w.get("x0", 0)) for w in line),
        "top": min(float(w.get("top", 0)) for w in line),
        "x1": max(float(w.get("x1", w.get("x0", 0))) for w in line),
        "bottom": max(float(w.get("bottom", w.get("top", 0))) for w in line),
    }


def _anchor(candidate: dict, text: str) -> bool:
    bits = []
    for key in ("texto", "enunciado", "text"):
        value = candidate.get(key)
        if isinstance(value, str) and len(_norm(value)) >= 12:
            bits.append(" ".join(_norm(value).split()[:10]))
    hay = _norm(text)
    if not bits:
        return True
    if any(0 <= hay.find(bit) <= 100 for bit in bits):
        return True
    # Some scanned two-column PDFs interleave isolated glyphs or introduce a
    # single OCR character inside a word. Keep the anchor ordered and bounded;
    # this is not a bag-of-words fallback.
    hay_words = hay.split()
    for bit in bits:
        expected = bit.split()
        cursor = 0
        skipped = 0
        matched = 0
        for token in expected:
            found = None
            for index in range(cursor, min(len(hay_words), cursor + 4)):
                probe = hay_words[index]
                distance = _edit_distance(token, probe)
                if distance == 0 or (len(token) >= 8 and distance <= 2) or (len(token) >= 5 and distance <= 1):
                    found = index
                    break
            if found is None:
                break
            skipped += found - cursor
            if skipped > 2:
                break
            cursor = found + 1
            matched += 1
        if matched == len(expected):
            return True
    return False


def _edit_distance(left: str, right: str) -> int:
    row = list(range(len(right) + 1))
    for i, char in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, row[j] + 1,
                               row[j - 1] + (char != other)))
        row = current
    return row[-1]


def _anchor_bits(candidate: dict) -> list[str]:
    bits = []
    for key in ("texto", "enunciado", "text"):
        value = candidate.get(key)
        if isinstance(value, str) and len(_norm(value)) >= 12:
            bits.append(" ".join(_norm(value).split()[:10]))
    return bits


def _contains_anchor(candidate: dict, text: str) -> bool:
    """Match an explicit source anchor, without fuzzy bag-of-words matching."""
    hay = _norm(text)
    return any(bit and bit in hay for bit in _anchor_bits(candidate))


def _contains_complete_support(support: str, text: str) -> bool:
    """Context support is authoritative only when the complete text is present."""
    needle = _norm(support)
    hay = _norm(text)
    return bool(needle) and needle in hay


def _trim_header_footer(page, bbox):
    # Header/footer removal is geometric and conservative: only repeated-looking
    # edge lines are removed, never body lines or long alternatives.
    x0, top, x1, bottom = bbox
    height = float(page.height)
    return (x0, max(top, 0), x1, min(bottom, height))


def _column_bounds(page, marker, physical):
    """Return the physical reading column, allowing genuine single-column PDFs."""
    page_marks = [m for m in physical if m["page"] == marker["page"]]
    right_marks = [m for m in page_marks if m["bbox"]["x0"] >= float(page.width) / 2]
    left_marks = [m for m in page_marks if m["bbox"]["x0"] < float(page.width) / 2]
    if not right_marks or not left_marks:
        if not any(m.get("profile") == "transpetro_arial_bold_v1" for m in page_marks):
            words = _words(page)
            middle = float(page.width) / 2
            body = [w for w in words if 60 < float(w.get("top", 0)) < float(page.height) - 40]
            crossing = sum(float(w.get("x0", 0)) < middle - 2 and float(w.get("x1", 0)) > middle + 2 for w in body)
            both_sides = (sum(float(w.get("x0", 0)) < middle - 25 for w in body) > 15
                          and sum(float(w.get("x0", 0)) > middle + 25 for w in body) > 15)
            if crossing >= 3 or not both_sides:
                return 0.0, float(page.width)
    return ((0.0, float(page.width) / 2) if marker["column"] == 0
            else (float(page.width) / 2, float(page.width)))


def _region_text(page, bbox):
    cache = getattr(page, "_source_region_text_cache", None)
    if cache is None:
        page._source_region_text_cache = cache = {}
    key = tuple(float(value) for value in bbox)
    if key not in cache:
        cache[key] = page.crop(bbox).extract_text(x_tolerance=2, y_tolerance=3) or ""
    return cache[key]


def _raw_region_text(page, bbox):
    while getattr(page, "parent_page", None) is not None:
        page = page.parent_page
    return _region_text(page, bbox)


def _context_physical_regions(pdf, physical, target):
    """Build ordered, bounded regions preceding a question marker."""
    regions = []
    for page_no in range(1, target["page"] + 1):
        page = pdf.pages[page_no - 1]
        marks = [m for m in physical if m["page"] == page_no]
        if marks:
            by_column = {index: [m for m in marks if m["column"] == index] for index in (0, 1)}
            if by_column[0] and by_column[1]:
                columns = [(0.0, float(page.width) / 2, 0),
                           (float(page.width) / 2, float(page.width), 1)]
            else:
                representative = marks[0]
                left, right = _column_bounds(page, representative, physical)
                columns = [(left, right, representative["column"])]
        else:
            columns = [(0.0, float(page.width), 0)]
        for left, right, column in columns:
            if page_no == target["page"] and column > target["column"]:
                continue
            bottom = float(page.height)
            if page_no == target["page"] and column == target["column"]:
                bottom = float(target["bbox"]["top"])
            if bottom <= 1:
                continue
            bbox = _trim_header_footer(page, (left, 0.0, right, bottom))
            text = _region_text(page, bbox)
            if text.strip():
                regions.append({"page": page_no, "column": column, "bbox": bbox, "text": text,
                                "raw_text": _raw_region_text(page, bbox)})
    return regions


def _image_context_region(page, number, physical):
    """Find an explicit ``Imagem/Figura ... itens N a M`` support block."""
    words = _words(page)
    for _, line in _lines(words):
        line_text = " ".join(str(word.get("text", "")) for word in line)
        match = re.search(r"(?i)(?:imagem|figura)\s+para\s+responder\s+aos\s+itens\s+de\s*(\d+)\s*a\s*(\d+)", line_text)
        if not match or not int(match.group(1)) <= number <= int(match.group(2)):
            continue
        # The caption line can share a baseline with the other column header;
        # keep only the words through the explicit range endpoint.
        endpoint = next((index for index, word in enumerate(line)
                         if str(word.get("text", "")) == match.group(2) + "."), len(line) - 1)
        caption_words = line[:endpoint + 1]
        top = min(float(word.get("top", 0)) for word in line)
        left = min(float(word.get("x0", 0)) for word in caption_words)
        right = max(float(word.get("x1", word.get("x0", 0))) for word in caption_words)
        column = 0 if left < float(page.width) / 2 else 1
        # The first marker in this column after the caption bounds the image;
        # otherwise use the page bottom conservatively.
        markers = [m for m in physical if m["bbox"]["top"] > top + 20
                   and ((column == 0 and m["bbox"]["x0"] < float(page.width) / 2)
                        or (column == 1 and m["bbox"]["x0"] >= float(page.width) / 2))]
        bottom = min((m["bbox"]["top"] for m in markers), default=float(page.height)) - 2
        nearby = [word for word in words if top - 8 <= float(word.get("top", 0)) < bottom
                  and ((column == 0 and float(word.get("x0", 0)) < float(page.width) / 2)
                       or (column == 1 and float(word.get("x0", 0)) >= float(page.width) / 2))]
        if nearby:
            left = min(left, min(float(word.get("x0", 0)) for word in nearby))
            right = max(right, max(float(word.get("x1", word.get("x0", 0))) for word in nearby))
        return (max(0.0, left - 2), max(0.0, top - 2),
                min(float(page.width), right + 2), min(float(page.height), bottom))
    return None


def _render_asset(pdf_path: Path, source_hash: str, page_no: int, bbox, asset_dir: Path, prefix="q"):
    try:
        scale = 2.0
        x0, top, x1, bottom = map(float, bbox)
        if x1 <= x0 or bottom <= top:
            return None
        asset_dir.mkdir(parents=True, exist_ok=True)
        key = f"{source_hash}-p{page_no}-{x0:.2f}-{top:.2f}-{x1:.2f}-{bottom:.2f}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        path = asset_dir / f"{prefix}-{digest}.png"
        rendered = render_region(pdf_path, page_no, (x0, top, x1, bottom), scale=scale, output=path)
        return {"path": str(rendered.get("path", path)),
                "sha256": rendered.get("sha256") or hashlib.sha256(path.read_bytes()).hexdigest(),
                "scale": scale}
    except Exception:
        return None


def extract_pdf_source(path, *, expected_questions: list[dict], asset_dir: Path | None = None) -> dict:
    """Extract independently bounded, source-backed question regions.

    Ambiguity is fail-closed: duplicate physical numbers, missing anchors and
    incomplete alternatives are reported in ``issues`` and are not certified.
    """
    pdf_path = Path(path)
    source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    result = {"source_sha256": source_hash, "profile": "pdf_fonte_geometrico_v1",
              "questions": [], "issues": []}
    expected_questions = expected_questions or []
    try:
        pdf = pdfplumber.open(str(pdf_path))
    except Exception as exc:
        result["issues"].append(f"pdf_open:{exc}")
        return result
    pdf.pages[:] = [readable_source_page(page) for page in pdf.pages]
    physical = []
    transpetro_profile = "transpetro" in pdf_path.name.casefold()
    cebraspe_profile = "cebraspe" in pdf_path.name.casefold()
    if not cebraspe_profile:
        for sample_page in pdf.pages[:2]:
            sample_text = sample_page.extract_text() if hasattr(sample_page, "extract_text") else ""
            if "CEBRASPE" in (sample_text or "").upper():
                cebraspe_profile = True
                break
    after_discursive = False
    page_words_cache = {}
    for page_no, page in enumerate(pdf.pages, 1):
        page_plain = page.extract_text() if hasattr(page, "extract_text") else ""
        page_plain = page_plain or ""
        if after_discursive or re.search(r"(?im)^\s*PROVA\s+DISCURSIVA\b", page_plain):
            after_discursive = True
            continue
        if re.search(r"(?im)^\s*RASCUNHO\s*$", page_plain) and len(page_plain.strip()) < 300:
            continue
        if transpetro_profile and page_no == 1:
            continue
        words = _words(page)
        page_words_cache[page_no] = words
        if transpetro_profile:
            # TRANSPETRO's verified source profile: Arial Bold 11 markers at
            # x=28/310, with two fixed content columns. Restricting by font,
            # size and geometry avoids question numbers in headers/tables.
            words = page.extract_words(x_tolerance=2, y_tolerance=3,
                                       extra_attrs=["fontname", "size"])
            for word in words:
                token = str(word.get("text", ""))
                if (token.isdigit() and 1 <= int(token) <= 70
                        and "Bold" in str(word.get("fontname", ""))
                        and float(word.get("size", 0)) >= 10
                        and (28 <= float(word.get("x0", 0)) <= 38 or 310 <= float(word.get("x0", 0)) <= 320)
                        and 60 < float(word.get("top", 0)) < 770):
                    box = _bbox([word], page)
                    col = 0 if box["x0"] < page.width / 2 else 1
                    physical.append({"numero": int(token), "page": page_no, "bbox": box,
                                     "column": col, "marker_text": token, "marker_bbox": box,
                                     "profile": "transpetro_arial_bold_v1"})
            continue
        # FGV booklets in the sample family use Calibri/Calibri-Bold 8--9pt
        # markers aligned to the same two left margins. Require multiple
        # aligned markers on a page before activating this profile so ordinary
        # body numbers are never promoted to question numbers.
        fgv_words = page.extract_words(x_tolerance=2, y_tolerance=3,
                                       extra_attrs=["fontname", "size"])
        fgv_markers = [w for w in fgv_words
                       if str(w.get("text", "")).isdigit()
                       and 1 <= int(w["text"]) <= 200
                       and "Calibri" in str(w.get("fontname", ""))
                       and 7.5 <= float(w.get("size", 0)) <= 9.5
                       and (40 <= float(w.get("x0", 0)) <= 52 or 305 <= float(w.get("x0", 0)) <= 320)
                       and 60 < float(w.get("top", 0)) < 770]
        if len(fgv_markers) >= 2:
            for word in fgv_markers:
                box = _bbox([word], page)
                col = 0 if box["x0"] < page.width / 2 else 1
                physical.append({"numero": int(word["text"]), "page": page_no,
                                 "bbox": box, "column": col,
                                 "marker_text": word["text"], "marker_bbox": box,
                                 "profile": "fgv_calibri_8_9_v1"})
            continue
        for y, line in _lines(words):
            number = _marker(line)
            marker_lines = [(number, line)] if number is not None else []
            if not marker_lines and len(line) >= 2:
                for index in range(len(line) - 1):
                    prefix = " ".join(str(word.get("text", "")) for word in line[index:index + 2])
                    explicit = re.fullmatch(r"(?i)QUEST\D*\s+([0-9]{1,3})[.)\-:]?", prefix)
                    if explicit:
                        marker_lines.append((int(explicit.group(1)), line[index:index + 2]))
            # Columns often put two physical markers on the same baseline. A
            # punctuated numeric token at a page margin is still a marker even
            # though the complete visual line contains the other column.
            if not marker_lines:
                for word in line:
                    token = str(word.get("text", ""))
                    m = re.fullmatch(r"(\d{1,3})[.)\-:]", token)
                    if m:
                        marker_lines.append((int(m.group(1)), [word]))
            for number, marker_line in marker_lines:
                box = _bbox(marker_line, page)
                # Marker columns are kept separate; this prevents Q68/Q70 in two
                # columns from becoming one region when their vertical ranges cross.
                col = 0 if box["x0"] < float(page.width) / 2 else 1
                physical.append({"numero": number, "page": page_no, "bbox": box,
                                 "column": col, "marker_text": " ".join(w.get("text", "") for w in marker_line),
                                 "marker_bbox": box})
    # Recover aligned markers whose embedded font metadata is unreliable.
    # Expected text is used only as a local, unique anchor; order/count never
    # supplies a missing number.
    known = set()
    for expected in expected_questions:
        number = expected.get("numero")
        if not isinstance(number, int) or number in known:
            continue
        hits = []
        for page_no, page in enumerate(pdf.pages, 1):
            words = page_words_cache.get(page_no)
            if words is None:
                words = _words(page)
                page_words_cache[page_no] = words
            for word in words:
                token = str(word.get("text", ""))
                x = float(word.get("x0", 0))
                numeric = re.fullmatch(r"0*(\d{1,3})[.)\-:]?", token)
                if not numeric or int(numeric.group(1)) != number or not (x < page.width * .20 or page.width * .45 < x < page.width * .60):
                    continue
                col = 0 if x < page.width / 2 else 1
                probe_marker = {"page": page_no, "column": col, "bbox": _bbox([word], page)}
                left, right = _column_bounds(page, probe_marker, physical)
                probe_box = (left, float(word.get("top", 0)), right,
                             min(float(page.height), float(word.get("top", 0)) + 250))
                probe = page.crop(probe_box).extract_text() or ""
                if _anchor(expected, probe) or _anchor(expected, _raw_region_text(page, probe_box)):
                    hits.append((page_no, word, col))
        if len(hits) == 1:
            page_no, word, col = hits[0]
            box = _bbox([word], pdf.pages[page_no - 1])
            physical.append({"numero": number, "page": page_no, "bbox": box,
                             "column": col, "marker_text": str(number),
                             "marker_bbox": box, "profile": "anchor_margin_v1"})
            known.add(number)
        elif len(hits) > 1:
            result["issues"].append(f"marcador_ambiguo_ancora:{number}")
    # Font-profile and fallback discovery can observe the same printed glyph
    # twice with tiny coordinate differences. Collapse only same-page nearby
    # bboxes; distinct pages/regions remain a hard ambiguity.
    # Elimina números de parágrafo/cabeçalho ANTES de tratar duplicatas.
    # Um número isolado sem a âncora imediata da sua questão não é marcador.
    anchored = []
    expected_by_number = {q.get("numero"): q for q in expected_questions if isinstance(q.get("numero"), int)}
    for marker in physical:
        expected = expected_by_number.get(marker["numero"])
        page = pdf.pages[marker["page"] - 1]
        left, right = _column_bounds(page, marker, physical)
        probe_box = (left, marker["bbox"]["top"], right, min(page.height, marker["bbox"]["top"] + 250))
        probe = page.crop(probe_box).extract_text() or ""
        if expected is None or _anchor(expected, probe) or _anchor(expected, _raw_region_text(page, probe_box)):
            anchored.append(marker)
    physical = anchored
    unique_physical = []
    for marker in physical:
        duplicate = any(marker["numero"] == prior["numero"]
                        and marker["page"] == prior["page"]
                        and marker["column"] == prior["column"]
                        and abs(marker["bbox"]["top"] - prior["bbox"]["top"]) <= 3
                        for prior in unique_physical)
        if not duplicate:
            unique_physical.append(marker)
    physical = unique_physical
    by_number = {}
    for mark in physical:
        by_number.setdefault(mark["numero"], []).append(mark)
    for number, marks in by_number.items():
        if len(marks) > 1:
            result["issues"].append(f"marcador_duplicado:{number}")
    used = set()
    for mark in physical:
        candidates = [q for q in expected_questions if q.get("numero") in (None, mark["numero"])]
        candidates = [q for q in candidates if _anchor(q, mark["marker_text"])] or candidates
        # Anchor against the eventual crop, not the marker itself.
        page = pdf.pages[mark["page"] - 1]
        same = [m for m in physical if m["page"] == mark["page"] and m["column"] == mark["column"]
                and (m["bbox"]["top"] > mark["bbox"]["top"] or m is mark)]
        following = min((m["bbox"]["top"] for m in same if m is not mark), default=float(page.height) - 8)
        col_left, col_right = _column_bounds(page, mark, physical)
        bbox = _trim_header_footer(page, (col_left, mark["bbox"].get("top", 0), col_right, following))
        text = _region_text(page, bbox)
        raw_text = _raw_region_text(page, bbox)
        candidate = next((q for q in candidates if _anchor(q, text) or _anchor(q, raw_text)), None)
        if candidate is None:
            result["issues"].append(f"ancora_nao_encontrada:{mark['numero']}")
        if mark["numero"] in used:
            continue
        used.add(mark["numero"])
        alts = sorted(set(m.group(1).upper() for m in (_ALT.match(line) for line in text.splitlines()) if m))
        # A phrase such as "julgue" may occur inside an ordinary FGV stem;
        # only the booklet-level CEBRASPE profile can change the source type.
        source_is_cebraspe = cebraspe_profile
        q = {"numero": mark["numero"], "enunciado": text.strip(),
             "tipo": "julgamento" if source_is_cebraspe else ("multipla_escolha" if alts else "julgamento"),
             "alternativas": alts, "texto_apoio": "", "regions": [{"page": mark["page"], "bbox": bbox,
             "width": bbox[2] - bbox[0], "height": bbox[3] - bbox[1], "rotation": 0,
             "marker_text": mark["marker_text"], "marker_bbox": mark["marker_bbox"]}],
             "context_regions": [], "assets": [], "context_assets": [], "checks": {}, "issues": []}
        if source_is_cebraspe:
            q["alternativas"] = []
        image_context = _image_context_region(page, mark["numero"], physical)
        if image_context:
            region = {"page": mark["page"], "bbox": image_context,
                      "width": image_context[2] - image_context[0],
                      "height": image_context[3] - image_context[1], "rotation": 0,
                      "context_kind": "imagem_itens"}
            q["context_regions"].append(region)
            image_text = _region_text(page, image_context)
            q["texto_apoio"] = image_text.strip()
            if asset_dir:
                asset = _render_asset(pdf_path, source_hash, mark["page"], image_context,
                                      Path(asset_dir), prefix="context")
                if asset:
                    q["context_assets"].append({**asset, "region_index": 0})
                else:
                    q["issues"].append("context_asset_nao_gerado")
        expected_source_letters = []
        if candidate and isinstance(candidate.get("alternativas"), list):
            expected_source_letters = [str(option.get("letra") if isinstance(option, dict) else option).strip().upper()
                                       for option in candidate["alternativas"]]
            expected_source_letters = [letter for letter in expected_source_letters if letter]
        continuation_needed = bool(expected_source_letters and alts != expected_source_letters)
        if not source_is_cebraspe and alts and continuation_needed:
            next_marks = sorted((m for m in physical if m["page"] == mark["page"]
                                 and m["column"] == mark["column"] + 1
                                 and m["bbox"]["top"] >= mark["bbox"]["top"]),
                                key=lambda m: m["bbox"]["top"])
            if next_marks:
                nxt = next_marks[0]
                other_left, other_right = _column_bounds(page, nxt, physical)
                cb = _trim_header_footer(page, (other_left, 0.0, other_right, nxt["bbox"]["top"]))
                continuation = _region_text(page, cb)
                continuation_alts = [m.group(1).upper() for m in
                                     (_ALT.match(line) for line in continuation.splitlines()) if m]
                expected_next = (expected_source_letters[len(alts)]
                                 if len(alts) < len(expected_source_letters) else None)
                if (expected_next and continuation_alts and continuation_alts[0] == expected_next
                        and continuation_alts[:len(expected_source_letters) - len(alts)]
                        == expected_source_letters[len(alts):]):
                    text = (text.rstrip() + "\n" + continuation.lstrip()).strip()
                    alts = alts + continuation_alts
                    q["enunciado"] = text
                    q["alternativas"] = alts
                    q["regions"].append({"page": mark["page"], "bbox": cb,
                                         "width": cb[2] - cb[0], "height": cb[3] - cb[1],
                                         "rotation": 0, "continuation": True})
                    if asset_dir:
                        asset = _render_asset(pdf_path, source_hash, mark["page"], cb,
                                              Path(asset_dir), prefix="q-continuation")
                        if asset:
                            q["assets"].append({**asset, "region_index": len(q["regions"]) - 1})
                        else:
                            q["issues"].append("asset_nao_gerado")
        if transpetro_profile and mark["numero"] in range(1, 21):
            # The cover explicitly assigns Portuguese Q1-10 and English Q11-20.
            # Their shared support blocks are on the top of pages 2 and 4.
            context_page_no = 2 if mark["numero"] <= 10 else 4
            if context_page_no <= len(pdf.pages):
                context_page = pdf.pages[context_page_no - 1]
                first = min((m["bbox"]["top"] for m in physical
                             if m["page"] == context_page_no and m["numero"] in
                             (1, 11)), default=120)
                if mark["numero"] <= 10:
                    boxes = [(28, 120, 289, 770), (310, 70, 568, first - 2)]
                else:
                    boxes = [(28, 70, 289, 770), (310, 70, 568, first - 2)]
                context_parts = []
                for region_index, cb in enumerate(boxes):
                    context_text = context_page.crop(cb).extract_text(x_tolerance=2, y_tolerance=3) or ""
                    context_parts.append(context_text)
                    region = {"page": context_page_no, "bbox": cb, "width": cb[2] - cb[0],
                              "height": cb[3] - cb[1], "rotation": 0}
                    q["context_regions"].append(region)
                    if asset_dir:
                        asset = _render_asset(pdf_path, source_hash, context_page_no, cb,
                                              Path(asset_dir), prefix="context")
                        if asset:
                            q["context_assets"].append({**asset, "region_index": region_index})
                        else:
                            q["issues"].append("context_asset_nao_gerado")
                q["texto_apoio"] = "\n".join(part.strip() for part in context_parts if part.strip())
        # Shared support text is kept outside the question crop. Only attach
        # it when the candidate supplies an explicit support-text anchor and
        # that anchor occurs above the physical marker on the same page.
        support = ""
        for key in ("texto_apoio", "contexto", "texto_base"):
            value = candidate.get(key) if candidate else None
            if isinstance(value, str) and len(_norm(value)) >= 12:
                support = value
                break
        if support and not q["context_regions"]:
            # Context is accepted only when its complete explicit anchor is
            # present in a bounded physical page/column region. Search prior
            # pages as well as the preceding part of the current page; this
            # handles support text that starts on the previous column/page
            # without ever borrowing a same-number-looking block from another
            # booklet.
            context_hit = None
            context_pool = _context_physical_regions(pdf, physical, mark)
            # Search contiguous physical regions in reading order. This allows
            # support to flow from a left column to a right column or to the
            # next page, while preserving every evidence rectangle.
            for end in range(len(context_pool)):
                joined = ""
                raw_joined = ""
                for start in range(end, -1, -1):
                    joined = context_pool[start]["text"] + "\n" + joined
                    raw_joined = context_pool[start]["raw_text"] + "\n" + raw_joined
                    if _contains_complete_support(support, joined) or _contains_complete_support(support, raw_joined):
                        context_hit = (context_pool[start:end + 1], joined.strip())
                        break
                if context_hit:
                    break
            if context_hit:
                hit_regions, context_text = context_hit
                q["texto_apoio"] = context_text.strip()
                for region_index, hit in enumerate(hit_regions):
                    cb = hit["bbox"]
                    region = {"page": hit["page"], "bbox": cb, "width": cb[2] - cb[0],
                              "height": cb[3] - cb[1], "rotation": 0}
                    q["context_regions"].append(region)
                    if asset_dir:
                        asset = _render_asset(pdf_path, source_hash, hit["page"], cb,
                                              Path(asset_dir), prefix="context")
                        if asset:
                            q["context_assets"].append({**asset, "region_index": region_index})
                        else:
                            q["issues"].append("context_asset_nao_gerado")
            else:
                q["issues"].append("contexto_necessario_nao_encontrado")
        expected_alternatives = []
        if candidate and isinstance(candidate.get("alternativas"), list):
            for option in candidate["alternativas"]:
                letra = option.get("letra") if isinstance(option, dict) else option
                if isinstance(letra, str) and letra.strip():
                    expected_alternatives.append(letra.strip().upper())
        q["expected_alternatives"] = expected_alternatives
        alternatives_match = (not expected_alternatives or alts == expected_alternatives
                              or source_is_cebraspe)
        q["checks"] = {"marker_physical": True, "anchor_confirmed": candidate is not None,
                        "region_valid": bbox[2] > bbox[0] and bbox[3] > bbox[1],
                        "alternatives_complete": (not alts or alternatives_match)}
        if not q["checks"]["region_valid"]:
            q["issues"].append("regiao_invalida")
        if alts and not q["checks"]["alternatives_complete"]:
            q["issues"].append("alternativas_incompletas")
        if candidate is None:
            q["issues"].append("ancora_nao_encontrada")
        if asset_dir:
            asset = _render_asset(pdf_path, source_hash, mark["page"], bbox, Path(asset_dir))
            if asset:
                q["assets"].append({**asset, "region_index": 0})
            else:
                q["issues"].append("asset_nao_gerado")
        q["enunciado_original"] = "\n".join(_raw_region_text(pdf.pages[region["page"] - 1], region["bbox"])
                                                   for region in q["regions"])
        result["questions"].append(q)
    pdf.close()
    result["questions"].sort(key=lambda q: q["numero"])
    observed = {q["numero"] for q in result["questions"]}
    result["issues"].extend(f"ancora_nao_encontrada:{number}" for number in expected_by_number if number not in observed)
    if cebraspe_profile:
        result["profile"] = "cebraspe_recuado_geometrico_v1"
    return result
