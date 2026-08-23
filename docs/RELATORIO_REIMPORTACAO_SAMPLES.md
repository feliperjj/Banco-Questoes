# Relatório de reimportação dos samples

Data da execução: 23/08/2026.

Operação solicitada: apagar as questões e dados dependentes do banco local, sem backup, e importar novamente os PDFs de `samples`.

## Resultado geral

| Indicador | Resultado |
|---|---:|
| PDFs de questões processados | 23 |
| Questões importadas | 979 |
| Alternativas importadas | 4.100 |
| Questões de múltipla escolha | 869 |
| Questões certo/errado | 106 |
| Questões com confiança alta | 954 |
| Questões com confiança média | 25 |
| Questões com confiança baixa | 0 |
| Gabaritos preenchidos | 551 |
| Gabaritos ausentes | 428 |
| Falhas técnicas de extração | 0 |

Comparação com a execução anterior: confiança alta subiu de 919/979 (93,87%) para 954/979 (97,45%), ganho de **3,58 pontos percentuais**. A soma de confiança alta e média passou a cobrir as 979 questões. O total de gabaritos preenchidos permaneceu em 551/979 (56,28%).

## Meta prioritária

O próximo objetivo é aumentar a cobertura de gabaritos confirmados de **56,28% para pelo menos 80%**. Na base desta execução, isso equivale a aproximadamente **783 das 979 questões**, ou cerca de **232 novos vínculos confiáveis**. A cobertura de gabaritos passa a ser a métrica principal; confiança de extração sem resposta correta confirmada não é considerada suficiente.

## Validação automática e revisão manual

A execução também validou número explícito, quantidade declarada e contexto de cargo/prova. Dois dos 23 arquivos passaram integralmente nessa validação; 21 foram marcados para revisão manual. As pendências encontradas foram divergência de quantidade, números duplicados, respostas extras ou respostas faltantes. Esses avisos são conservadores e não removem questões nem deslocam respostas.

As respostas preenchidas vêm de associações por cargo/prova e número explícito. Quando o caderno e o gabarito têm quantidades diferentes, somente os números presentes nos dois lados são vinculados; não há deslocamento posicional.

## Resultado por arquivo

| Arquivo | Questões | Alta | Média | Baixa | Situação |
|---|---:|---:|---:|---:|---|
| `administrador-FGV.pdf` | 75 | 74 | 1 | 0 | 75 gabaritos vinculados; revisar 1 média |
| `agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf` | 51 | 48 | 3 | 0 | Importado; revisar 3 médias |
| `agente_especializado_analista_de_sistemas.pdf` | 61 | 58 | 3 | 0 | Importado; revisar 3 médias |
| `analista_analise_de_sistema_desenvolvimento_de_sistema.pdf` | 6 | 6 | 0 | 0 | Importado; quantidade ainda baixa, conferir contra o PDF |
| `analista_de_planejamento_e_orcamento_especialidade_governanca_e_gestao_de_projetos_de_ti-CEBRASPE.pdf` | 100 | 99 | 1 | 0 | Importado; revisar 1 média |
| `lote_2026_08_22/agente_administrativo_auxiliar_i.pdf` | 30 | 30 | 0 | 0 | Importado |
| `lote_2026_08_22/agente_administrativo_i-1.pdf` | 25 | 25 | 0 | 0 | Importado |
| `lote_2026_08_22/agente_administrativo_i-2.pdf` | 30 | 30 | 0 | 0 | Importado |
| `lote_2026_08_22/agente_administrativo_i-3.pdf` | 49 | 48 | 1 | 0 | Importado; revisar 1 média |
| `lote_2026_08_22/agente_administrativo_i-4.pdf` | 40 | 40 | 0 | 0 | Importado |
| `lote_2026_08_22/agente_administrativo_i.pdf` | 40 | 40 | 0 | 0 | Importado |
| `lote_2026_08_22/agente_nivel_superior_analista_de_sistemas.pdf` | 35 | 35 | 0 | 0 | Importado |
| `lote_2026_08_22/analista_adm_desenvolvimento_sistemas.pdf` | 30 | 30 | 0 | 0 | Importado |
| `lote_2026_08_22/analista_administrativo_iii_analista_de_sistemas.pdf` | 79 | 79 | 0 | 0 | 73 gabaritos vinculados; revisar divergências de numeração |
| `lote_2026_08_22/analista_analista_de_sistemas.pdf` | 43 | 43 | 0 | 0 | 42 gabaritos vinculados; revisar divergências de numeração |
| `lote_2026_08_22/analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf` | 2 | 2 | 0 | 0 | Importado; quantidade baixa, conferir contra o PDF |
| `lote_2026_08_22/analista_area_ciencias_exatas_e_da_terra_subarea_sistemas_de_informacao.pdf` | 2 | 2 | 0 | 0 | Importado; quantidade baixa, conferir contra o PDF |
| `lote_2026_08_22/analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf` | 29 | 29 | 0 | 0 | Importado |
| `lote_2026_08_22/analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf` | 40 | 32 | 8 | 0 | Importado; revisar 8 médias |
| `lote_2026_08_22/auditor_fiscal.pdf` | 30 | 30 | 0 | 0 | Importado |
| `lote_2026_08_22/prova1_auditor_fiscal.pdf` | 46 | 42 | 4 | 0 | Importado; revisar 4 médias |
| `lote_2026_08_22/provas_2e3_auditor_fiscal.pdf` | 66 | 62 | 4 | 0 | Importado; revisar 4 médias |
| `TRANSPETRO.pdf` | 70 | 70 | 0 | 0 | 67 gabaritos vinculados; revisar divergências de numeração |

## O que foi reconhecido no banco

### Bancas

| Banca | Questões |
|---|---:|
| FGV | 314 |
| CESPE/CEBRASPE | 100 |
| IBFC | 83 |
| Objetiva | 55 |
| FEPESE | 51 |
| Avança SP | 40 |
| FUNDATEC | 30 |
| Não identificada | 306 |

O número baixo de bancas não significa que os PDFs não foram importados. Significa que o parser só preenche `banca` quando encontra uma marca textual reconhecível no conteúdo extraído. Muitos arquivos têm a banca somente no nome do arquivo ou em uma capa que não foi associada à questão.

### Disciplinas

Foram reconhecidas 14 categorias de disciplina. 280 questões ficaram sem disciplina e precisam de classificação manual ou por lote. As maiores categorias foram:

| Disciplina | Questões |
|---|---:|
| Conhecimentos Específicos | 276 |
| Língua Inglesa | 115 |
| Língua Portuguesa | 101 |
| Auditoria | 62 |
| Informática | 53 |
| Legislação | 25 |
| Matemática | 19 |
| Raciocínio Lógico | 15 |

### Gabaritos

As associações automáticas agora são limitadas a cabeçalhos confirmados:

```text
TRANSPETRO: 70 questões / 70 respostas reconhecidas
FGV/NITTRANS: 75 questões / 75 respostas reconhecidas
ALESC/Analista de Sistemas: 79 questões / 79 respostas reconhecidas
DPE-MT/Analista de Sistemas: 43 questões / 43 respostas reconhecidas
Demais arquivos: 428 questões sem gabarito aplicado
```

Os demais PDFs de gabarito continuam pendentes porque reúnem vários cargos, têm páginas escaneadas ou não têm correspondência inequívoca com um caderno. O sistema agora aceita seleção por cargo/prova, mas só aplica associações confirmadas para não gravar respostas de outro cargo.

## O que não foi completamente resolvido

Não houve falha técnica de leitura, mas há três grupos que exigem atenção:

1. **Metadados de banca:** 306 questões ficaram sem banca.
2. **Classificação:** 280 questões ficaram sem disciplina.
3. **Quantidade suspeita:** três arquivos retornaram apenas 2 questões cada. Eles foram gravados, mas devem ser comparados manualmente com o PDF para saber se o documento realmente contém dois itens ou se o parser deixou questões de fora.

Além disso, 428 questões foram salvas sem gabarito porque os gabaritos correspondentes não foram vinculados nesta execução.

## Estado final do banco

Após a limpeza e reimportação:

```text
questoes:          979
alternativas:     4100
provas:              0
prova_questoes:      0
tentativas:          0
respostas:           0
revisao_espacada:    0
```

Isso é esperado: o script remove as provas, tentativas, respostas e revisões dependentes antes de recriar somente as questões dos samples.

## Próximas melhorias recomendadas

- Inferir banca pelo nome do arquivo com um campo de origem rastreável, sem misturar essa inferência com o texto da questão.
- Criar uma tabela/configuração de associação entre prova e PDF de gabarito.
- Gerar este relatório automaticamente pelo script de reimportação.
- Exibir na UI um resumo de questões sem banca, sem disciplina e sem gabarito antes de salvar.
- Criar testes de contagem esperada para cada sample conhecido.
