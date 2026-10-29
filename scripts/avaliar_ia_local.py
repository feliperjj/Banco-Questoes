"""Benchmark local auditável de sugestões, sem abrir o banco do aplicativo."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--force-model', action='store_true', help='Mede IA mesmo quando PDF/OCR já concordam.')
    parser.add_argument('--no-model', action='store_true', help='Mede somente localização e leitores locais.')
    args = parser.parse_args()
    if args.force_model and args.no_model:
        parser.error('--force-model e --no-model são mutuamente exclusivos')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ['BANCO_QUESTOES_IMAGE_DIR'] = str(output / 'rendering')
    from src.importador.ia_revisao import prepare_evidence, analyze_evidence, normalize, file_hash
    from src.importador.ia_runtime import LocalVisionRuntime
    from src.importador.ia_ocr import LocalOcrReader
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    cases = manifest['cases']
    if len({case['id'] for case in cases}) != len(cases):
        raise ValueError('IDs de casos repetidos.')
    source_splits, group_splits = {}, {}
    sources = {}
    for case in cases:
        if case['split'] not in {'ajuste', 'avaliacao'}:
            raise ValueError('Split inválido.')
        path = (ROOT / case['path']).resolve()
        digest = file_hash(path)
        if digest != case['source_sha256']:
            raise ValueError('Fonte do benchmark mudou: ' + case['id'])
        sources[str(path)] = digest
        for groups, key in ((source_splits, digest), (group_splits, case['group'])):
            if key in groups and groups[key] != case['split']:
                raise ValueError('Vazamento entre ajuste e avaliação.')
            groups[key] = case['split']
    runtime = LocalVisionRuntime(log_dir=output / 'logs')
    reader = LocalOcrReader()
    result = {'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
              'force_model': args.force_model, 'no_model': args.no_model,
              'cases': [], 'code_sha256': {}, 'reference_origin': manifest.get('reference_origin'),
              'no_database_writes': True, 'no_human_labels_created': True}
    for relative in ('src/importador/ia_revisao.py', 'src/importador/ia_runtime.py', 'src/importador/ia_ocr.py'):
        result['code_sha256'][relative] = file_hash(ROOT / relative)
    def save():
        (output / 'resultado.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    class NoModel:
        fingerprint = 'sem-modelo'
        def transcribe(self, *a, **k):
            return {'encontrado': False, 'texto': ''}
        def close(self): pass
    try:
        with ExitStack() as stack:
            stack.enter_context(reader.batch())
            stack.enter_context(runtime.batch())
            for case in cases:
                print('Analisando', case['id'], flush=True)
                started = time.perf_counter()
                evidence = prepare_evidence(ROOT / case['path'], case['page'], case['bounds'],
                    letter=case.get('letter'), expected_sha256=case['source_sha256'], reader=reader)
                value = analyze_evidence(evidence, case['current'], runtime=NoModel() if args.no_model else runtime,
                    cache_dir=output / 'cache', force_model=args.force_model)
                if args.no_model:
                    value['model_called'] = False
                value.pop('region')
                if evidence['image_bytes']:
                    image_name = case['id'] + '.png'
                    if Path(image_name).name != image_name:
                        raise ValueError('ID de caso contém caminho inválido.')
                    (output / image_name).write_bytes(evidence['image_bytes'])
                value.update(id=case['id'], split=case['split'], group=case['group'],
                    expected=case['expected'], located=evidence['located'], evidence_reason=evidence['reason'],
                    total_seconds=round(time.perf_counter() - started, 3))
                expected = case['expected']
                if expected['status'] == 'abster':
                    value['meets_reference'] = value['status'] == 'abster' and not value['model_called']
                elif expected['status'] == 'manter':
                    value['meets_reference'] = value['status'] == 'manter' and value['proposal'] is None
                else:
                    value['meets_reference'] = value['status'] == 'proposta' and normalize(value['proposal']) == normalize(expected['text'])
                value['wrong_proposal'] = value['status'] == 'proposta' and (
                    expected['status'] != 'proposta' or normalize(value['proposal']) != normalize(expected.get('text', '')))
                if not args.no_model and (value['model_called'] or value['cache_hit']):
                    count = runtime.stats['requests']
                    t = time.perf_counter()
                    repeated = analyze_evidence(evidence, case['current'], runtime=runtime,
                        cache_dir=output / 'cache', force_model=True)
                    value['cache_probe'] = {'hit': repeated['cache_hit'],
                        'no_new_inference': runtime.stats['requests'] == count,
                        'seconds': round(time.perf_counter() - t, 3)}
                result['cases'].append(value)
                save()
                print(json.dumps({k: value[k] for k in ('id', 'status', 'meets_reference', 'wrong_proposal', 'model_called', 'total_seconds')}, ensure_ascii=True), flush=True)
    finally:
        reader.close(); runtime.close()
        result['runtime_stats'] = runtime.stats
        result['ocr_stats'] = reader.stats
        result['sources_unchanged'] = all(file_hash(path) == digest for path, digest in sources.items())
        result['processes_stopped'] = runtime._process is None and reader._process is None
        for split in ('ajuste', 'avaliacao'):
            rows = [c for c in result['cases'] if c['split'] == split]
            negative = [c for c in rows if c['expected']['status'] == 'abster']
            result[split] = {'cases': len(rows), 'matches_reference': sum(c['meets_reference'] for c in rows),
                'wrong_proposals': sum(c['wrong_proposal'] for c in rows),
                'required_abstentions': len(negative), 'safe_abstentions': sum(c['meets_reference'] for c in negative),
                'unresolved': sum(c['status'] in {'abster', 'divergencia'} and c['expected']['status'] != 'abster' for c in rows)}
        save()
    print(json.dumps({k: result[k] for k in ('ajuste', 'avaliacao', 'runtime_stats', 'processes_stopped')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
