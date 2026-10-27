import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar

from peewee import SqliteDatabase
from src.config import DB_PATH, PRODUCTION_DB_PATH, TEST_MODE
from src.db.migrations import CURRENT_SCHEMA_VERSION, apply_migrations, backup_before_structural_change


DB_DIR = DB_PATH.parent
db = SqliteDatabase(str(DB_PATH), pragmas={"foreign_keys": 1})
LAST_VERIFIED_SCHEMA_BACKUP = None
_initialized_batch = ContextVar("initialized_database_batch", default=None)


@contextmanager
def initialized_database_batch():
    """Evita DDL repetido dentro de uma operação já inicializada e transacional."""
    if db.is_closed():
        raise RuntimeError("Inicialize o banco antes de iniciar o lote.")
    token = _initialized_batch.set((str(db.database), id(db.connection())))
    try:
        yield
    finally:
        _initialized_batch.reset(token)

_INDEXES_ADDED_BY_SCHEMA_5 = {
    "provaquestao_questao_versao_id",
    "resposta_questao_versao_id",
    "provacadastrada_documento_fonte_questoes_id",
    "provacadastrada_documento_fonte_gabarito_id",
    "provacadastradaquestao_questao_versao_id",
}


def _configure_database(db_path):
    if TEST_MODE:
        requested = Path(str(db_path)).expanduser().resolve()
        if requested == PRODUCTION_DB_PATH or requested.is_relative_to(PRODUCTION_DB_PATH.parent):
            raise RuntimeError(
                "Execução de teste bloqueada: conexão ao banco real data/questoes.db recusada. "
                "Defina BANCO_QUESTOES_DB_PATH para um arquivo temporário."
            )
    if db.database != db_path:
        if not db.is_closed():
            db.close()
        db.init(db_path)


def _needs_structural_backup(db_path: str) -> bool:
    path = Path(str(db_path))
    if not path.is_file() or not path.stat().st_size or str(db_path) == ":memory:":
        return False
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "schema_version" not in tables:
            return True
        version = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if version is None or int(version[0]) < CURRENT_SCHEMA_VERSION:
            return True
        required_tables = {
            "documentos_fonte", "execucoes_extracao", "questoes_versoes",
            "evidencias_questao", "revisoes_conteudo", "revisoes_gabarito",
            "resolucoes_diagnostico",
            "validacoes_automaticas",
        }
        if not required_tables.issubset(tables):
            return True
        columns = {row[1] for row in connection.execute('PRAGMA table_info("prova_questoes")')}
        links = {row[1] for row in connection.execute('PRAGMA table_info("prova_cadastrada_questoes")')}
        proof_sources = {row[1] for row in connection.execute('PRAGMA table_info("provas_cadastradas")')}
        question_columns = {row[1] for row in connection.execute('PRAGMA table_info("questoes")')}
        response_columns = {row[1] for row in connection.execute('PRAGMA table_info("respostas")')}
        evidence_columns = {row[1] for row in connection.execute('PRAGMA table_info("evidencias_questao")')}
        return (
            "questao_versao_id" not in columns
            or "questao_versao_id" not in links
            or "numero_oficial" not in question_columns
            or "questao_versao_id" not in response_columns
            or not {"documento_fonte_questoes_id", "documento_fonte_gabarito_id"}.issubset(proof_sources)
            or "escopo_json" not in evidence_columns
        )


def _defer_indexes_with_missing_columns() -> list[str]:
    """Avoid Peewee's early indexes on columns added by the pending migration."""
    deferred = []
    tables = [row[0] for row in db.execute_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for table in tables:
        for index in db.execute_sql(f'PRAGMA index_list("{table}")').fetchall():
            name = index[1]
            if name not in _INDEXES_ADDED_BY_SCHEMA_5:
                continue
            info = db.execute_sql(f'PRAGMA index_info("{name}")').fetchall()
            if not info or any(column[2] is None for column in info):
                row = db.execute_sql(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name = ?", (name,)
                ).fetchone()
                # Indexes over expressions can also have a NULL name; preserve
                # known SQL only when a migration is in flight, then recreate
                # after the new columns exist.
                if row and row[0]:
                    deferred.append(row[0])
                    db.execute_sql(f'DROP INDEX "{name}"')
    return deferred


def init_db(db_path=None):
    global LAST_VERIFIED_SCHEMA_BACKUP
    db_path = db.database if db_path is None else db_path
    banco_existente = Path(str(db_path)).is_file() and Path(str(db_path)).stat().st_size > 0
    _configure_database(db_path)
    if not db.is_closed() and _initialized_batch.get() == (str(db.database), id(db.connection())):
        return db
    os.makedirs(os.path.dirname(str(db_path)) or ".", exist_ok=True)
    db.connect(reuse_if_open=True)
    if banco_existente and _needs_structural_backup(str(db_path)):
        # Backup validado antes de create_tables/ALTER TABLE. Se falhar, a
        # aplicação interrompe a inicialização antes de modificar o banco.
        LAST_VERIFIED_SCHEMA_BACKUP = backup_before_structural_change(db)
    from src.db.models import ALL_MODELS
    # Tables, indexes, and additive migrations form one SQLite transaction.
    # Peewee may expose indexes over columns added by a pending migration; hold
    # those indexes until the columns exist, so migration failure rolls back all
    # schema work to the backed-up legacy state.
    with db.atomic():
        db.create_tables(ALL_MODELS, safe=True)
        deferred_indexes = _defer_indexes_with_missing_columns()
        apply_migrations(db, banco_existente=banco_existente)
        for sql in deferred_indexes:
            db.execute_sql(sql)
    return db




class _ConnectionCompatibility:
    """Ponte mínima para a consulta legada do dashboard sem expor sqlite3."""

    def execute(self, sql, parameters=None):
        return db.execute_sql(sql, parameters or ())

    def close(self):
        return None


def get_connection():
    init_db()
    return _ConnectionCompatibility()
