"""Confere binários extraídos contra o ZIP oficial fixo, antes de executá-los."""
from __future__ import annotations

import hashlib
from pathlib import Path
import threading
import zipfile

RUNTIME_ARCHIVE_SHA256 = '20cd898fafc269657df8de946b06ef37dcf6b783dfa43d28ac6d187bb6ebfe1e'
_CACHE = {}
_LOCK = threading.Lock()


def _identity(path):
    stat = path.stat()
    return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)


def _cancel(event):
    if event is not None and event.is_set():
        raise TimeoutError('Verificação do executor cancelada.')


def _digest(stream, cancel_event):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
        _cancel(cancel_event)
        digest.update(chunk)
    return digest.hexdigest()


def verify_extracted_runtime(runtime_dir, archive_path, *, expected_archive_hash=RUNTIME_ARCHIVE_SHA256,
                             cancel_event=None):
    runtime_dir, archive_path = Path(runtime_dir).resolve(), Path(archive_path).resolve()
    _cancel(cancel_event)
    if not archive_path.is_file() or not runtime_dir.is_dir():
        raise ValueError('Executor local incompleto. Execute scripts/instalar_ia_local.py para instalá-lo.')
    key = (str(runtime_dir), str(archive_path), expected_archive_hash)
    with _LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        identities, manifest = cached
        try:
            if all(_identity(Path(path)) == identity for path, identity in identities.items()):
                _cancel(cancel_event)
                return [dict(item) for item in manifest]
        except OSError:
            pass
    archive_identity = _identity(archive_path)
    with archive_path.open('rb') as stream:
        if _digest(stream, cancel_event) != expected_archive_hash:
            raise ValueError('O arquivo do executor está alterado. Reinstale a IA local.')
    identities = {str(archive_path): archive_identity}
    manifest = []
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            _cancel(cancel_event)
            if entry.is_dir():
                continue
            path = (runtime_dir / entry.filename).resolve()
            if not path.is_relative_to(runtime_dir) or not path.is_file():
                raise ValueError('Arquivo do executor ausente ou fora do destino: ' + entry.filename)
            before = _identity(path)
            with archive.open(entry) as stream:
                expected = _digest(stream, cancel_event)
            with path.open('rb') as stream:
                actual = _digest(stream, cancel_event)
            if actual != expected or before != _identity(path):
                raise ValueError('Arquivo do executor alterado: ' + entry.filename)
            identities[str(path)] = before
            manifest.append({'name': entry.filename, 'sha256': actual, 'bytes': before[0]})
    if not any(item['name'].replace('\\', '/') == 'llama-server.exe' for item in manifest):
        raise ValueError('O pacote não contém o servidor local esperado.')
    if _identity(archive_path) != archive_identity:
        raise ValueError('O pacote do executor mudou durante a verificação.')
    _cancel(cancel_event)
    with _LOCK:
        _CACHE[key] = (identities, manifest)
    return [dict(item) for item in manifest]
