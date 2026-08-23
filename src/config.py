"""Caminhos da aplicação independentes do diretório de execução."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "questoes.db"
LOG_PATH = DATA_DIR / "app.log"
