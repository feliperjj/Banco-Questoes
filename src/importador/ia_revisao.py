"""Evidência física e comparação de leituras; nunca aprova questões ou gabaritos."""
from __future__ import annotations

from io import BytesIO
from contextlib import nullcontext
import hashlib
import json
import math
from pathlib import Path
import re
import time
import unicodedata
from uuid import uuid4

import pdfplumber

from src.config import DATA_DIR
from .pdf_render import render_image, rendering_batch

POLICY_VERSION = 'local-review-v2'
_LABEL = re.compile(r'^\s*\(?([A-Ea-e])[.)]\s*')


def file_hash(path):
    path = Path(path)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('O arquivo mudou durante a leitura. Reabra a fonte.')
    return digest.hexdigest()


def normalize(text):
    text = re.sub(r'(?<=\w)-\s*\n\s*(?=\w)', '', text or '')
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip()


def _cancel(event):
    if event is not None and event.is_set():
        raise InterruptedError('Análise cancelada.')


def _png(image):
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _word_lines(words):
    lines = []
    for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if not lines or abs(word['top'] - lines[-1][0]['top']) > 3:
            lines.append([])
        lines[-1].append(word)
    return [sorted(line, key=lambda w: w['x0']) for line in lines]


def _native_target(page, bounds, letter):
    """Exige marcador único; não escolhe alternativa pela posição na lista."""
    words = [w for w in page.crop(bounds).extract_words(x_tolerance=2, y_tolerance=3)
             if w.get('upright', True)]
    markers = []
    for word in words:
        match = _LABEL.match(word['text'])
        if match and match.group(1).upper() == letter:
            markers.append(word)
    if len(markers) != 1:
        return None, 'marcador_ausente' if not markers else 'marcador_repetido'
    marker = markers[0]
    x0, y0, x1, y1 = bounds
    # A fronteira da coluna só é inferida quando há outros marcadores alinhados
    # na metade direita; sem isso mantém o recorte explicitamente selecionado.
    if marker['x0'] < page.width / 2 and any(
            _LABEL.match(w['text']) and w['x0'] > page.width / 2 for w in words):
        x1 = min(x1, page.width / 2)
    column = [w for w in words if marker['x0'] - 3 <= w['x0'] < x1
              and w['top'] >= marker['top'] - 2]
    selected = []
    previous_bottom = marker['bottom']
    height = max(6, marker['bottom'] - marker['top'])
    for line in _word_lines(column):
        first = line[0]
        if selected:
            next_label = _LABEL.match(first['text'])
            aligned = abs(first['x0'] - marker['x0']) <= 4
            if next_label and aligned:
                if next_label.group(1).upper() > letter:
                    break
                return None, 'limite_ambiguo'
            if aligned and re.match(r'^\d{1,3}[.)]?$', first['text']):
                return None, 'limite_ambiguo'
            if re.match(r'^(RASCUNHO|L[ÍI]NGUA|TRANSPETRO|www\.)', first['text'], re.I):
                return None, 'limite_ambiguo'
            if first['top'] - previous_bottom > height * 1.0:
                # Espaço em branco não comprova o fim de uma alternativa.
                # Não devolve o prefixo como se fosse uma transcrição completa.
                return None, 'limite_ambiguo'
        selected.extend(line)
        previous_bottom = max(w['bottom'] for w in line)
    if not selected:
        return None, 'trecho_nao_delimitado'
    full_words = [w for w in page.extract_words(x_tolerance=2, y_tolerance=3)
                  if w.get('upright', True) and marker['x0'] - 3 <= w['x0'] < x1
                  and marker['top'] - 1 <= w['top'] <= y1 + height * 1.2]
    for word in full_words:
        if word['top'] < y1 and word['bottom'] > y1 + .1:
            return None, 'trecho_cortado'
        if word['top'] >= y1 and word['top'] - previous_bottom <= height:
            if not (_LABEL.match(word['text']) or re.match(r'^\d{1,3}[.)]?$', word['text'])):
                return None, 'trecho_cortado'
    result = (max(x0, marker['x0'] - .5), max(y0, marker['top'] - .25),
              min(x1, max(w['x1'] for w in selected) + 1), min(y1, previous_bottom + .25))
    return result, 'marcador_pdf'


def _ocr_target(lines, letter, bounds, scale):
    matches = [item for item in lines if item['confidence'] >= .85
               and (match := _LABEL.match(item['text'])) and match.group(1).upper() == letter]
    if len(matches) != 1:
        return None
    match = matches[0]
    left, top, right, bottom = match['bbox']
    # O marcador não comprova que a alternativa ocupa uma única linha.
    # Conserva a região até o próximo rótulo alinhado ou o limite selecionado.
    if not _LABEL.sub('', match['text'], count=1).strip():
        return None
    x0, y0, x1, y1 = bounds
    next_markers = [item for item in lines if item['confidence'] >= .85
        and item['bbox'][1] > bottom and abs(item['bbox'][0] - left) <= 8
        and _LABEL.match(item['text'])]
    limit = y1
    if next_markers:
        following = min(next_markers, key=lambda item: item['bbox'][1])
        if _LABEL.match(following['text']).group(1).upper() <= letter:
            return None
        limit = min(y1, y0 + following['bbox'][1] / scale - .5)
    return (max(x0, x0 + left / scale - .5), max(y0, y0 + top / scale - .5), x1, limit)


def _target_text(text, letter):
    if letter is None:
        return text.strip() or None
    match = _LABEL.match(text)
    if not match or match.group(1).upper() != letter:
        return None
    remaining = text[match.end():].strip()
    if re.search(r'(?m)^\s*\(?[A-Ea-e][.)]\s+', remaining):
        return None
    return remaining or None


def _ocr_text(lines):
    """Agrupa detecções da mesma linha antes de ordenar esquerda para direita."""
    rows = []
    for item in sorted(lines, key=lambda l: (l['bbox'][1] + l['bbox'][3]) / 2):
        if item['confidence'] < .65:
            continue
        center = (item['bbox'][1] + item['bbox'][3]) / 2
        height = item['bbox'][3] - item['bbox'][1]
        if not rows or abs(center - rows[-1][0]) > max(4, height * .5):
            rows.append([center, []])
        rows[-1][1].append(item)
    return '\n'.join(' '.join(i['text'] for i in sorted(row, key=lambda l: l['bbox'][0]))
                     for _, row in rows)


@rendering_batch
def prepare_evidence(path, page_number, bounds, *, letter=None, expected_sha256=None,
                     cancel_event=None, reader=None):
    """Retorna texto/imagem ligados ao hash real, inclusive diagnóstico negativo."""
    _cancel(cancel_event)
    path = Path(path).resolve()
    source_hash = file_hash(path)
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise ValueError('A fonte está ausente ou alterada. Reabra o PDF original.')
    if type(page_number) is not int or page_number < 1:
        raise ValueError('Selecione uma página válida.')
    if len(bounds) != 4 or any(isinstance(v, bool) for v in bounds):
        raise ValueError('Informe quatro coordenadas válidas.')
    bounds = tuple(float(v) for v in bounds)
    if not all(math.isfinite(v) for v in bounds):
        raise ValueError('Informe coordenadas finitas.')
    if letter is not None and letter not in tuple('ABCDE'):
        raise ValueError('Selecione uma alternativa A–E.')
    from .ia_ocr import LocalOcrReader
    owned_reader = reader is None
    reader = reader or LocalOcrReader()
    read = lambda image: reader(image, cancel_event=cancel_event) if isinstance(reader, LocalOcrReader) else reader(image)
    result = {'source_sha256': source_hash, 'path': str(path), 'page': page_number,
              'requested_bounds': list(bounds), 'bounds': list(bounds), 'letter': letter,
              'located': False, 'pdf': '', 'ocr': '', 'image_bytes': b'', 'warnings': []}
    with (reader.batch() if owned_reader else nullcontext()), pdfplumber.open(path) as pdf:
        if page_number > len(pdf.pages):
            raise ValueError('A página selecionada não existe.')
        page = pdf.pages[page_number - 1].dedupe_chars(tolerance=.3)
        if not (0 <= bounds[0] < bounds[2] <= page.width and 0 <= bounds[1] < bounds[3] <= page.height):
            raise ValueError('O recorte precisa ficar dentro da página.')
        target_bounds, reason = (_native_target(page, bounds, letter) if letter else (bounds, 'recorte_selecionado'))
        if reason in {'marcador_repetido', 'trecho_cortado', 'limite_ambiguo'}:
            result['reason'] = reason
            return result
        if target_bounds is None:
            image = render_image(path, page_number, bounds, scale=2, cancel_event=cancel_event)
            try:
                _cancel(cancel_event)
                target_bounds = _ocr_target(read(image), letter, bounds, 2)
            finally:
                image.close()
            reason = 'marcador_ocr' if target_bounds else 'marcador_ausente'
        if target_bounds is not None:
            result['bounds'] = list(target_bounds)
            native = page.within_bbox(target_bounds).extract_text() or ''
            from PIL import ImageOps
            rendered = render_image(path, page_number, target_bounds, scale=3, cancel_event=cancel_event)
            image = ImageOps.expand(rendered, border=8, fill='white')
            rendered.close()
            try:
                _cancel(cancel_event)
                lines = read(image)
                ocr = _ocr_text(lines)
                # OCR pode omitir os parênteses do rótulo. Só recupera o rótulo
                # quando ele foi localizado fisicamente no PDF, no mesmo recorte.
                if letter and reason == 'marcador_pdf' and re.match(r'^' + letter + r'\s+', ocr):
                    ocr = '(' + letter + ') ' + ocr[1:].lstrip()
                result.update(image_bytes=_png(image), pdf=native, ocr=ocr)
            finally:
                image.close()
            result['located'] = bool(_target_text(native, letter) or _target_text(ocr, letter))
    result['reason'] = reason
    _cancel(cancel_event)
    if file_hash(path) != source_hash:
        raise ValueError('A fonte mudou durante a análise.')
    return result


def _valid_transcript(value):
    return (isinstance(value, dict) and set(value) == {'encontrado', 'texto'}
            and type(value['encontrado']) is bool and isinstance(value['texto'], str)
            and (bool(value['texto'].strip()) if value['encontrado'] else value['texto'] == ''))


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def analyze_evidence(evidence, current_text, *, runtime=None, cancel_event=None,
                     cache_dir=None, force_model=False):
    """Acordo de leitores gera só proposta pendente; ausência nunca chama IA."""
    started = time.perf_counter()
    _cancel(cancel_event)
    letter = evidence['letter']
    native = _target_text(evidence['pdf'], letter)
    ocr = _target_text(evidence['ocr'], letter)
    readings = {'pdf': native or '', 'ocr': ocr or '', 'ia': ''}
    result = {'status': 'abster', 'proposal': None, 'readings': readings,
              'reason': evidence.get('reason', ''), 'cache_hit': False, 'model_called': False,
              'requires_review': True, 'automatic_approval': False,
              'region': evidence, 'seconds': 0}
    if not evidence['located']:
        result['reason'] = 'Não foi possível localizar o trecho. Ajuste o recorte; nenhuma IA foi acionada.'
        return result
    if native and ocr and normalize(native) == normalize(ocr) and not force_model:
        text = native
        result['reason'] = 'PDF e OCR concordam; releitura local disponível para conferência.'
    else:
        from .ia_runtime import LocalVisionRuntime
        owned = runtime is None
        runtime = runtime or LocalVisionRuntime()
        try:
            fingerprint = (runtime.fingerprint_for(cancel_event) if hasattr(runtime, 'fingerprint_for')
                           else runtime.fingerprint)
            key = hashlib.sha256(json.dumps({
                'policy': POLICY_VERSION, 'source': evidence['source_sha256'],
                'page': evidence['page'], 'bounds': evidence['bounds'], 'letter': letter,
                'image': hashlib.sha256(evidence['image_bytes']).hexdigest(),
                'runtime': fingerprint,
            }, sort_keys=True).encode()).hexdigest()
            cache_path = Path(cache_dir or DATA_DIR / 'ia_local/cache') / (key + '.json')
            transcript = None
            if cache_path.is_file():
                try:
                    saved = json.loads(cache_path.read_text(encoding='utf-8'))
                    if saved.get('key') == key and _valid_transcript(saved.get('transcript')):
                        transcript = saved['transcript']
                        result['cache_hit'] = True
                except (ValueError, OSError):
                    pass
            if transcript is None:
                result['model_called'] = True
                transcript = runtime.transcribe(evidence['image_bytes'], cancel_event=cancel_event)
                if not _valid_transcript(transcript):
                    raise ValueError('A IA retornou uma transcrição inválida. Confira o original.')
                _atomic_json(cache_path, {'key': key, 'transcript': transcript})
            _cancel(cancel_event)
            if not transcript['encontrado']:
                result['reason'] = 'A IA não conseguiu transcrever o trecho. Confira o original.'
                return result
            text = _target_text(transcript['texto'], letter)
            readings['ia'] = text or transcript['texto']
            # A palavra encontrada=true não prova localização nem fidelidade.
            # O texto deve conter o rótulo físico e concordar com outra leitura.
            support = [v for v in (native, ocr) if v]
            if text is None or not any(normalize(text) == normalize(v) for v in support):
                result['status'] = 'divergencia'
                result['reason'] = 'A leitura da IA diverge da evidência. Compare as leituras com o original.'
                return result
            if len(support) > 1 and len({normalize(v) for v in support + [text]}) != 1:
                result['reason'] = 'Duas leituras concordam e outra diverge. Confira as diferenças com o original antes de salvar.'
            else:
                result['reason'] = 'Transcrição apoiada por outra leitura; confira o original antes de salvar.'
        finally:
            if owned:
                runtime.close()
    result['status'] = 'manter' if normalize(text) == normalize(current_text) else 'proposta'
    result['proposal'] = text if result['status'] == 'proposta' else None
    result['seconds'] = round(time.perf_counter() - started, 3)
    return result


def analyze_region(path, page_number, bounds, current_text, *, letter=None,
                   expected_sha256=None, cancel_event=None, runtime=None,
                   cache_dir=None, reader=None, force_model=False):
    evidence = prepare_evidence(path, page_number, bounds, letter=letter,
        expected_sha256=expected_sha256, cancel_event=cancel_event, reader=reader)
    result = analyze_evidence(evidence, current_text, runtime=runtime,
        cancel_event=cancel_event, cache_dir=cache_dir, force_model=force_model)
    if file_hash(path) != evidence['source_sha256']:
        raise ValueError('A fonte mudou durante a análise. Reabra o original.')
    return result
