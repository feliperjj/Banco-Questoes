"""Prepara (ou aplica explicitamente) uma reconstrução canônica de cadernos."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import DB_PATH
from src.models.reconstrucao_canonica import apply_canonical, prepare_canonical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--provas", type=int, nargs="+")
    parser.add_argument("--saida", type=Path)
    parser.add_argument("--aplicar", type=Path, metavar="PROPOSTA_JSON")
    args = parser.parse_args()
    if args.aplicar:
        result = apply_canonical(args.aplicar, db_path=args.db)
    else:
        path, summary = prepare_canonical(db_path=args.db, proof_ids=args.provas, output=args.saida)
        result = dict(summary, proposta=str(path))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
