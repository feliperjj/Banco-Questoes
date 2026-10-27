"""Lista, registra decisão humana e aplica propostas explicitamente aprovadas."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DB_PATH, REPORTS_DIR
from src.db.database import db, init_db
from src.db.migrations import backup_before_structural_change
from src.db.models import ProvaCadastradaQuestao
from src.importador.reimportacao_staging import decide_proposal, list_proposals, mark_applied
from src.models import questoes_repo as repo


STAGING_DEFAULT = REPORTS_DIR / "reimportacao_staging_v2.sqlite3"


def _normal(value):
    if value == "":
        return None
    if isinstance(value, list):
        return sorted((_normal(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    if isinstance(value, dict):
        return {key: _normal(item) for key, item in sorted(value.items())}
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aplicar_aprovadas(staging_path: Path, db_path: Path) -> dict:
    approved = list_proposals(staging_path, status="aprovada")
    if not approved:
        return {"aplicadas": 0, "backup": None, "pendencias": []}
    init_db(str(db_path))
    prepared = []
    issues = []
    for row in approved:
        payload = json.loads(row["payload_json"])
        qid, proof_id = row.get("questao_id"), row.get("prova_id")
        proposed, expected = payload.get("proposta"), payload.get("conteudo_atual")
        if not qid or not proof_id or not isinstance(proposed, dict) or not isinstance(expected, dict):
            issues.append({"chave": row["chave"], "motivo": "identidade_ou_snapshot_ausente"})
            continue
        source_path = Path(payload.get("fonte_path") or "")
        if (not source_path.is_file() or not row.get("sha256_fonte")
                or _sha256(source_path) != row["sha256_fonte"]):
            issues.append({"chave": row["chave"], "motivo": "fonte_ausente_ou_alterada"})
            continue
        if not ProvaCadastradaQuestao.select().where(
            (ProvaCadastradaQuestao.prova_cadastrada == proof_id)
            & (ProvaCadastradaQuestao.questao == qid)
        ).exists():
            issues.append({"chave": row["chave"], "motivo": "vinculo_prova_questao_divergente"})
            continue
        current = repo.obter_questao(int(qid))
        fields = set(expected)
        if not current or _normal({key: current.get(key) for key in fields}) != _normal(expected):
            # A retry after the DB commit but before the staging status update
            # is safe: recognize the exact proposed content without versioning again.
            if current and _normal({key: current.get(key) for key in proposed}) == _normal(proposed):
                prepared.append((row["chave"], int(qid), None))
            else:
                issues.append({"chave": row["chave"], "motivo": "questao_mudou_desde_a_conferencia"})
            continue
        differences = payload.get("diferencas") or {}
        if not differences:
            issues.append({"chave": row["chave"], "motivo": "sem_diferencas_para_aplicar"})
            continue
        prepared.append((row["chave"], int(qid), proposed))

    if issues:
        return {"aplicadas": 0, "backup": None, "pendencias": issues}
    if not any(proposal is not None for _, _, proposal in prepared):
        for key, _, _ in prepared:
            mark_applied(staging_path, key)
        return {"aplicadas": len(prepared), "backup": None, "pendencias": []}

    backup = backup_before_structural_change(db)
    with db.atomic():
        for _, qid, proposal in prepared:
            if proposal is not None:
                repo.atualizar_questao(qid, proposal)
    for key, _, _ in prepared:
        mark_applied(staging_path, key)
    return {"aplicadas": len(prepared), "backup": str(backup), "pendencias": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, default=STAGING_DEFAULT)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--decidir", metavar="CHAVE")
    parser.add_argument("--decisao", choices=("aprovar", "rejeitar"))
    parser.add_argument("--responsavel")
    parser.add_argument("--justificativa")
    parser.add_argument("--aplicar-aprovadas", action="store_true")
    parser.add_argument("--status", choices=("pendente", "aprovada", "rejeitada", "aplicada", "sem_diferencas"))
    args = parser.parse_args()
    if args.decidir:
        decision = {"aprovar": "aprovada", "rejeitar": "rejeitada"}.get(args.decisao)
        if not decision:
            parser.error("--decidir exige --decisao aprovar|rejeitar")
        try:
            decide_proposal(args.staging, args.decidir, decision=decision,
                            reviewer=args.responsavel or "", rationale=args.justificativa or "")
        except ValueError as error:
            parser.error(str(error))
        print(f"Decisão {decision} registrada; nenhuma proposta foi aplicada.")
        return 0
    if args.aplicar_aprovadas:
        result = aplicar_aprovadas(args.staging, args.db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(bool(result["pendencias"]))
    rows = list_proposals(args.staging, status=args.status)
    for row in rows:
        print(f"{row['chave']}\t{row['status']}\t{row['arquivo']}\tqID={row['questao_id']}\tordem={row['ordem_candidata']}")
    print(f"{len(rows)} proposta(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
