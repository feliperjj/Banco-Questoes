import os
import sys


def test_banco_tem_caminho_estavel_fora_do_diretorio_atual(tmp_path):
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    antigo = os.getcwd()
    try:
        os.chdir(tmp_path)
        sys.path.insert(0, repo)
        from src.db.database import init_db
        banco = init_db(str(tmp_path / "fora-do-cwd.db"))
        assert banco.database == str(tmp_path / "fora-do-cwd.db")
    finally:
        os.chdir(antigo)
