# Relatório de execução — confiabilidade máxima

Data: 26/10/2026
Repositório: `C:\Users\Felipe\Desktop\Banco-Questões`
Branch: `main`

## Objetivo e implementação

Implementar rastreabilidade de fontes, snapshots de versões, evidências e revisão humana separada para conteúdo e gabarito. A liberação de novas provas exige uma versão conferida e fonte íntegra. O legado foi migrado como pendente, sem certificar a extração histórica.

Áreas alteradas: modelos e migração SQLite; serviços de proveniência e repositório de questões; extração de gabaritos e parsing; importação, execução e revisão na UI; diagnóstico, simulação de reimportação, testes e documentação.

## Migração do banco original

O banco já estava modificado no início desta tarefa. Durante a inicialização de testes, o arquivo original recebeu índices inválidos de schema 5 enquanto ainda registrava schema 4. Não houve mudança nas contagens de registros. Isso foi detectado antes da migração definitiva e comunicado; os processos identificados do aplicativo e testes pendentes foram encerrados com autorização do usuário.

Backup SQLite criado imediatamente antes da migração e validado com contagens, `integrity_check`, `foreign_key_check` e teste de cópia/restauração:

`data/questoes.pre-migration-20261026-124424-120372-2c39d5.db`

O backup representa o estado encontrado antes da migração, incluindo os índices inválidos; não é uma cópia anterior à inicialização dos testes.

Resultado no banco original `data/questoes.db`:

- Schema 5; integridade `ok`; zero violações de chave estrangeira e zero índices inválidos.
- Contagens preexistentes preservadas: 1.385 questões, 4.545 alternativas, 23 provas cadastradas e seus 1.385 vínculos, 6 tentativas, 0 respostas e 4 registros de progresso.
- Criados 1.385 snapshots e 42 registros de fontes. Todos os snapshots legados estão com conteúdo `pendente` e gabarito `desconhecido`; nenhum recebeu aprovação humana.
- Composições e respostas históricas sem versão identificável permanecem sem vínculo de versão, evitando atribuir retroativamente conteúdo atual a tentativas antigas.

## Comparação do acervo

A simulação pós-migração analisou 23 PDFs e 1.385 questões propostas, comparando arquivos correspondentes por ordem candidata sem tratá-la como número oficial. As 1.385 comparações ficaram pendentes de conferência; seis tentativas aparecem relacionadas no relatório. Não foram aplicadas alterações de reimportação ao banco. A cobertura de extração de gabarito observada foi 86,28%; essa métrica não representa precisão.

Relatório detalhado: `reports/proposta_reimportacao_samples_20261026-125047-920843.json`. A reimportação permanece em proposta até as diferenças e os vínculos serem conferidos; nenhuma correção manual ou histórico foi sobrescrito.

## Validações e pendências

- Suíte executada: 204 aprovados, 1 ignorado. `compileall` passou. A suíte teve inicializações que tocaram a estrutura do banco original; por isso, o resultado verde não demonstra isolamento completo dos testes. A auditoria pós-migração do banco foi executada separadamente em leitura.
- `scripts/verificar_regressoes_perfis.py`: 21/23 referências preservadas. As duas diferenças são `samples/administrador-FGV.pdf` (80 questões) e `samples/agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf` (50). Em ambas, a saída atual é igual à saída do parser de `HEAD`, embora o hash do manifesto não corresponda. Os manifests não foram alterados para mascarar a divergência.
- Diagnóstico pós-migração: `reports/diagnostico_confiabilidade_pos_migracao.md` e `.json`; 1.385 questões, 1.385 vínculos de prova cadastrada e zero revisões humanas.
- Revisão humana do acervo e conferência das 1.385 propostas permanecem pendentes. O legado continua bloqueado para novas provas até a revisão correspondente.
- Nenhum commit, push, merge ou pull request foi criado.
