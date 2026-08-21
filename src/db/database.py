import os

from peewee import SqliteDatabase


DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "questoes.db")
db = SqliteDatabase(DB_PATH, pragmas={"foreign_keys": 1})


def _configure_database(db_path):
    if db.database != db_path:
        if not db.is_closed():
            db.close()
        db.init(db_path)


def init_db(db_path=None):
    db_path = db.database if db_path is None else db_path
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    _configure_database(db_path)
    db.connect(reuse_if_open=True)
    from src.db.models import ALL_MODELS
    db.create_tables(ALL_MODELS, safe=True)
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
