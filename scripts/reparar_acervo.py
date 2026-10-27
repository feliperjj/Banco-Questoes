"""Prepara e aplica reparos rastreáveis preservando IDs e histórico."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import DB_PATH
from src.models.reparacao_service import prepare_repair, apply_repair

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--provas", type=int, nargs="+")
    parser.add_argument("--saida", type=Path)
    parser.add_argument("--aplicar", type=Path, metavar="PROPOSTA_JSON")
    args = parser.parse_args()
    if args.aplicar:
        applied = apply_repair(args.aplicar, db_path=args.db)
        result = {key: value for key, value in applied.items() if key != "pendencias"}
        result["pendencias"] = len(applied["pendencias"])
        result["relatorio"] = str(args.aplicar.with_name("resultado_aplicacao.json"))
    else:
        path, result = prepare_repair(db_path=args.db, output_dir=args.saida, proof_ids=args.provas)
        result = dict(result, proposta=str(path))
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
