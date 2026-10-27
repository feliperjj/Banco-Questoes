"""Caminhos da aplicação independentes do diretório de execução.

Os overrides de ambiente são carregados antes dos módulos de banco/UI. O modo
de teste exige caminhos explícitos e nunca pode escrever no acervo do projeto.
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
TEST_MODE = os.environ.get("BANCO_QUESTOES_TEST_MODE") == "1"
TEST_ROOT = Path(os.environ["BANCO_QUESTOES_TEST_ROOT"]).resolve() if TEST_MODE and os.environ.get("BANCO_QUESTOES_TEST_ROOT") else None
if TEST_MODE and TEST_ROOT is None:
    raise RuntimeError("Modo de teste exige BANCO_QUESTOES_TEST_ROOT definido antes das importações.")

DATA_DIR = Path(os.environ.get("BANCO_QUESTOES_DATA_DIR", TEST_ROOT / "data" if TEST_ROOT else ROOT_DIR / "data")).resolve()
DB_PATH = Path(os.environ.get("BANCO_QUESTOES_DB_PATH", DATA_DIR / "questoes.db")).resolve()
LOG_PATH = Path(os.environ.get("BANCO_QUESTOES_LOG_PATH", DATA_DIR / "app.log")).resolve()
REPORTS_DIR = Path(os.environ.get("BANCO_QUESTOES_REPORTS_DIR", TEST_ROOT / "reports" if TEST_ROOT else ROOT_DIR / "reports")).resolve()
IMAGE_DIR = Path(os.environ.get("BANCO_QUESTOES_IMAGE_DIR", TEST_ROOT / "data" / "questao_imagens" if TEST_ROOT else DATA_DIR / "questao_imagens")).resolve()

PRODUCTION_DB_PATH = (ROOT_DIR / "data" / "questoes.db").resolve()

if TEST_MODE:
    for name, path in (("banco", DB_PATH), ("dados", DATA_DIR), ("logs", LOG_PATH), ("relatórios", REPORTS_DIR), ("imagens", IMAGE_DIR)):
        if path == PRODUCTION_DB_PATH or path.is_relative_to(ROOT_DIR / "data"):
            raise RuntimeError(f"O caminho de {name} não pode apontar para o acervo real durante testes: {path}")
