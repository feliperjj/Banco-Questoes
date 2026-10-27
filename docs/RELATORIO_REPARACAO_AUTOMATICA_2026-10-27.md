# Reparação automática do acervo

Atualização: 27/10/2026. Este documento atualiza o estado histórico dos relatórios de 26/10.

## Resultado e limite da execução

O usuário autorizou a reparação em lote e a liberação dos itens que passarem na verificação automática contra a fonte. A última contagem conferida antes da interrupção foi de 1.068 questões reparadas e 913 liberadas, em um acervo de 1.385 questões. Cobertura de liberação não é uma estimativa estatística de precisão.

A Transpetro teve seus 70 itens reparados, incluindo o contexto em inglês, a notação da questão 41 e o recorte correto da questão 68. A banca foi corrigida para CESGRANRIO conforme a capa. A correspondência dos gabaritos refere-se ao PDF local fornecido, sem afirmar verificação independente de publicação definitiva.

A reconstrução experimental de 29 itens com novos IDs foi interrompida a pedido do usuário e não foi aplicada ao banco real. Após a interrupção, a conferência confirmou 1.385 registros, nenhum ID novo, integridade SQLite `ok` e zero violações de chave estrangeira. O código experimental de reconstrução não integra esta entrega.

## Comportamento entregue

- Schema 8 mantém certificados automáticos separados das decisões humanas, com hashes de fontes, versões, escopo, páginas, regiões e imagens.
- A apresentação usa fac-símiles do PDF para preservar fórmulas, destaques, tabelas e contexto. A verificação compara os pixels com as regiões originais.
- A associação exige número físico e identidade documental. A ordem de importação não substitui o número oficial nem escolhe o gabarito.
- Rejeições humanas do mesmo conteúdo não podem ser contornadas reaplicando um lote. Fontes alteradas e snapshots desatualizados bloqueiam a aplicação.
- Provas parciais oferecem **Resolver N verificadas**. O treino reavalia a elegibilidade no momento da criação, exclui os demais itens e identifica a composição parcial no nome e na configuração.
- Falta de gabarito, documento preliminar, anulação e conflitos permanecem motivos explícitos de indisponibilidade para nota.

## Preservação e verificação

As aplicações criam backups SQLite consistentes com teste de restauração. Os IDs anteriores, versões originais e tabelas de provas históricas, tentativas, respostas e progresso foram comparados antes e depois dos lotes aplicados. O lote em andamento foi interrompido em transação; a recuperação SQLite foi conferida em seguida.

Backups locais incluem `data/questoes.pre-reparacao-20261026-180209-22b020.db`, `data/questoes.pre-reparacao-20261027-091831-cd595c.db` e `data/questoes.pre-reparacao-20261027-092530-282b32.db`. Relatórios detalhados e cópias de teste ficam em `reports/`, fora do Git.

As validações focadas cobriram extração física de gabaritos e regiões, certificados e invalidação de fontes, rejeição humana, idempotência, preservação histórica e execução parcial. A interface foi renderizada em cópia para as questões 11, 41 e 68 da Transpetro; isso não substitui uma conferência da janela ativa do usuário.

Validação final da entrega: `venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --ignore=tests/test_reconstrucao_canonica.py` — **247 aprovados, 1 ignorado**. O teste experimental excluído não faz parte do commit. `git diff --cached --check` passou; a conferência dos arquivos preparados não encontrou credenciais, banco local ou arquivos da reconstrução interrompida.

O commit contém código, testes e documentação. O SQLite local, imagens derivadas, backups, relatórios operacionais e arquivos experimentais permanecem locais. Nenhum pull request será aberto.
