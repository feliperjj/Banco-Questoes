# Correção das lacunas e regressões de importação

Data: 07/09/2026.

## Validação final

- 23 cadernos extraídos novamente: **1.239 → 1.385 questões** (+146).
- Todas as 23 saídas têm sequência 1–N sem lacunas ou números repetidos.
- Nenhum problema apontado pelo validador estrutural atual nas saídas finais.
  Isso não equivale a uma revisão humana integral.
- Suíte completa: **164 testes aprovados**. Ajuste posterior do falso aviso em
  expressão lógica: **16 testes direcionados aprovados**.
- Resumo por arquivo: `reports/auditoria_lacunas.json`.
- Nova referência de conteúdo: `tests/fixtures/perfis_corrigidos_manifest.json`.
  As referências anteriores foram preservadas, incluindo seus defeitos conhecidos.

## Problemas investigados

A auditoria anterior contava registros, mas alguns registros tinham números
repetidos ou continham trechos da questão seguinte. Também havia textos-base
descartados e leitura de colunas como linhas corridas. Os arquivos apontados
como possivelmente parciais contêm as questões iniciais: nesse conjunto, elas
estavam sendo perdidas pelo importador.

## Correções do algoritmo

1. **Início do conteúdo:** a procura pela primeira questão após uma disciplina
   não termina mais em 12 linhas. Textos-base longos não fazem a importação
   começar na disciplina seguinte. Um título posterior não pode apagar questões
   que já apresentam alternativas.
2. **PDF e colunas:** letras grandes com transformação diagonal são removidas
   mesmo quando o leitor as classifica como `upright`. A detecção considera
   números com traço, alternativas recuadas e cabeçalhos nomeados nas duas
   margens. Palavras que atravessam o centro evitam cortar páginas de largura
   inteira. Rodapés identificados na margem inferior são removidos antes do
   recorte das colunas.
3. **Numeração isolada:** além dos candidatos anteriores, um perfil procura
   um caminho consecutivo entre os números realmente impressos. Presença de
   alternativas locais desempata números repetidos. Não cria questões para
   preencher lacunas. O resultado participa da validação contra o candidato geral.
4. **Itens C/E com ponto:** o leitor de recuos aceita `1.` e mantém o texto-base,
   o comando de julgamento e o item separados. Continua exigindo sequência
   válida e contexto de julgamento. Isso recupera os 120 itens do caderno IADES.
5. **Frações:** séries completas A–E no padrão vertical numerador/letra/
   denominador são reconstruídas como `1/2`, por exemplo. Um número isolado
   próximo de uma alternativa não aciona essa conversão.
6. **Listas dentro do enunciado:** quando existe uma lista interna e uma nova
   sequência completa de respostas iniciada em A, a lista interna permanece
   no enunciado. Isso preserva tabelas de associação e listas de tributos.
7. **Expressões lógicas:** letras maiúsculas de alternativas e variáveis
   minúsculas não formam uma sequência horizontal. `(a and not b)` permanece
   dentro da alternativa A.
8. **Texto compartilhado:** intervalos e pares explícitos de questões vinculam
   o texto às questões indicadas. Marcadores nomeados têm prioridade sobre
   números de linha do texto-base. O apoio seguinte é retirado da alternativa
   anterior antes da associação.

## Resultados verificados pelos testes de integração

| Caderno | Antes | Sequência oficial exigida |
|---|---:|---|
| IADES — análise/desenvolvimento de sistema | 57 registros, 55 números distintos | 1–120 |
| CRF — agente administrativo I (`i-3`) | 49 | 1–55 |
| Analista administrativo III | 79 | 1–80 |
| Analista de sistemas (IBFC) | 45 | 1–50 |
| Analista administrativo — desenvolvimento | 30 | 1–40 |
| Apoio especializado — desenvolvimento | 30 | 1–70 |
| Analista — produção/redes/suporte | 40 | 1–50 |
| Auditor fiscal (FUNDATEC) | 30 | 1–40 |
| Auditor fiscal — provas II e III | 69 | 1–70 |
| Auditor fiscal — prova I | 45 | 1–45, preservada |
| Transpetro | 70 registros, 68 números distintos | 1–70 |

`tests/test_lacunas_importacao.py` verifica essas sequências sem duplicatas e
inclui expectativas de conteúdo, como a mudança de texto-base nos itens 9/10
da IADES, os enunciados 48/70 da Transpetro e os valores das frações.

## Funcionamento do fluxo

O arquivo passa pelo leitor documental, pelo reconhecimento de formato e pela
segmentação. O parser monta enunciados, alternativas e metadados. A validação
aponta estrutura inválida, lacunas e duplicatas. O gabarito é selecionado pelo
contexto de cargo/prova e associado pelo número oficial, nunca pela posição
do registro na lista. A tela recebe rascunhos para revisão antes de salvar.

Os perfis e diagnósticos estão descritos em `IMPORTACAO_HIBRIDA.md`. A extração
é determinística, com OCR local opcional; a confiança alta/média/baixa é uma
heurística estrutural, não uma probabilidade de correção.

## Limites e persistência

Sequência completa e testes aprovados não certificam a fidelidade visual de
todas as questões. Imagens, diagramas, tabelas complexas e fórmulas fora do
padrão de frações tratado continuam sujeitos à conferência na fonte. Os avisos
de revisão permanecem; não foram suprimidos para aparentar completude.

Esta correção não executa o script que limpa e recria o banco, nem apaga provas,
tentativas ou edições manuais. Os registros previamente salvos não são
reescritos automaticamente pelo parser.
