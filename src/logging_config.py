import logging
import os
from src.config import DATA_DIR, LOG_PATH


def configure_logging():
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        encoding="utf-8",
    )
    logging.getLogger(__name__).info("Logging inicializado")
