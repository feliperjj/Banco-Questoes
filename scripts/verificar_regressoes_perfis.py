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
              if k not in {"perfil_importacao", "aviso_importacao", "perfil_extracao", "diagnostico_importacao", "ordem_visual"}} for q in questoes]
    return hashlib.sha256(json.dumps(dados, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def diagnosticar(questoes, referencia):
    """Mantém o confronto estrito e identifica a extensão de contrato de 2e8797c.

    Naquele parser o dicionário inicial não incluía instrucoes_prova nem
    texto_apoio. A projeção serve somente para explicar a diferença: não
    substitui a assinatura integral e não aprova os campos novos.
    """
    current = assinatura(questoes)
    legacy = [{key: value for key, value in question.items()
               if key not in {"instrucoes_prova", "texto_apoio"}} for question in questoes]
    empty_only = [{key: value for key, value in question.items()
                   if key != "instrucoes_prova" and (key != "texto_apoio" or value)} for question in questoes]
    return {"quantidade_esperada": referencia["quantidade"], "quantidade_extraida": len(questoes),
        "hash_esperado": referencia["sha256"], "hash_atual": current,
        "assinatura_integral_igual": current == referencia["sha256"],
        "projecao_campos_antigos_igual": assinatura(legacy) == referencia["sha256"],
        "projecao_sem_novos_campos_vazios_igual": assinatura(empty_only) == referencia["sha256"],
        "campos_novos_sem_referencia": ["instrucoes_prova", "texto_apoio"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--referencia", type=Path, default=ROOT / "tests/fixtures/perfis_corrigidos_manifest.json")
    parser.add_argument("--diagnostico-json", type=Path, help="Grava classificação por documento sem alterar a referência.")
    args = parser.parse_args()
    manifesto = json.loads(args.referencia.read_text(encoding="utf-8"))
    falhas = []
    diagnosticos = []
    for item in manifesto:
        caminho = ROOT / item["arquivo"]
        if not caminho.exists():
            falhas.append(item["arquivo"] + ": arquivo ausente")
            continue
        questoes = parsear_questoes(extrair_texto_pdf(str(caminho)), str(caminho))
        detail = {"arquivo": item["arquivo"], **diagnosticar(questoes, item)}
        diagnosticos.append(detail)
        ok = len(questoes) == item["quantidade"] and assinatura(questoes) == item["sha256"]
        classification = "campos antigos preservados; contexto/instruções sem referência" if detail["projecao_campos_antigos_igual"] else "diferença nos campos anteriores; conferir fonte"
        print(f'{"OK" if ok else "DIFERENCA"}: {item["arquivo"]} ({len(questoes)}; {classification})', flush=True)
        if not ok:
            falhas.append(item["arquivo"])
    print(f"{len(manifesto) - len(falhas)}/{len(manifesto)} referências preservadas")
    print(f"{sum(d['projecao_campos_antigos_igual'] for d in diagnosticos)}/{len(manifesto)} projeções dos campos anteriores preservadas")
    if args.diagnostico_json:
        args.diagnostico_json.parent.mkdir(parents=True, exist_ok=True)
        args.diagnostico_json.write_text(json.dumps(diagnosticos, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(bool(falhas))


if __name__ == "__main__":
    raise SystemExit(main())
