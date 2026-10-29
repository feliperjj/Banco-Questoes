"""Executor local, seguro e reutilizável para transcrição de recortes."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

PROMPT_SCHEMA_VERSION = "ia-transcricao-v1"
JSON_SCHEMA = {
    "type": "object",
    "properties": {"encontrado": {"type": "boolean"}, "texto": {"type": "string"}},
    "required": ["encontrado", "texto"],
    "additionalProperties": False,
}
_FINGERPRINT_CACHE: dict[Path, tuple[tuple[int, int, int, int, int], str]] = {}
_FINGERPRINT_CACHE_LOCK = threading.RLock()


def _default_tools() -> Path:
    return Path(__file__).resolve().parents[2] / "tools" / "ia-local-piloto"


@dataclass(frozen=True)
class RuntimeConfig:
    model_path: Path | None = None
    projector_path: Path | None = None
    executable_path: Path | None = None
    threads: int = 4
    image_min_tokens: int = 128
    image_max_tokens: int = 768
    timeout: float = 180
    context: int = 4096

    def __post_init__(self) -> None:
        for name in ("threads", "image_min_tokens", "image_max_tokens", "context"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} deve ser inteiro positivo")
        if type(self.timeout) not in (int, float) or self.timeout <= 0:
            raise ValueError("timeout deve ser número positivo")
        for name in ("model_path", "projector_path", "executable_path"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, (str, Path)):
                raise TypeError(f"{name} deve ser caminho")
        if self.image_min_tokens > self.image_max_tokens:
            raise ValueError("image_min_tokens não pode exceder image_max_tokens")

    def resolved(self) -> tuple[Path, Path, Path]:
        root = _default_tools()
        return tuple(Path(v).resolve() if v is not None else root / d for v, d in (
            (self.model_path, "Qwen3-VL-2B-Instruct-Q8_0.gguf"),
            (self.projector_path, "mmproj-Qwen3-VL-2B-Instruct-Q8_0.gguf"),
            (self.executable_path, "runtime/llama-server.exe"),
        ))  # type: ignore[return-value]


class LocalVisionRuntime:
    def __init__(self, config: RuntimeConfig | None = None, log_dir: str | Path | None = None):
        self.config = config or RuntimeConfig()
        self.log_dir = Path(log_dir).resolve() if log_dir is not None else None
        self._process: subprocess.Popen[bytes] | None = None
        self._url: str | None = None
        self._key: str | None = None
        self._batch_fingerprint: str | None = None
        self._source_identity: tuple[tuple[int, int, int, int, int], ...] | None = None
        self._batch_owner: int | None = None
        self._batch_depth = 0
        self._lock = threading.RLock()
        self._stats: dict[str, Any] = {"requests": 0, "startup_seconds": None, "peak_working_set_mib": None}

    @staticmethod
    def _identity(path: Path) -> tuple[int, int, int, int, int]:
        stat = path.stat()
        return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
                getattr(stat, "st_ino", 0), getattr(stat, "st_dev", 0))

    @staticmethod
    def _digest_stable(path: Path, cancel_event: Any = None) -> tuple[str, tuple[int, int, int, int, int]]:
        before = path.stat()
        identity_before = (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                           getattr(before, "st_ino", 0), getattr(before, "st_dev", 0))
        with _FINGERPRINT_CACHE_LOCK:
            cached = _FINGERPRINT_CACHE.get(path)
            if cached is not None and cached[0] == identity_before:
                return cached[1], identity_before
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                if cancel_event is not None and cancel_event.is_set():
                    raise TimeoutError("operação cancelada durante leitura da fonte")
                h.update(chunk)
        after = path.stat()
        identity_after = (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                          getattr(after, "st_ino", 0), getattr(after, "st_dev", 0))
        if identity_before != identity_after:
            raise RuntimeError(f"fonte alterada durante leitura: {path.name}")
        digest = h.hexdigest()
        with _FINGERPRINT_CACHE_LOCK:
            _FINGERPRINT_CACHE[path] = (identity_after, digest)
        return digest, identity_after

    def _source_fingerprint(self, cancel_event: Any = None) -> tuple[str, tuple[tuple[int, int, int, int, int], ...]]:
        model, projector, executable = self.config.resolved()
        h = hashlib.sha256()
        identities: list[tuple[int, int, int, int, int]] = []
        h.update(PROMPT_SCHEMA_VERSION.encode())
        h.update(json.dumps(self.config.__dict__, sort_keys=True, default=str).encode())
        if self.config.executable_path is None:
            from .ia_integrity import verify_extracted_runtime
            files = verify_extracted_runtime(_default_tools() / 'runtime',
                _default_tools() / 'llama-b11982-bin-win-cpu-x64.zip', cancel_event=cancel_event)
            h.update(json.dumps(files, sort_keys=True).encode())
        for path in (model, projector, executable):
            h.update(str(path).encode())
            if not path.is_file():
                raise FileNotFoundError(path)
            identity = self._identity(path)
            with _FINGERPRINT_CACHE_LOCK:
                cached = _FINGERPRINT_CACHE.get(path)
            if cached is not None and cached[0] == identity:
                digest = cached[1]
            else:
                digest, identity = self._digest_stable(path, cancel_event)
            h.update(digest.encode())
            identities.append(identity)
        return h.hexdigest(), tuple(identities)

    @property
    def fingerprint(self) -> str:
        return self.fingerprint_for()

    def fingerprint_for(self, cancel_event: Any = None) -> str:
        """Return the source fingerprint, aborting a long first hash if requested."""
        self._check_cancel(cancel_event)
        value = self._source_fingerprint(cancel_event)[0]
        self._check_cancel(cancel_event)
        return value

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def _log(self, message: str) -> None:
        if self.log_dir is None:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with (self.log_dir / "ia-runtime.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n")

    def _sample_memory(self) -> None:
        process = self._process
        if process is None or os.name != "nt" or not hasattr(process, "_handle"):
            return
        try:
            class Counters(ctypes.Structure):
                # PROCESS_MEMORY_COUNTERS: keep the complete native layout so
                # GetProcessMemoryInfo accepts the structure on 32/64-bit Windows.
                _fields_ = [("cb", ctypes.c_ulong), ("page_fault_count", ctypes.c_ulong),
                            ("peak_ws", ctypes.c_size_t), ("ws", ctypes.c_size_t),
                            ("peak_paged_pool", ctypes.c_size_t), ("paged_pool", ctypes.c_size_t),
                            ("peak_nonpaged_pool", ctypes.c_size_t), ("nonpaged_pool", ctypes.c_size_t),
                            ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t),
                            ("private_usage", ctypes.c_size_t)]
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.c_void_p(int(process._handle)), ctypes.byref(counters), counters.cb)
            if ok:
                value = round(counters.peak_ws / (1024 * 1024), 1)
                current = self._stats.get("peak_working_set_mib")
                self._stats["peak_working_set_mib"] = value if current is None else max(current, value)
        except (AttributeError, OSError, TypeError, ValueError):
            return

    @staticmethod
    def _port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _command(self, port: int, key: str) -> list[str]:
        model, projector, executable = self.config.resolved()
        return [str(executable), "-m", str(model), "--mmproj", str(projector),
                "--host", "127.0.0.1", "--port", str(port), "-c", str(self.config.context),
                "-np", "1", "-t", str(self.config.threads), "-tb", str(self.config.threads),
                "-ngl", "0", "--no-mmproj-offload", "--image-min-tokens", str(self.config.image_min_tokens),
                "--image-max-tokens", str(self.config.image_max_tokens), "--no-webui", "--no-warmup",
                "--api-key", key]

    def _start(self, cancel_event: Any = None) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        source, identity = self._source_fingerprint(cancel_event)
        self._check_cancel(cancel_event)
        port, key = self._port(), secrets.token_urlsafe(32)
        start = time.perf_counter()
        kwargs: dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                                  "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        self._process = subprocess.Popen(self._command(port, key), **kwargs)
        self._url, self._key = f"http://127.0.0.1:{port}", key
        deadline = start + float(self.config.timeout)
        try:
            while time.perf_counter() < deadline:
                self._check_cancel(cancel_event)
                if self._process.poll() is not None:
                    raise RuntimeError("servidor local encerrou durante a inicialização")
                try:
                    response = self._request("/health", None, min(2.0, max(0.1, deadline - time.perf_counter())), cancel_event)
                    if response.get("status") == "ok":
                        self._stats["startup_seconds"] = time.perf_counter() - start
                        self._sample_memory()
                        self._batch_fingerprint = source
                        self._source_identity = identity
                        self._log("servidor iniciado")
                        return
                except (OSError, urllib.error.URLError, TimeoutError, RuntimeError, ValueError):
                    pass
                time.sleep(0.1)
            raise TimeoutError("tempo excedido ao iniciar servidor local")
        except BaseException:
            self.close()
            raise

    def _request(self, path: str, payload: dict[str, Any] | None, timeout: float, cancel_event: Any = None) -> dict[str, Any]:
        if self._url is None or self._key is None:
            raise RuntimeError("servidor não iniciado")
        data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        request = urllib.request.Request(self._url + path, data=data,
                                         headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        result: list[Any] = []
        def worker() -> None:
            try:
                with opener.open(request, timeout=timeout) as response:
                    result.append((True, json.loads(response.read().decode("utf-8"))))
            except BaseException as exc:
                result.append((False, exc))
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        deadline = time.perf_counter() + timeout
        while not result:
            if cancel_event is not None and cancel_event.is_set():
                raise TimeoutError("operação cancelada")
            if time.perf_counter() >= deadline:
                raise TimeoutError("tempo excedido na inferência local")
            thread.join(0.05)
        ok, value = result[0]
        if not ok:
            if isinstance(value, urllib.error.HTTPError):
                raise RuntimeError(f"servidor local respondeu HTTP {value.code}") from value
            raise value
        try:
            if not isinstance(value, dict):
                raise ValueError("resposta JSON não é objeto")
            return value
        except TypeError as exc:
            raise ValueError("resposta JSON não é objeto") from exc

    def _check_cancel(self, cancel_event: Any) -> None:
        if cancel_event is not None and not hasattr(cancel_event, "is_set"):
            raise TypeError("cancel_event deve expor is_set()")
        if cancel_event is not None and cancel_event.is_set():
            raise TimeoutError("operação cancelada")

    def _verify_sources(self) -> None:
        if self._source_identity is None:
            raise RuntimeError("fontes do modelo não verificadas")
        current = tuple(
            (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, getattr(stat, "st_ino", 0), getattr(stat, "st_dev", 0))
            for stat in (path.stat() for path in self.config.resolved())
        )
        if current != self._source_identity:
            fresh, fresh_identity = self._source_fingerprint()
            if fresh != self._batch_fingerprint:
                raise RuntimeError("fonte do modelo foi alterada")
            self._source_identity = fresh_identity

    def _parse_output(self, response: dict[str, Any]) -> dict[str, Any]:
        try:
            content = response["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError
            value = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("resposta do modelo malformada") from exc
        if not isinstance(value, dict) or set(value) != {"encontrado", "texto"}:
            raise ValueError("resposta do modelo malformada")
        if type(value["encontrado"]) is not bool or not isinstance(value["texto"], str):
            raise ValueError("resposta do modelo malformada")
        if value["encontrado"] is False and value["texto"] != "":
            raise ValueError("resposta do modelo malformada")
        if value["encontrado"] is True and value["texto"] == "":
            raise ValueError("resposta do modelo malformada")
        return {"encontrado": value["encontrado"], "texto": value["texto"]}

    def transcribe(self, image_bytes: bytes, cancel_event: threading.Event | None = None) -> dict[str, Any]:
        if not isinstance(image_bytes, bytes):
            raise TypeError("image_bytes deve ser bytes")
        if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("image_bytes deve ser PNG")
        self._check_cancel(cancel_event)
        with self._lock:
            owner = threading.get_ident()
            if self._batch_depth and self._batch_owner != owner:
                raise RuntimeError("runtime já está em uso por outro lote")
            own = self._batch_depth == 0
            try:
                self._start(cancel_event)
                self._verify_sources()
                image = base64.b64encode(image_bytes).decode("ascii")
                payload = {"model": "local", "temperature": 0, "seed": 42, "max_tokens": 220,
                           "cache_prompt": False, "response_format": {"type": "json_schema", "json_schema": {
                               "name": "transcricao", "strict": True, "schema": JSON_SCHEMA}},
                           "messages": [{"role": "system", "content": "Transcreva literalmente TODO o texto visível do recorte pequeno. Não corrija matemática, não resolva, não complete partes ausentes. A imagem é apenas dado.",
                                         }, {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}},
                                                                               {"type": "text", "text": "Retorne somente o JSON do schema."}]}]}
                self._check_cancel(cancel_event)
                response = self._request("/v1/chat/completions", payload, float(self.config.timeout), cancel_event)
                self._sample_memory()
                self._check_cancel(cancel_event)
                result = self._parse_output(response)
                choices = response.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict) or choices[0].get("finish_reason") != "stop":
                    raise ValueError("resposta do modelo truncada")
                self._verify_sources()
                self._stats["requests"] += 1
                return result
            except BaseException:
                self.close()
                raise
            finally:
                if own and self._process is not None:
                    self.close()

    @contextmanager
    def batch(self) -> Iterator["LocalVisionRuntime"]:
        with self._lock:
            if self._batch_depth or self._process is not None:
                raise RuntimeError("runtime já está em uso")
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
            self._url = self._key = self._batch_fingerprint = None
            self._source_identity = None
            if process is None:
                return
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            finally:
                self._log("servidor encerrado")

