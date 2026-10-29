"""OCR local isolado em processo próprio, sem dependência de Qt ou banco."""

from __future__ import annotations

import base64
import io
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_ROOT = Path(__file__).resolve().parents[2]
_PNG = b"\x89PNG\r\n\x1a\n"


def _worker() -> int:
    from PIL import Image
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
    for line in sys.stdin:
        try:
            payload = json.loads(line)
            image = Image.open(io.BytesIO(base64.b64decode(payload["image"])))
            result, _ = ocr(np.asarray(image.convert("RGB")))
            words = []
            for item in result or []:
                points, text, confidence = item
                flat = [(float(point[0]), float(point[1])) for point in points]
                words.append({"text": str(text), "confidence": float(confidence),
                              "bbox": [min(p[0] for p in flat), min(p[1] for p in flat),
                                        max(p[0] for p in flat), max(p[1] for p in flat)]})
            print(json.dumps({"ok": True, "items": words}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"OCR worker: {type(exc).__name__}"}), flush=True)
    return 0


class LocalOcrReader:
    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._responses: queue.Queue[Any] = queue.Queue()
        self._lock = threading.RLock()
        self._batch_depth = 0
        self._batch_owner: int | None = None
        self._stats = {"requests": 0}

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def _start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        self._process = subprocess.Popen(
            [sys.executable, "-m", "src.importador.ia_ocr", "--server"], cwd=str(_ROOT),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            bufsize=1, env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                self._responses.put(json.loads(line))
        except BaseException as exc:
            self._responses.put(exc)

    def _validate_image(self, image: Any) -> bytes:
        from PIL import Image
        if not isinstance(image, Image.Image):
            raise TypeError("image deve ser PIL.Image.Image")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    @staticmethod
    def _validate_response(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict) and value.get("ok") is False:
            raise RuntimeError("worker OCR falhou: " + str(value.get("error", "erro desconhecido"))[:160])
        if not isinstance(value, dict) or value.get("ok") is not True or set(value) != {"ok", "items"}:
            raise ValueError("resposta OCR malformada")
        items = value["items"]
        if not isinstance(items, list):
            raise ValueError("resposta OCR malformada")
        output = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"text", "confidence", "bbox"}:
                raise ValueError("resposta OCR malformada")
            text, confidence, bbox = item["text"], item["confidence"], item["bbox"]
            if not isinstance(text, str) or isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise ValueError("resposta OCR malformada")
            if not math.isfinite(float(confidence)) or not 0 <= float(confidence) <= 1 or not isinstance(bbox, list) or len(bbox) != 4:
                raise ValueError("resposta OCR malformada")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in bbox):
                raise ValueError("resposta OCR malformada")
            x0, y0, x1, y1 = (float(v) for v in bbox)
            if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
                raise ValueError("resposta OCR malformada")
            output.append({"text": text, "confidence": float(confidence), "bbox": [float(v) for v in bbox]})
        return output

    def __call__(self, image: Any, cancel_event: threading.Event | None = None) -> list[dict[str, Any]]:
        if cancel_event is not None and not hasattr(cancel_event, "is_set"):
            raise TypeError("cancel_event deve expor is_set()")
        if cancel_event is not None and cancel_event.is_set():
            raise TimeoutError("OCR cancelado")
        png = self._validate_image(image)
        owner = threading.get_ident()
        with self._lock:
            if self._batch_depth and self._batch_owner != owner:
                raise RuntimeError("OCR já está em uso por outro lote")
            own = self._batch_depth == 0
            try:
                self._start()
                if self._process is None or self._process.stdin is None:
                    raise RuntimeError("worker OCR indisponível")
                self._process.stdin.write(json.dumps({"image": base64.b64encode(png).decode("ascii")}) + "\n")
                self._process.stdin.flush()
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if cancel_event is not None and cancel_event.is_set():
                        raise TimeoutError("OCR cancelado")
                    try:
                        response = self._responses.get(timeout=0.1)
                    except queue.Empty:
                        if self._process.poll() is not None:
                            raise RuntimeError("worker OCR encerrou")
                        continue
                    if isinstance(response, BaseException):
                        raise RuntimeError("worker OCR retornou JSON inválido") from response
                    result = self._validate_response(response)
                    self._stats["requests"] += 1
                    return result
                raise TimeoutError("tempo excedido no OCR")
            except BaseException:
                self.close()
                raise
            finally:
                if own:
                    self.close()

    @contextmanager
    def batch(self) -> Iterator["LocalOcrReader"]:
        with self._lock:
            if self._batch_depth or self._process is not None:
                raise RuntimeError("OCR já está em uso")
            self._batch_depth = 1
            self._batch_owner = threading.get_ident()
        try:
            yield self
        finally:
            with self._lock:
                self.close()
                self._batch_depth = 0
                self._batch_owner = None

    def close(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            reader, self._reader = self._reader, None
            if process is None:
                return
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
            finally:
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass
                if reader is not None and reader is not threading.current_thread():
                    reader.join(timeout=0.5)
                while True:
                    try:
                        self._responses.get_nowait()
                    except queue.Empty:
                        break


if __name__ == "__main__":
    if "--server" not in sys.argv:
        raise SystemExit("use --server")
    raise SystemExit(_worker())
