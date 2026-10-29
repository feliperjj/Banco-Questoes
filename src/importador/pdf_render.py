"""PDFium em processo isolado: uma falha nativa não derruba a interface Qt."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from contextvars import ContextVar
from functools import lru_cache, wraps

_batch = ContextVar("pdf_render_batch", default=None)


def rendering_batch(function):
    """Um processo isolado reutilizado durante o lote; nenhum cache persistente."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _batch.get() is not None:
            return function(*args, **kwargs)
        holder = [None]
        token = _batch.set(holder)
        try:
            return function(*args, **kwargs)
        finally:
            _batch.reset(token)
            if holder[0] is not None:
                process = holder[0]
                try:
                    process.stdin.close()
                except (OSError, EOFError, BrokenPipeError):
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)
    return wrapped


def render_region(path, page, bbox, *, scale=2.0, output=None):
    payload = {"path": str(Path(path).resolve()), "page": int(page), "bbox": list(bbox), "scale": float(scale),
               "output": str(Path(output).resolve()) if output else None}
    holder = _batch.get()
    if holder is not None:
        if holder[0] is None:
            holder[0] = subprocess.Popen([sys.executable, "-m", "src.importador.pdf_render", "--server"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", cwd=Path(__file__).resolve().parents[2],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        process = holder[0]
        try:
            import queue
            import threading
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
            response = queue.Queue()
            threading.Thread(target=lambda: response.put(process.stdout.readline()), daemon=True).start()
            try:
                line = response.get(timeout=60)
            except queue.Empty as error:
                process.terminate()
                raise ValueError("Tempo excedido na renderização isolada.") from error
            if not line:
                raise ValueError("O processo de renderização encerrou sem resposta.")
            reply = json.loads(line)
        except (OSError, EOFError, BrokenPipeError) as error:
            raise ValueError("O processo de renderização foi interrompido.") from error
        if "error" in reply:
            raise ValueError(reply["error"])
        return reply["ok"]
    process = subprocess.run([sys.executable, "-m", "src.importador.pdf_render"], input=json.dumps(payload),
        capture_output=True, text=True, timeout=60, cwd=Path(__file__).resolve().parents[2],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if process.returncode:
        raise ValueError("Falha no processo isolado de renderização: " + process.stderr[-600:])
    try:
        return json.loads(process.stdout)
    except (ValueError, TypeError) as error:
        raise ValueError("Resposta inválida do processo de renderização.") from error


def render_image(path, page, bbox, *, scale=2.0):
    """Carrega o recorte isolado sem inicializar PDFium no processo da UI."""
    from PIL import Image
    from uuid import uuid4
    from src.config import IMAGE_DIR
    staging = IMAGE_DIR / ".rendering"
    staging.mkdir(parents=True, exist_ok=True)
    target = staging / f"{uuid4().hex}.png"
    try:
        render_region(path, page, bbox, scale=scale, output=target)
        with Image.open(target) as image:
            return image.convert("RGB").copy()
    finally:
        target.unlink(missing_ok=True)


def render_page_image(page, *, resolution=150):
    return render_image(page.pdf.stream.name, page.page_number, page.bbox, scale=resolution / 72)


@lru_cache(maxsize=4)
def _page_image(path, page_number, scale, file_size, modified_ns):
    import pypdfium2 as pdfium
    doc = page = bitmap = None
    try:
        doc = pdfium.PdfDocument(path)
        page = doc[page_number - 1]
        width, height = page.get_size()
        bitmap = page.render(scale=scale)
        return bitmap.to_pil().copy().convert("RGB"), width, height
    finally:
        for obj in (bitmap, page, doc):
            if obj is not None:
                obj.close()


def _work(payload):
    from PIL import Image
    scale = float(payload["scale"])
    bounds = [float(value) for value in payload["bbox"]]
    if not 1 <= scale <= 3 or not all(math.isfinite(value) for value in bounds):
        raise ValueError("Escala ou região inválida.")
    path = Path(payload["path"])
    stat = path.stat()
    full, width, height = _page_image(str(path), int(payload["page"]), scale, stat.st_size, stat.st_mtime_ns)
    x0, y0, x1, y1 = bounds
    if not 0 <= x0 < x1 <= width + .01 or not 0 <= y0 < y1 <= height + .01:
        raise ValueError("Região fora da página.")
    image = full.crop(tuple(int(value * scale) for value in bounds))
    try:
        result = {"size": list(image.size), "pixels_sha256": hashlib.sha256(image.tobytes()).hexdigest()}
        if payload.get("output"):
            output = Path(payload["output"])
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                with Image.open(output) as existing:
                    if existing.size != image.size or hashlib.sha256(existing.convert("RGB").tobytes()).hexdigest() != result["pixels_sha256"]:
                        raise ValueError("Imagem existente diverge do original; não foi sobrescrita.")
            else:
                if output.suffix.lower() == '.webp':
                    image.save(output, format='WEBP', lossless=True, method=4)
                else:
                    image.save(output, format="PNG")
            result["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
            result["path"] = str(output)
        return result
    finally:
        image.close()


if __name__ == "__main__":
    if "--server" in sys.argv:
        for line in sys.stdin:
            try:
                reply = {"ok": _work(json.loads(line))}
            except Exception as error:
                reply = {"error": str(error)}
            print(json.dumps(reply), flush=True)
    else:
        print(json.dumps(_work(json.loads(sys.stdin.read()))))
