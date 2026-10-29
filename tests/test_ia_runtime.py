import json
import threading
import time
from pathlib import Path

import pytest

from src.importador import ia_runtime


def _files(tmp_path: Path):
    model = tmp_path / "model.gguf"
    projector = tmp_path / "projector.gguf"
    executable = tmp_path / "llama-server.exe"
    for path in (model, projector, executable):
        path.write_bytes(path.name.encode())
    return model, projector, executable


class _Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.value).encode()


class _Process:
    def __init__(self, *args, **kwargs):
        self.args = args[0]
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        self.returncode = self.returncode or 0
        return self.returncode


def _runtime(tmp_path, monkeypatch, content='{"encontrado": true, "texto": "literal"}'):
    model, projector, executable = _files(tmp_path)
    runtime = ia_runtime.LocalVisionRuntime(ia_runtime.RuntimeConfig(model, projector, executable), tmp_path / "logs")
    monkeypatch.setattr(ia_runtime.subprocess, "Popen", _Process)

    def open_url(request, timeout=None):
        if request.full_url.endswith("/health"):
            return _Response({"status": "ok"})
        return _Response({"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})

    class Opener:
        def open(self, request, timeout=None):
            return open_url(request, timeout)

    monkeypatch.setattr(ia_runtime.urllib.request, "build_opener", lambda *args: Opener())
    return runtime


def test_transcribe_returns_exact_contract_and_stops_owned_process(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, monkeypatch)
    assert runtime.transcribe(b"\x89PNG\r\n\x1a\n") == {"encontrado": True, "texto": "literal"}
    assert runtime.stats["requests"] == 1
    assert runtime._process is None


def test_batch_reuses_process_and_close_is_idempotent(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, monkeypatch)
    with runtime.batch() as active:
        assert active._process is None
        active.transcribe(b"\x89PNG\r\n\x1a\none")
        active.transcribe(b"\x89PNG\r\n\x1a\ntwo")
        assert active._process is not None
    assert runtime._process is None
    runtime.close()
    assert runtime.stats["requests"] == 2


def test_start_waits_for_loading_then_requires_ok(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, monkeypatch)
    responses = iter([{"status": "loading"}, {"status": "ok"},
                      {"choices": [{"message": {"content": '{"encontrado":true,"texto":"ok"}'},
                                    "finish_reason": "stop"}]}])
    monkeypatch.setattr(runtime, "_request", lambda *args, **kwargs: next(responses))
    assert runtime.transcribe(b"\x89PNG\r\n\x1a\n") == {"encontrado": True, "texto": "ok"}
    assert runtime.stats["requests"] == 1


def test_cancel_during_request_ends_promptly(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, monkeypatch)
    request_started = threading.Event()
    cancel = threading.Event()

    def blocking_request(path, payload, timeout, cancel_event=None):
        if path.endswith("health"):
            return {"status": "ok"}
        request_started.set()
        while not cancel_event.is_set():
            time.sleep(0.01)
        raise TimeoutError("operação cancelada")

    monkeypatch.setattr(runtime, "_request", blocking_request)
    errors = []

    def run():
        try:
            runtime.transcribe(b"\x89PNG\r\n\x1a\n", cancel)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    assert request_started.wait(2)
    cancel.set()
    thread.join(2)
    assert not thread.is_alive()
    assert errors and isinstance(errors[0], TimeoutError)
    assert runtime._process is None


@pytest.mark.parametrize("content", [
    '{"encontrado": false, "texto": "não pode"}',
    '{"encontrado": true, "texto": "ok", "extra": 1}',
    '{"encontrado": "true", "texto": "ok"}',
    "not json",
])
def test_malformed_model_output_fails_safe(tmp_path, monkeypatch, content):
    runtime = _runtime(tmp_path, monkeypatch, content)
    with pytest.raises(ValueError):
        runtime.transcribe(b"\x89PNG\r\n\x1a\n")
    assert runtime._process is None


def test_cancel_closes_without_request(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, monkeypatch)
    event = threading.Event()
    event.set()
    with pytest.raises(TimeoutError):
        runtime.transcribe(b"\x89PNG\r\n\x1a\n", event)
    assert runtime._process is None


def test_fingerprint_changes_when_model_changes(tmp_path, monkeypatch):
    model, _, _ = _files(tmp_path)
    runtime = ia_runtime.LocalVisionRuntime(ia_runtime.RuntimeConfig(model, tmp_path / "projector.gguf", tmp_path / "llama-server.exe"))
    first = runtime.fingerprint
    model.write_bytes(b"changed")
    assert runtime.fingerprint != first


def test_fingerprint_reuses_process_memory_cache_until_identity_changes(tmp_path, monkeypatch):
    model, projector, executable = _files(tmp_path)
    runtime = ia_runtime.LocalVisionRuntime(ia_runtime.RuntimeConfig(model, projector, executable))
    original = runtime._digest_stable
    calls = []

    def counted(path, cancel_event=None):
        calls.append(path)
        return original(path, cancel_event)

    monkeypatch.setattr(runtime, "_digest_stable", counted)
    runtime.fingerprint
    first_count = len(calls)
    runtime.fingerprint
    assert len(calls) == first_count
    model.write_bytes(b"changed")
    runtime.fingerprint
    assert len(calls) == first_count + 1


def test_fingerprint_for_honors_cancel_before_hash(tmp_path):
    model, projector, executable = _files(tmp_path)
    runtime = ia_runtime.LocalVisionRuntime(ia_runtime.RuntimeConfig(model, projector, executable))
    event = threading.Event()
    event.set()
    with pytest.raises(TimeoutError):
        runtime.fingerprint_for(event)

