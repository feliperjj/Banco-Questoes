"""Verificação somente leitura: não atualiza a referência nem o banco."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.importador.extrator import extrair_texto_pdf
from src.importador.parser import parsear_questoes


def assinatura(questoes):
    dados = [{k: v for k, v in q.items()
              if k not in {"perfil_importacao", "aviso_importacao", "perfil_extracao", "diagnostico_importacao"}} for q in questoes]
    return hashlib.sha256(json.dumps(dados, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--referencia", type=Path, default=ROOT / "tests/fixtures/perfis_corrigidos_manifest.json")
    args = parser.parse_args()
    manifesto = json.loads(args.referencia.read_text(encoding="utf-8"))
    falhas = []
    for item in manifesto:
        caminho = ROOT / item["arquivo"]
        if not caminho.exists():
            falhas.append(item["arquivo"] + ": arquivo ausente")
            continue
        questoes = parsear_questoes(extrair_texto_pdf(str(caminho)), str(caminho))
        ok = len(questoes) == item["quantidade"] and assinatura(questoes) == item["sha256"]
        print(f'{"OK" if ok else "DIFERENCA"}: {item["arquivo"]} ({len(questoes)})', flush=True)
        if not ok:
            falhas.append(item["arquivo"])
    print(f"{len(manifesto) - len(falhas)}/{len(manifesto)} referências preservadas")
    return int(bool(falhas))


if __name__ == "__main__":
    raise SystemExit(main())
