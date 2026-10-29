"""Obtém/valida arquivos públicos fixos. A aplicação nunca baixa modelos sozinha."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
COMMIT = 'ea6a11058182570be6436b9a2e4ee7f7b49f908d'
ASSETS = [
    ('llama-b11982-bin-win-cpu-x64.zip',
     'https://github.com/ggml-org/llama.cpp/releases/download/b11982/llama-b11982-bin-win-cpu-x64.zip',
     '20cd898fafc269657df8de946b06ef37dcf6b783dfa43d28ac6d187bb6ebfe1e'),
    ('Qwen3-VL-2B-Instruct-Q8_0.gguf',
     f'https://huggingface.co/ggml-org/Qwen3-VL-2B-Instruct-GGUF/resolve/{COMMIT}/Qwen3-VL-2B-Instruct-Q8_0.gguf',
     'b7802e29f71a9e5b5e3f83f613df898a2204342dcea71a231ea501d481813c39'),
    ('mmproj-Qwen3-VL-2B-Instruct-Q8_0.gguf',
     f'https://huggingface.co/ggml-org/Qwen3-VL-2B-Instruct-GGUF/resolve/{COMMIT}/mmproj-Qwen3-VL-2B-Instruct-Q8_0.gguf',
     '69066c8f279ec85ff48ab4059f6ebba0d2932ca57667f2bbdac7d9805bca9e7b'),
]


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path, default=ROOT / 'tools/ia-local-piloto')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    dest = args.dest.resolve()
    if not args.verify_only:
        dest.mkdir(parents=True, exist_ok=True)
    def obtain(asset):
        name, url, expected = asset
        path = dest / name
        if not path.is_file() or sha(path) != expected:
            if args.verify_only:
                raise ValueError('Arquivo ausente ou hash divergente: ' + name)
            temporary = path.with_suffix(path.suffix + '.part')
            print('Baixando', name, flush=True)
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as stream:
                for chunk in iter(lambda: response.read(8 * 1024 * 1024), b''):
                    stream.write(chunk)
            if sha(temporary) != expected:
                raise ValueError('SHA-256 divergente; arquivo não instalado: ' + name)
            temporary.replace(path)
        return {'name': name, 'url': url, 'sha256': expected, 'bytes': path.stat().st_size}
    with ThreadPoolExecutor(max_workers=3) as pool:
        manifest = list(pool.map(obtain, ASSETS))
    if not args.verify_only:
        runtime = dest / 'runtime'
        with zipfile.ZipFile(dest / ASSETS[0][0]) as archive:
            for entry in archive.infolist():
                if not (runtime / entry.filename).resolve().is_relative_to(runtime.resolve()):
                    raise ValueError('Arquivo ZIP contém caminho fora do destino.')
            archive.extractall(runtime)
    from src.importador.ia_integrity import verify_extracted_runtime
    runtime_files = verify_extracted_runtime(dest / 'runtime', dest / ASSETS[0][0])
    if not args.verify_only:
        (dest / 'manifest.json').write_text(json.dumps({'assets': manifest, 'runtime': runtime_files}, indent=2), encoding='utf-8')
    print('Arquivos verificados. Modelo local sem cobrança por consulta.')


if __name__ == '__main__':
    main()
