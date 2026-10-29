import hashlib
import zipfile

import pytest

from src.importador.ia_integrity import verify_extracted_runtime


def install(tmp_path):
    archive, runtime = tmp_path / 'runtime.zip', tmp_path / 'runtime'
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.writestr('llama-server.exe', b'official-executable')
        zipped.writestr('ggml-cpu.dll', b'official-library')
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(runtime)
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    return archive, runtime, expected


@pytest.mark.parametrize('name', ['llama-server.exe', 'ggml-cpu.dll'])
def test_runtime_alterado_apos_verificacao_e_rejeitado(tmp_path, name):
    archive, runtime, expected = install(tmp_path)
    files = verify_extracted_runtime(runtime, archive, expected_archive_hash=expected)
    assert len(files) == 2
    (runtime / name).write_bytes(b'adulterado')
    with pytest.raises(ValueError, match='alterado'):
        verify_extracted_runtime(runtime, archive, expected_archive_hash=expected)


def test_runtime_ausente_nao_passa_porque_zip_continua_correto(tmp_path):
    archive, runtime, expected = install(tmp_path)
    (runtime / 'llama-server.exe').unlink()
    with pytest.raises(ValueError, match='ausente'):
        verify_extracted_runtime(runtime, archive, expected_archive_hash=expected)
