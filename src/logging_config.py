import logging
import os


def configure_logging():
    os.makedirs("data", exist_ok=True)
    logging.basicConfig(
        filename=os.path.join("data", "app.log"),
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        encoding="utf-8",
    )
    logging.getLogger(__name__).info("Logging inicializado")
