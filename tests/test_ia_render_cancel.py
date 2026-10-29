from io import StringIO
import threading

from src.importador import pdf_render


def test_cancelar_renderizacao_encerra_somente_processo_da_operacao(monkeypatch):
    started = threading.Event()
    stopped = threading.Event()
    processes = []
    class Output:
        def readline(self):
            started.set()
            stopped.wait(3)
            return ''
    class Process:
        def __init__(self, *args, **kwargs):
            self.stdin, self.stdout = StringIO(), Output()
            self.returncode = None
            processes.append(self)
        def terminate(self):
            self.returncode = -1
            stopped.set()
        def wait(self, timeout=None):
            stopped.wait(timeout)
            return self.returncode
    monkeypatch.setattr(pdf_render.subprocess, 'Popen', Process)
    cancel = threading.Event()
    errors = []
    def work():
        try:
            pdf_render.render_region('original.pdf', 1, (0, 0, 100, 100), cancel_event=cancel)
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=work)
    worker.start()
    assert started.wait(2)
    cancel.set()
    worker.join(2)
    assert not worker.is_alive()
    assert len(processes) == 1 and processes[0].returncode == -1
    assert errors and isinstance(errors[0], InterruptedError)
