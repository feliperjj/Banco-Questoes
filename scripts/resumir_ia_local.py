"""Resume durações locais observadas, sem alegar economia causal de tempo."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models.ia_metrics import summarize_sessions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize_sessions(args.directory), ensure_ascii=False, indent=2))
