"""Uma aplicação Qt por processo; widgets não vazam entre bancos de teste."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session', autouse=True)
def qt_application():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def limpar_widgets(qt_application):
    yield
    for widget in qt_application.topLevelWidgets():
        widget.hide()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
