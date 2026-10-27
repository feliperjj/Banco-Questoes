"""Dá diretórios temporários exclusivos a subprocessos iniciados pelo pytest."""

import os
import tempfile
from pathlib import Path
from uuid import uuid4

if os.environ.get("BANCO_QUESTOES_TEST_MODE") == "1":
    root = Path(tempfile.gettempdir()) / f"banco-questoes-subprocess-{os.getpid()}-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    os.environ["BANCO_QUESTOES_TEST_ROOT"] = str(root)
    os.environ["BANCO_QUESTOES_DATA_DIR"] = str(root / "data")
    os.environ["BANCO_QUESTOES_DB_PATH"] = str(root / "data" / "questoes.db")
    os.environ["BANCO_QUESTOES_LOG_PATH"] = str(root / "logs" / "app.log")
    os.environ["BANCO_QUESTOES_REPORTS_DIR"] = str(root / "reports")
    os.environ["BANCO_QUESTOES_IMAGE_DIR"] = str(root / "data" / "questao_imagens")
