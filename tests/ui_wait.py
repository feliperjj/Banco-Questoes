from time import monotonic, sleep
from PySide6.QtWidgets import QApplication
from src.ui.database_task import DatabaseTask


def wait_ui_jobs(timeout=15000):
    app = QApplication.instance()
    deadline = monotonic() + timeout / 1000
    while monotonic() < deadline:
        app.processEvents()
        widgets = app.allWidgets()
        busy = any(job.running for widget in app.topLevelWidgets() for job in widget.findChildren(DatabaseTask))
        busy |= any(getattr(widget, '_availability_timer', None) and widget._availability_timer.isActive() for widget in widgets)
        busy |= any(getattr(widget, 'crop_timer', None) and widget.crop_timer.isActive() for widget in widgets)
        if not busy:
            return
        sleep(0.01)
    raise AssertionError('O trabalho assíncrono da UI não terminou no prazo: ' + str([(type(w).__name__, [(j.running, j._ident, bool(j._pending)) for j in w.findChildren(DatabaseTask)]) for w in app.topLevelWidgets()]))
