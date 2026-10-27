"""Uma aplicação Qt por processo e dados isolados antes dos imports do projeto."""
import os
from pathlib import Path
from uuid import uuid4

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['BANCO_QUESTOES_TEST_MODE'] = '1'
_TEST_ROOT = Path(__file__).resolve().parents[1] / f".t{os.getpid()}-{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True, exist_ok=False)
for _name, _path in {
    'BANCO_QUESTOES_TEST_ROOT': _TEST_ROOT,
    'BANCO_QUESTOES_DATA_DIR': _TEST_ROOT / 'data',
    'BANCO_QUESTOES_DB_PATH': _TEST_ROOT / 'data' / 'questoes.db',
    'BANCO_QUESTOES_LOG_PATH': _TEST_ROOT / 'logs' / 'app.log',
    'BANCO_QUESTOES_REPORTS_DIR': _TEST_ROOT / 'reports',
    'BANCO_QUESTOES_IMAGE_DIR': _TEST_ROOT / 'data' / 'questao_imagens',
}.items():
    os.environ[_name] = str(_path)

# Subprocessos Python herdam este bootstrap e recebem caminhos próprios. Não
# compartilham o SQLite do pytest pai nem os artefatos de outros subprocessos.
_tests_path = str(Path(__file__).resolve().parent)
_python_path = os.environ.get('PYTHONPATH', '')
if _tests_path not in _python_path.split(os.pathsep):
    os.environ['PYTHONPATH'] = os.pathsep.join(filter(None, (_tests_path, _python_path)))

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from src.db.database import db


@pytest.fixture(scope='session', autouse=True)
def qt_application():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def tmp_path(request):
    """Substitui o tmp_path do plugin por uma pasta isolada e sob controle do projeto."""
    name = f"c-{uuid4().hex[:8]}"
    path = _TEST_ROOT / 'cases' / name
    path.mkdir(parents=True, exist_ok=False)
    return path


@pytest.fixture(autouse=True)
def limpar_widgets(qt_application):
    yield
    for widget in qt_application.topLevelWidgets():
        widget.hide()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture(scope='session', autouse=True)
def fechar_banco_de_teste():
    yield
    if not db.is_closed():
        db.close()
