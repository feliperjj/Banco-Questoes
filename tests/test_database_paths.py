from src.db.database import init_db
import sqlite3


def test_init_db_cria_versionamento_sem_apagar_banco(tmp_path):
    caminho = tmp_path / "subdir" / "teste.db"
    banco = init_db(str(caminho))
    versao = banco.execute_sql("SELECT version FROM schema_version").fetchone()[0]
    assert versao == 1


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
    assert banco.execute_sql("SELECT enunciado FROM questoes").fetchone()[0] == "legada"
    assert list(tmp_path.glob("legado.backup-*.db"))
