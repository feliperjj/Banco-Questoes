"""Trabalho de banco fora da UI, com resultado antigo descartado e conexão própria."""
from PySide6.QtCore import QCoreApplication, QObject, QRunnable, QThreadPool, Signal, Slot
from src.db.database import db, initialized_database_batch

_pool = QThreadPool()
_pool.setMaxThreadCount(2)


class _Signals(QObject):
    done = Signal(object)


class _Job(QRunnable):
    def __init__(self, ident, function, database, signals):
        super().__init__()
        self.ident, self.function, self.database, self.signals = ident, function, database, signals

    def run(self):
        try:
            if db.database != self.database:
                raise RuntimeError('O banco mudou durante o carregamento. Atualize a tela.')
            with db.connection_context(), initialized_database_batch():
                value = self.function()
            result = (self.ident, value, None)
        except Exception as error:
            result = (self.ident, None, str(error))
        self.signals.done.emit(result)


class DatabaseTask(QObject):
    idle = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self._ident = 0
        self._pending = None
        self._signals = _Signals()
        self._signals.done.connect(self._done)
        app = QCoreApplication.instance()
        if app is not None and not app.property('databaseJobsJoined'):
            app.aboutToQuit.connect(_pool.waitForDone)
            app.setProperty('databaseJobsJoined', True)

    def submit(self, function, success, error):
        self._ident += 1
        self._pending = (self._ident, function, db.database, success, error)
        if not self.running:
            self._start()

    def invalidate(self):
        self._ident += 1
        self._pending = None

    def _start(self):
        ident, function, database, self._success, self._error = self._pending
        self._pending = None
        self.running = True
        _pool.start(_Job(ident, function, database, self._signals))

    @Slot(object)
    def _done(self, result):
        ident, value, error = result
        self.running = False
        if ident == self._ident:
            self._error(error) if error else self._success(value)
        if self.running:
            return
        if self._pending is not None:
            self._start()
        else:
            self.idle.emit()


def wait_for_database_jobs():
    """Fronteira de limpeza para testes; não bloqueia a navegação do produto."""
    _pool.waitForDone()
