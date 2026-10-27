"""Staging transacional e idempotente para propostas sem identidade certificada."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


def stage_proposals(path: str | Path, proposals: list[dict], *, fail_after: int | None = None) -> dict:
    """Guarda propostas sem tocar no acervo; mesmas propostas não duplicam.

    A chave deriva da prova/questão candidata, hash da origem e payload. Itens
    sem correspondência ficam no staging, nunca são aplicados por posição.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target, timeout=10) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("""CREATE TABLE IF NOT EXISTS propostas_reimportacao (
            chave TEXT PRIMARY KEY,
            arquivo TEXT NOT NULL,
            sha256_fonte TEXT,
            prova_id INTEGER,
            questao_id INTEGER,
            ordem_candidata INTEGER,
            status TEXT NOT NULL DEFAULT 'pendente',
            payload_json TEXT NOT NULL,
            criada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS proposta_status ON propostas_reimportacao(status)")
        columns = {row[1] for row in connection.execute('PRAGMA table_info("propostas_reimportacao")')}
        if "responsavel" not in columns:
            connection.execute('ALTER TABLE propostas_reimportacao ADD COLUMN responsavel TEXT')
        if "justificativa" not in columns:
            connection.execute('ALTER TABLE propostas_reimportacao ADD COLUMN justificativa TEXT')
        before = connection.total_changes
        try:
            with connection:
                for index, item in enumerate(proposals, 1):
                    canonical = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                    key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                    initial_status = ("sem_diferencas" if item.get("status") == "sem_diferenca_estrutural_detectada"
                                      else "pendente")
                    connection.execute(
                        "INSERT OR IGNORE INTO propostas_reimportacao "
                        "(chave, arquivo, sha256_fonte, prova_id, questao_id, ordem_candidata, status, payload_json) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (key, str(item.get("arquivo") or ""), item.get("sha256_fonte"),
                         item.get("prova_id"), item.get("questao_id"), item.get("ordem_candidata"),
                         initial_status, canonical),
                    )
                    if fail_after is not None and index >= fail_after:
                        raise RuntimeError("falha simulada durante staging")
        except Exception:
            raise
        inserted = connection.total_changes - before
        total = connection.execute("SELECT COUNT(*) FROM propostas_reimportacao").fetchone()[0]
        pending = connection.execute("SELECT COUNT(*) FROM propostas_reimportacao WHERE status='pendente'").fetchone()[0]
    return {"novas": inserted, "total": total, "pendentes": pending, "banco": str(target)}


def list_proposals(path: str | Path, *, status: str | None = None) -> list[dict]:
    target = Path(path)
    if not target.is_file():
        return []
    with sqlite3.connect(target) as connection:
        connection.row_factory = sqlite3.Row
        query = "SELECT * FROM propostas_reimportacao"
        params = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY arquivo, ordem_candidata, chave"
        return [dict(row) for row in connection.execute(query, params)]


def decide_proposal(path: str | Path, key: str, *, decision: str, reviewer: str, rationale: str) -> None:
    """Registra aprovação/rejeição declarada; não toca no banco do acervo."""
    if decision not in {"aprovada", "rejeitada"} or not reviewer.strip() or not rationale.strip():
        raise ValueError("Decisão, responsável e justificativa são obrigatórios.")
    with sqlite3.connect(path, timeout=10) as connection, connection:
        cursor = connection.execute(
            "UPDATE propostas_reimportacao SET status=?, responsavel=?, justificativa=? "
            "WHERE chave=? AND status='pendente'",
            (decision, reviewer.strip(), rationale.strip(), key),
        )
        if cursor.rowcount != 1:
            raise ValueError("Proposta inexistente ou já decidida; nenhuma alteração foi aplicada.")


def mark_applied(path: str | Path, key: str) -> None:
    with sqlite3.connect(path, timeout=10) as connection, connection:
        cursor = connection.execute(
            "UPDATE propostas_reimportacao SET status='aplicada' WHERE chave=? AND status='aprovada'",
            (key,),
        )
        if cursor.rowcount != 1:
            row = connection.execute("SELECT status FROM propostas_reimportacao WHERE chave=?", (key,)).fetchone()
            if row and row[0] == "aplicada":
                return
            raise ValueError("Proposta não está aprovada para aplicação.")
