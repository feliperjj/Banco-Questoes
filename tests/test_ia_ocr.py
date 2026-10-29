import threading
import time
from io import BytesIO

import pytest
from PIL import Image

from src.importador import ia_ocr


PNG = Image.new("RGB", (4, 4), "white")


class FakeStream:
    def write(self, value):
        return len(value)

    def flush(self):
        return None

    def close(self):
        return None


class FakeProcess:
    def __init__(self):
        self.stdin = FakeStream()
        self.stdout = FakeStream()
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


def fake_runtime(monkeypatch, response):
    reader = ia_ocr.LocalOcrReader()
    process = FakeProcess()

    def start():
        reader._process = process
        reader._responses.put(response)

    monkeypatch.setattr(reader, "_start", start)
    return reader, process


def test_reader_validates_and_returns_pixel_boxes(monkeypatch):
    reader, process = fake_runtime(monkeypatch, {
        "ok": True, "items": [{"text": "abc", "confidence": .9, "bbox": [1, 2, 3, 4]}]})
    assert reader(PNG) == [{"text": "abc", "confidence": .9, "bbox": [1., 2., 3., 4.]}]
    assert reader.stats == {"requests": 1}
    assert process.returncode == 0


def test_batch_is_lazy_and_reuses_worker(monkeypatch):
    reader, process = fake_runtime(monkeypatch, {"ok": True, "items": []})
    with reader.batch() as active:
        assert active._process is None
        active(PNG)
        # The fake response is replenished for the second request.
        active._responses.put({"ok": True, "items": []})
        active(PNG)
        assert active._process is process
    assert process.returncode == 0
    assert reader.stats["requests"] == 2


@pytest.mark.parametrize("response", [
    {"ok": False, "error": "worker OCR: ValueError"},
    {"ok": True, "items": [{"text": "x", "confidence": "bad", "bbox": [0, 0, 1, 1]}]},
    {"ok": True, "items": [{"text": "x", "confidence": .8, "bbox": [0, 0, 1]}]},
])
def test_malformed_worker_response_fails_safe(monkeypatch, response):
    reader, process = fake_runtime(monkeypatch, response)
    with pytest.raises((ValueError, RuntimeError)):
        reader(PNG)
    assert process.returncode == 0


def test_cancel_during_wait_closes_worker(monkeypatch):
    reader = ia_ocr.LocalOcrReader()
    process = FakeProcess()

    def start():
        reader._process = process

    monkeypatch.setattr(reader, "_start", start)
    event = threading.Event()
    errors = []

    def run():
        try:
            reader(PNG, event)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(.1)
    event.set()
    thread.join(2)
    assert not thread.is_alive()
    assert errors and isinstance(errors[0], TimeoutError)
    assert reader._process is None


def test_command_uses_worker_module_and_no_window(monkeypatch):
    calls = []
    monkeypatch.setattr(ia_ocr.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)) or FakeProcess())
    reader = ia_ocr.LocalOcrReader()
    reader._responses.put({"ok": True, "items": []})
    reader._start()
    assert calls[0][0][0][1:4] == ["-m", "src.importador.ia_ocr", "--server"]
    reader.close()

