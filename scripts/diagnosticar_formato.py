"""Diagnóstico por formato: gera JSON revisável sem gravar questões no banco."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.importador.servico import importar_caderno
from src.importador.extrator import extrair_gabaritos_pdf
from src.importador.validacao import associar_gabaritos


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('caderno')
    parser.add_argument('--gabarito')
    parser.add_argument('--cargo',default='')
    parser.add_argument('--codigo',default='')
    parser.add_argument('--saida',required=True)
    args=parser.parse_args()
    lote=importar_caderno(args.caderno)
    relatorio=lote.relatorio
    if args.gabarito:
        gab=extrair_gabaritos_pdf(args.gabarito,args.codigo,args.cargo, numeros_esperados={q['numero'] for q in lote})
        relatorio['gabarito']=associar_gabaritos(lote,gab)
        relatorio['conflitos_na_fonte']=sorted(getattr(gab,'conflitos',()))
    relatorio['questoes']=list(lote)
    Path(args.saida).write_text(json.dumps(relatorio,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(lote)} questões; diagnóstico salvo em {args.saida}')


if __name__=='__main__':
    main()
