import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from src.db.database import init_db
from src.logging_config import configure_logging
from src.ui.main_window import MainWindow

if __name__ == "__main__":
    configure_logging()
    logger = logging.getLogger(__name__)
    init_db()
    app = QApplication(sys.argv)
    styles_path = Path(__file__).parent / "src" / "ui" / "styles.qss"
    try:
        app.setStyleSheet(styles_path.read_text(encoding="utf-8"))
        logger.info("Folha de estilos carregada: %s", styles_path)
    except OSError:
        logger.exception("Não foi possível carregar a folha de estilos: %s", styles_path)
    window = MainWindow()
    window.show()
    logger.info("Aplicação iniciada")
    sys.exit(app.exec())
