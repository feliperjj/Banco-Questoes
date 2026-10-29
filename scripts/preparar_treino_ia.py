"""Exporta exemplos humanos para JSONL; não executa treinamento."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.ia_dataset import export_dataset, validate_export


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--holdout-group", action="append", default=[])
    parser.add_argument("--verify-export", type=Path, help="valida um export existente; não exporta")
    args = parser.parse_args()
    if args.verify_export is not None:
        if args.dataset or args.output or args.holdout_group:
            parser.error("--verify-export é mutuamente exclusivo de --dataset/--output")
        print(json.dumps(validate_export(args.verify_export), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.dataset is None or args.output is None:
        parser.error("--dataset e --output são obrigatórios ao exportar")
    result = export_dataset(args.dataset, args.output, holdout_groups=args.holdout_group)
    print(json.dumps({"manifest": result["manifest"], "readiness": result["readiness"], "output_dir": str(result["output_dir"])}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

