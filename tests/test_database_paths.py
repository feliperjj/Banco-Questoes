from src.db.database import init_db
from src.db.migrations import CURRENT_SCHEMA_VERSION
import sqlite3
import os
import subprocess
import sys
from pathlib import Path


def test_init_db_cria_versionamento_sem_apagar_banco(tmp_path):
    caminho = tmp_path / "subdir" / "teste.db"
    banco = init_db(str(caminho))
    versao = banco.execute_sql("SELECT version FROM schema_version").fetchone()[0]
    assert versao == CURRENT_SCHEMA_VERSION
    tabelas = {
        linha[0]
        for linha in banco.execute_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {"provas_cadastradas", "prova_cadastrada_questoes"}.issubset(tabelas)
    assert not list(tmp_path.glob("teste.backup-*.db"))


def test_modo_teste_recusa_banco_original_sem_altera_lo():
    from src.config import PRODUCTION_DB_PATH, TEST_MODE
    from src.db.database import init_db
    import hashlib

    assert TEST_MODE is True
    digest_antes = hashlib.sha256(PRODUCTION_DB_PATH.read_bytes()).hexdigest()
    try:
        init_db(str(PRODUCTION_DB_PATH))
    except RuntimeError as error:
        assert "banco real" in str(error)
    else:
        raise AssertionError("A conexão de teste ao banco original deveria ser recusada.")
    assert hashlib.sha256(PRODUCTION_DB_PATH.read_bytes()).hexdigest() == digest_antes


def test_subprocesso_python_recebe_diretorio_de_teste_proprio():
    from src.config import DB_PATH

    resultado = subprocess.run(
        [sys.executable, "-c", "from src.config import DB_PATH; print(DB_PATH)"],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        env=os.environ.copy(),
    )
    child_db = Path(resultado.stdout.strip()).resolve()
    assert child_db != DB_PATH.resolve()
    assert "Banco-Questões" not in str(child_db)


def test_init_db_migra_questoes_legadas_e_cria_backup(tmp_path):
    caminho = tmp_path / "legado.db"
    conexao = sqlite3.connect(caminho)
    conexao.execute("CREATE TABLE questoes (id INTEGER PRIMARY KEY, enunciado TEXT NOT NULL, tipo TEXT NOT NULL)")
    conexao.execute("INSERT INTO questoes (enunciado, tipo) VALUES ('legada', 'certo_errado')")
    conexao.commit()
    conexao.close()

    banco = init_db(str(caminho))

    colunas = {linha[1] for linha in banco.execute_sql('PRAGMA table_info("questoes")').fetchall()}
    assert {"gabarito", "cargo", "ativa", "criada_em"}.issubset(colunas)
    assert banco.execute_sql("SELECT version FROM schema_version").fetchone()[0] == CURRENT_SCHEMA_VERSION
    assert banco.execute_sql("SELECT enunciado FROM questoes").fetchone()[0] == "legada"
    backups = list(tmp_path.glob("legado.pre-migration-*.db"))
    assert len(backups) == 1


def test_migracao_registra_fontes_legadas_e_cria_indices_apos_colunas(tmp_path):
    caminho = tmp_path / "legado-com-fonte.db"
    fonte = tmp_path / "caderno.pdf"
    fonte.write_bytes(b"%PDF-1.4 fixture")
    with sqlite3.connect(caminho) as conexao:
        conexao.execute("CREATE TABLE questoes (id INTEGER PRIMARY KEY, enunciado TEXT NOT NULL, tipo TEXT NOT NULL)")
        conexao.execute("INSERT INTO questoes (enunciado, tipo) VALUES ('Questão antiga', 'certo_errado')")
        conexao.execute(
            "CREATE TABLE provas_cadastradas (id INTEGER PRIMARY KEY, nome TEXT NOT NULL, "
            "arquivo_questoes TEXT, arquivo_gabarito TEXT, ativa INTEGER NOT NULL, "
            "criada_em DATETIME NOT NULL, instrucoes_prova TEXT)"
        )
        conexao.execute(
            "INSERT INTO provas_cadastradas (nome, arquivo_questoes, ativa, criada_em) VALUES (?, ?, 1, ?)",
            ("Legada", str(fonte), "2026-10-26 12:00:00"),
        )

    banco = init_db(str(caminho))
    prova = banco.execute_sql(
        "SELECT documento_fonte_questoes_id FROM provas_cadastradas WHERE id = 1"
    ).fetchone()
    assert prova[0] is not None
    assert banco.execute_sql("SELECT COUNT(*) FROM documentos_fonte WHERE disponibilidade = 'presente'").fetchone()[0] == 1
    assert banco.execute_sql("SELECT COUNT(*) FROM questoes_versoes").fetchone()[0] == 1
    assert banco.execute_sql("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert banco.execute_sql("PRAGMA foreign_key_check").fetchall() == []
    for table, index in (
        ("prova_questoes", "provaquestao_questao_versao_id"),
        ("prova_cadastrada_questoes", "provacadastradaquestao_questao_versao_id"),
        ("provas_cadastradas", "provacadastrada_documento_fonte_questoes_id"),
    ):
        assert all(column[2] is not None for column in banco.execute_sql(f'PRAGMA index_info("{index}")').fetchall())
