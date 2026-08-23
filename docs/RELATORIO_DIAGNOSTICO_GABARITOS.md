# Diagnóstico não destrutivo de gabaritos

Data: 23/08/2026.

## Resultado

| Indicador | Resultado |
|---|---:|
| Cadernos analisados | 23 |
| Questões identificadas | 979 |
| Respostas extraídas dos arquivos catalogados | 996 |
| Vínculos estruturais válidos | 820 |
| Cobertura anterior | 551/979 (56,28%) |
| Cobertura atual | 820/979 (83,76%) |
| Ganho | 269 vínculos / 27,48 p.p. |

A quantidade extraída pode ser maior que a quantidade de questões porque os
PDFs de gabarito incluem respostas extras, outros tipos de prova ou números que
o parser não encontrou no caderno. Somente a interseção com números oficiais
únicos é contabilizada como vínculo.

## Como a meta foi alcançada

- catálogo por caminho relativo, cargo e prova, sem associação aproximada;
- sete correspondências adicionais confirmadas pelos cabeçalhos dos PDFs;
- tratamento de tabelas e formatos `1 A`, `1 - A`, `1: A` e `1) A`;
- continuidade multipágina por cargo/código;
- anulações definitivas aplicadas sobre o gabarito-base do Auditor Fiscal;
- rejeição conservadora de números duplicados;
- OCR reservado para completar números esperados ausentes.

O diagnóstico desta medição usou somente texto e tabelas. OCR não foi
necessário para superar a meta e não foi executado.

## Confirmação após reimportação

Em 23/08/2026, o banco local foi recriado a partir dos 23 cadernos. A consulta
direta após a transação encontrou 979 questões, das quais 820 possuem gabarito
persistido e 159 permanecem sem gabarito. Portanto, a cobertura prevista pelo
diagnóstico foi reproduzida no banco: **820/979 (83,76%)**.

As provas, tentativas, respostas e revisões antigas foram removidas pela
operação, conforme esperado. Antes da limpeza foi criado o backup local
`data/questoes.pre-reimport-2026-08-23.db`.

## Maiores pendências

| Caderno | Potencial pendente | Motivo principal |
|---|---:|---|
| `agente_nivel_superior_analista_de_sistemas.pdf` | 35 | layout T1–T4 ainda não associado de forma segura |
| `agente_administrativo_auxiliar_i.pdf` | 30 | gabarito correspondente não catalogado |
| `agente_administrativo_i-2.pdf` | 30 | tabela matricial por cargo ainda não catalogada |
| `provas_2e3_auditor_fiscal.pdf` | 12 | números duplicados/faltantes no parser do caderno |
| `agente_especializado_analista_de_sistemas.pdf` | 10 | números duplicados no parser |
| `analista_administrativo_iii_analista_de_sistemas.pdf` | 9 | números duplicados e respostas extras |

## Segurança da operação

O comando `scripts/diagnosticar_samples.py` não importa os modelos do banco,
não chama `init_db()` e grava apenas relatórios. Nenhuma questão, prova,
tentativa, resposta ou revisão local foi modificada nesta medição.

“Associação confirmada” significa correspondência explícita entre caderno,
cargo/prova e arquivo de resposta. Alguns arquivos catalogados são gabaritos
preliminares; a consolidação com versões definitivas continua sendo uma etapa
editorial separada.
