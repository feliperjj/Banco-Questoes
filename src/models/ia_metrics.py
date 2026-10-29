"""Medições locais de uso; não são labels humanos nem prova de tempo economizado."""
import json
import math
from pathlib import Path
from uuid import uuid4

from src.config import DATA_DIR


def record_session(*, field, assisted, outcome, elapsed_seconds, waiting_seconds=0, directory=None):
    if type(assisted) is not bool or outcome not in {'salvou', 'cancelou'}:
        raise ValueError('Medição de sessão inválida.')
    for value in (elapsed_seconds, waiting_seconds):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Duração inválida.')
    if waiting_seconds > elapsed_seconds + .01:
        raise ValueError('Espera maior que a sessão.')
    root = Path(directory or DATA_DIR / 'ia_local/metricas')
    root.mkdir(parents=True, exist_ok=True)
    path = root / (uuid4().hex + '.json')
    value = {'schema_version': 1, 'field': str(field), 'assisted': assisted, 'outcome': outcome,
             'elapsed_seconds': round(elapsed_seconds, 3), 'waiting_seconds': round(waiting_seconds, 3),
             'human_training_label': False}
    temporary = path.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(value), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def summarize_sessions(directory=None):
    groups = {'manual': [], 'assistido': []}
    for path in Path(directory or DATA_DIR / 'ia_local/metricas').glob('*.json'):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if value.get('schema_version') != 1 or value.get('outcome') != 'salvou' or type(value.get('assisted')) is not bool:
                continue
            seconds = value.get('elapsed_seconds')
            if type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0:
                groups['assistido' if value['assisted'] else 'manual'].append(seconds)
        except (OSError, ValueError):
            continue
    return {name: {'sessions': len(values), 'mean_seconds': round(sum(values) / len(values), 3) if values else None}
            for name, values in groups.items()} | {
                'time_saved_verified': False,
                'note': 'Tempos observados não comprovam economia sem comparação humana controlada de casos equivalentes.'}
