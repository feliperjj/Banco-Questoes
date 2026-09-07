"""Uma tarefa por executor, com vida útil dos objetos Qt explícita."""
from PySide6.QtCore import QObject, QThread, Signal, Slot


class Worker(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    @Slot()
    def run(self):
        try:
            self.result.emit(self.function())
        except Exception as exc:
            self.error.emit(str(exc))


class BackgroundTask(QObject):
    result = Signal(object)
    error = Signal(str)
    idle = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None

    @property
    def running(self):
        return self.thread is not None

    def start(self, function):
        if self.running:
            return False
        # Uma função isolada não precisa de um event loop próprio nem de um
        # QObject transferido entre threads para executar a leitura.
        self.thread = Worker(function, self)
        self.thread.result.connect(self.result)
        self.thread.error.connect(self.error)
        self.thread.finished.connect(self._finished)
        self.thread.start()
        return True

    @Slot()
    def _finished(self):
        # finished pode chegar antes da limpeza nativa terminar no Windows.
        # Aguarde essa limpeza antes de liberar os wrappers Python.
        self.thread.wait()
        self.thread.deleteLater()
        self.thread = None
        self.idle.emit()
