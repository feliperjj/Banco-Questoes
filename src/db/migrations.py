"""Migrações incrementais não destrutivas do SQLite."""

from __future__ import annotations

import os
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4

CURRENT_SCHEMA_VERSION = 8

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

PROVA_TABLES_V2 = (
    """
    CREATE TABLE IF NOT EXISTS provas_cadastradas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        arquivo_questoes TEXT,
        arquivo_gabarito TEXT,
        ativa INTEGER NOT NULL DEFAULT 1,
        criada_em DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prova_cadastrada_questoes (
        prova_cadastrada_id INTEGER NOT NULL,
        questao_id INTEGER NOT NULL,
        ordem INTEGER NOT NULL,
        PRIMARY KEY (prova_cadastrada_id, questao_id),
        FOREIGN KEY (prova_cadastrada_id) REFERENCES provas_cadastradas(id),
        FOREIGN KEY (questao_id) REFERENCES questoes(id)
    )
    """,
)

QUESTAO_COLUMNS_V3 = {"imagem_path": "TEXT"}
QUESTAO_COLUMNS_V4 = {"texto_apoio": "TEXT"}
PROVA_COLUMNS_V4 = {"instrucoes_prova": "TEXT"}


def _snapshot_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    return {table: connection.execute(f' SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}


def _arquivo_fonte(raiz: Path, value: str | None) -> tuple[Path | None, str]:
    if not value:
        return None, "nao_informado"
    path = Path(value)
    if not path.is_absolute():
        direto = raiz / path
        por_samples = raiz / "samples" / path
        path = direto if direto.is_file() else por_samples if por_samples.is_file() else direto
    return path, "presente" if path.is_file() else "ausente"


def _hash_arquivo(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _registrar_fonte(database, raiz: Path, valor: str | None) -> int | None:
    path, availability = _arquivo_fonte(raiz, valor)
    if path is None:
        return None
    sha256 = _hash_arquivo(path) if availability == "presente" else None
    if sha256:
        existente = database.execute_sql(
            'SELECT id FROM documentos_fonte WHERE sha256 = ?', (sha256,)
        ).fetchone()
        if existente:
            return int(existente[0])
    cursor = database.execute_sql(
        "INSERT INTO documentos_fonte (sha256, tipo, localizacao, disponibilidade, criado_em) VALUES (?, ?, ?, ?, ?)",
        (sha256, path.suffix.lower().lstrip(".") or "desconhecido", str(path), availability, datetime.now().isoformat(timespec="seconds")),
    )
    return int(cursor.lastrowid)


def _criar_snapshots_legados(database) -> None:
    """Captura o conteúdo disponível hoje sem declarar revisão ou história anterior."""
    nomes = ["numero_oficial", "enunciado", "texto_apoio", "tipo", "disciplina", "topico", "banca", "ano", "cargo", "orgao", "dificuldade", "gabarito", "comentario", "imagem_path"]
    selecao = ", ".join(f'"{nome}"' for nome in nomes)
    questoes = database.execute_sql(f'SELECT id, {selecao} FROM questoes ORDER BY id').fetchall()
    alternativas = {}
    for qid, letra, texto in database.execute_sql(
        'SELECT questao_id, letra, texto FROM alternativas ORDER BY questao_id, letra'
    ).fetchall():
        alternativas.setdefault(qid, []).append({"letra": letra, "texto": texto})
    for row in questoes:
        questao = dict(zip(["id", *nomes], row))
        conteudo = {**{nome: questao[nome] for nome in nomes}, "alternativas": alternativas.get(questao["id"], [])}
        serializado = json.dumps(conteudo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serializado.encode("utf-8")).hexdigest()
        database.execute_sql(
            "INSERT OR IGNORE INTO questoes_versoes "
            "(questao_id, numero_versao, hash_conteudo, conteudo_json, revisao_conteudo, revisao_gabarito, criada_em) "
            "VALUES (?, 1, ?, ?, 'pendente', 'desconhecido', ?)",
            (questao["id"], digest, serializado, datetime.now().isoformat(timespec="seconds")),
        )


def backup_before_structural_change(database) -> Path:
    """Cria e valida snapshot SQLite consistente, inclusive com WAL ativo."""
    db_path = Path(str(database.database))
    if str(database.database) == ":memory:":
        raise ValueError("Backup estrutural exige um banco SQLite em arquivo.")
    destino = db_path.with_name(
        f"{db_path.stem}.pre-migration-{datetime.now():%Y%m%d-%H%M%S-%f}-{uuid4().hex[:6]}{db_path.suffix}"
    )
    teste = db_path.with_name(f".{destino.stem}.restore-check.db")
    if destino.exists() or teste.exists():
        raise FileExistsError("Caminho de backup/restauração já existe; nenhum arquivo foi sobrescrito.")
    try:
        with closing(sqlite3.connect(destino)) as target:
            with target:
                database.connection().backup(target)
        with destino.open("r+b") as stream:
            os.fsync(stream.fileno())
        with closing(sqlite3.connect(destino)) as backup:
            backup_counts = _snapshot_counts(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup SQLite falhou em integrity_check.")
            if backup.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Backup SQLite contém violações de chave estrangeira.")
            source_counts = _snapshot_counts(database.connection())
            if backup_counts != source_counts:
                raise RuntimeError("As contagens do backup divergem do banco de origem.")
            with closing(sqlite3.connect(teste)) as restored:
                with restored:
                    backup.backup(restored)
        with closing(sqlite3.connect(teste)) as restored:
            if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Cópia de restauração do backup falhou em integrity_check.")
            if restored.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Cópia restaurada contém violações de chave estrangeira.")
            if _snapshot_counts(restored) != source_counts:
                raise RuntimeError("Contagens da cópia restaurada divergem do banco de origem.")
        return destino
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    finally:
        teste.unlink(missing_ok=True)


def apply_migrations(database, banco_existente: bool = True) -> None:
    database.execute_sql("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    if database.execute_sql("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
        database.execute_sql("INSERT INTO schema_version (version) VALUES (0)")
    versao = int(database.execute_sql("SELECT version FROM schema_version LIMIT 1").fetchone()[0])
    existentes = {
        linha[1] for linha in database.execute_sql('PRAGMA table_info("questoes")').fetchall()
    }
    faltantes = {nome: tipo for nome, tipo in QUESTAO_COLUMNS_V1.items() if nome not in existentes}
    if versao < 1 or faltantes:
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
    if versao < 2:
        with database.atomic():
            for definicao in PROVA_TABLES_V2:
                database.execute_sql(definicao)
            database.execute_sql("UPDATE schema_version SET version = ?", (2,))
        versao = 2
    if versao < 3:
        existentes = {
            linha[1] for linha in database.execute_sql('PRAGMA table_info("questoes")').fetchall()
        }
        faltantes = {nome: tipo for nome, tipo in QUESTAO_COLUMNS_V3.items() if nome not in existentes}
        with database.atomic():
            for nome, definicao in faltantes.items():
                database.execute_sql(f'ALTER TABLE "questoes" ADD COLUMN "{nome}" {definicao}')
            database.execute_sql("UPDATE schema_version SET version = ?", (3,))
        versao = 3
    if versao < 4:
        questoes_existentes = {
            linha[1] for linha in database.execute_sql('PRAGMA table_info("questoes")').fetchall()
        }
        provas_existentes = {
            linha[1] for linha in database.execute_sql('PRAGMA table_info("provas_cadastradas")').fetchall()
        }
        questoes_faltantes = {
            nome: tipo for nome, tipo in QUESTAO_COLUMNS_V4.items() if nome not in questoes_existentes
        }
        provas_faltantes = {
            nome: tipo for nome, tipo in PROVA_COLUMNS_V4.items() if nome not in provas_existentes
        }
        with database.atomic():
            for nome, definicao in questoes_faltantes.items():
                database.execute_sql(f'ALTER TABLE "questoes" ADD COLUMN "{nome}" {definicao}')
            for nome, definicao in provas_faltantes.items():
                database.execute_sql(f'ALTER TABLE "provas_cadastradas" ADD COLUMN "{nome}" {definicao}')
            database.execute_sql("UPDATE schema_version SET version = ?", (4,))
        versao = 4
    if versao < 5:
        questao_colunas = {
            linha[1] for linha in database.execute_sql('PRAGMA table_info("questoes")').fetchall()
        }
        colunas = {
            linha[1] for linha in database.execute_sql('PRAGMA table_info("prova_questoes")').fetchall()
        }
        colunas_provas = {
            linha[1] for linha in database.execute_sql('PRAGMA table_info("provas_cadastradas")').fetchall()
        }
        colunas_vinculo_cadastrada = {
            linha[1] for linha in database.execute_sql('PRAGMA table_info("prova_cadastrada_questoes")').fetchall()
        }
        colunas_respostas = {
            linha[1] for linha in database.execute_sql('PRAGMA table_info("respostas")').fetchall()
        }
        with database.atomic():
            if "numero_oficial" not in questao_colunas:
                database.execute_sql('ALTER TABLE "questoes" ADD COLUMN "numero_oficial" INTEGER')
            if "questao_versao_id" not in colunas:
                database.execute_sql(
                    'ALTER TABLE "prova_questoes" ADD COLUMN "questao_versao_id" INTEGER '
                    'REFERENCES "questoes_versoes"("id")'
                )
            if "documento_fonte_questoes_id" not in colunas_provas:
                database.execute_sql(
                    'ALTER TABLE "provas_cadastradas" ADD COLUMN "documento_fonte_questoes_id" INTEGER '
                    'REFERENCES "documentos_fonte"("id")'
                )
            if "documento_fonte_gabarito_id" not in colunas_provas:
                database.execute_sql(
                    'ALTER TABLE "provas_cadastradas" ADD COLUMN "documento_fonte_gabarito_id" INTEGER '
                    'REFERENCES "documentos_fonte"("id")'
                )
            if "questao_versao_id" not in colunas_vinculo_cadastrada:
                database.execute_sql(
                    'ALTER TABLE "prova_cadastrada_questoes" ADD COLUMN "questao_versao_id" INTEGER '
                    'REFERENCES "questoes_versoes"("id")'
                )
            if "questao_versao_id" not in colunas_respostas:
                database.execute_sql(
                    'ALTER TABLE "respostas" ADD COLUMN "questao_versao_id" INTEGER '
                    'REFERENCES "questoes_versoes"("id")'
                )
            raiz = Path(str(database.database)).resolve().parent.parent
            if "provas_cadastradas" in {
                row[0] for row in database.execute_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }:
                for proof_id, questions_path, answers_path in database.execute_sql(
                    "SELECT id, arquivo_questoes, arquivo_gabarito FROM provas_cadastradas ORDER BY id"
                ).fetchall():
                    questions_source = _registrar_fonte(database, raiz, questions_path)
                    answers_source = _registrar_fonte(database, raiz, answers_path)
                    database.execute_sql(
                        "UPDATE provas_cadastradas SET documento_fonte_questoes_id = ?, "
                        "documento_fonte_gabarito_id = ? WHERE id = ?",
                        (questions_source, answers_source, proof_id),
                    )
            _criar_snapshots_legados(database)
            database.execute_sql(
                "UPDATE questoes_versoes SET documento_fonte_id = ("
                "SELECT MIN(pc.documento_fonte_questoes_id) "
                "FROM prova_cadastrada_questoes pq "
                "JOIN provas_cadastradas pc ON pc.id = pq.prova_cadastrada_id "
                "WHERE pq.questao_id = questoes_versoes.questao_id "
                "AND pc.documento_fonte_questoes_id IS NOT NULL "
                "GROUP BY pq.questao_id HAVING COUNT(DISTINCT pc.documento_fonte_questoes_id) = 1) "
                "WHERE numero_versao = 1"
            )
            database.execute_sql("UPDATE schema_version SET version = ?", (5,))
        versao = 5
    if versao < 6:
        evidence_columns = {
            row[1] for row in database.execute_sql('PRAGMA table_info("evidencias_questao")').fetchall()
        }
        with database.atomic():
            if "escopo_json" not in evidence_columns:
                database.execute_sql(
                    'ALTER TABLE "evidencias_questao" ADD COLUMN "escopo_json" TEXT NOT NULL DEFAULT \'{}\''
                )
            database.execute_sql("UPDATE schema_version SET version = ?", (6,))
        versao = 6
    if versao < 7:
        with database.atomic():
            database.execute_sql(
                "CREATE TABLE IF NOT EXISTS resolucoes_diagnostico ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "questao_versao_id INTEGER NOT NULL REFERENCES questoes_versoes(id), "
                "codigo TEXT NOT NULL, versao_regra TEXT NOT NULL, decisao TEXT NOT NULL, "
                "responsavel_declarado TEXT NOT NULL, justificativa TEXT NOT NULL, "
                "evidencia_json TEXT NOT NULL DEFAULT '[]', fingerprint_evidencias TEXT NOT NULL, "
                "criada_em DATETIME NOT NULL)"
            )
            database.execute_sql("CREATE INDEX IF NOT EXISTS resolucao_diagnostico_versao ON resolucoes_diagnostico(questao_versao_id)")
            database.execute_sql("UPDATE schema_version SET version = ?", (7,))
        versao = 7
    if versao < 8:
        with database.atomic():
            database.execute_sql(
                "CREATE TABLE IF NOT EXISTS validacoes_automaticas ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "questao_versao_id INTEGER NOT NULL REFERENCES questoes_versoes(id), "
                "versao_regra TEXT NOT NULL, hash_snapshot TEXT NOT NULL, "
                "fingerprint_evidencias TEXT NOT NULL, evidencia_json TEXT NOT NULL DEFAULT '[]', "
                "manifesto_json TEXT NOT NULL DEFAULT '{}', criada_em DATETIME NOT NULL)"
            )
            database.execute_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS validacao_automatica_identidade "
                "ON validacoes_automaticas(questao_versao_id, versao_regra, hash_snapshot, fingerprint_evidencias)"
            )
            database.execute_sql("UPDATE schema_version SET version = ?", (8,))
        versao = 8
    if versao != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Versão de schema não suportada: {versao}; esperada: {CURRENT_SCHEMA_VERSION}."
        )
