"""Migrações incrementais não destrutivas do SQLite."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

CURRENT_SCHEMA_VERSION = 1

QUESTAO_COLUMNS_V1 = {
    "disciplina": "TEXT",
    "topico": "TEXT",
    "banca": "TEXT",
    "ano": "INTEGER",
    "cargo": "TEXT",
    "orgao": "TEXT",
    "dificuldade": "TEXT",
    "gabarito": "TEXT",
    "comentario": "TEXT",
    "ativa": "INTEGER NOT NULL DEFAULT 1",
    "criada_em": "DATETIME",
}


def backup_before_structural_change(db_path: str | Path) -> Path:
    """Cria cópia ao lado do banco antes de uma migração estrutural futura."""
    origem = Path(db_path)
    destino = origem.with_name(f"{origem.stem}.backup-{datetime.now():%Y%m%d%H%M%S}{origem.suffix}")
    shutil.copy2(origem, destino)
    return destino


def apply_migrations(database) -> None:
    database.execute_sql("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    if database.execute_sql("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
        database.execute_sql("INSERT INTO schema_version (version) VALUES (0)")
    versao = int(database.execute_sql("SELECT version FROM schema_version LIMIT 1").fetchone()[0])
    existentes = {
        linha[1] for linha in database.execute_sql('PRAGMA table_info("questoes")').fetchall()
    }
    faltantes = {nome: tipo for nome, tipo in QUESTAO_COLUMNS_V1.items() if nome not in existentes}
    if versao < 1 or faltantes:
        caminho = Path(str(database.database))
        if faltantes and caminho.exists() and caminho.stat().st_size:
            backup_before_structural_change(caminho)
        with database.atomic():
            for nome, definicao in faltantes.items():
                database.execute_sql(f'ALTER TABLE "questoes" ADD COLUMN "{nome}" {definicao}')
            if "criada_em" in faltantes:
                agora = datetime.now().isoformat(sep=" ")
                database.execute_sql(
                    'UPDATE "questoes" SET "criada_em" = ? WHERE "criada_em" IS NULL', (agora,)
                )
            database.execute_sql("UPDATE schema_version SET version = ?", (1,))
        versao = 1
    if versao != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Versão de schema não suportada: {versao}; esperada: {CURRENT_SCHEMA_VERSION}."
        )
