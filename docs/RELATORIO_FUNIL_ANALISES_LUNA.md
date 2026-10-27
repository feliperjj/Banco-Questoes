# Relatório de execução — evolução do funil de análises

Data: 26/10/2026
Repositório: `C:\Users\Felipe\Desktop\Banco-Questões`
Branch: `main` (inicialmente alinhada a `origin/main`)
Entrega local. Sem commit, push, merge ou PR.

## Matriz de aceite A0–A8

| ID | Estado | Implementação e evidência | Resultado / limite real |
|---|---|---|---|
| A0 | Validado | `src/config.py`, `src/db/database.py`, `tests/conftest.py`, `tests/sitecustomize.py`; `tests/test_database_paths.py` confirma recusa do banco original e subprocesso isolado. Suíte executada com `-p no:tmpdir`; banco real aberto em `mode=ro` para o diagnóstico. `Get-Process` não encontrou processo Python/aplicação ativo antes da migração. | Fingerprint lógico antes da migração: `b87dbe1232b8db9049c5d4e0e61ebe5dc6d0cce3a608a6ea4fe70ebfa5b2dbc5`. Nenhuma alteração lógica do acervo durante testes. Diretórios temporários do pytest ficam dentro do projeto e são ignorados pelo Git. |
| A1 | Validado | `validacao.py`, `parser.py`, `diagnostico.py`, `importacao.py`, `ImportacaoSession` e `reimportar_samples.py` separam número explícito de `ordem_visual`; associação exige número e escopo inequívocos. `tests/test_validacao.py`, `tests/test_extrator.py` e `tests/test_lacunas_importacao.py`. Busca global não encontrou fallback remanescente de gabarito por ordem. | Questões sem marcador ficam sem número oficial; a posição visual é só localizador. Não foi alterado o manifesto de perfis para esconder divergências. |
| A2 | Validado | `provenance_service.py`, modelos e migrações; validação de parte, IDs exatos, versão, escopo, hash, página, região, dimensões e rotação. `tests/test_provenance.py` cobre fonte alterada, parte errada, ID inexistente, página inválida, região e decisões independentes. UI usa dimensões/rotação da página PDF original. | DOCX exige `paragraph:N`/`table:N`; paginação não é declarada estável. Snapshot antigo sem hash de imagem é preservado e apresentado como integridade desconhecida, não falsamente como adulterado. |
| A3 | Validado | `assess_version` é a política estruturada; `version_is_eligible` é adaptador. Repositório, geração/início de prova e nova tela de análise consomem essa regra. Avaliação é somente leitura, retorna todos os motivos, severidade, etapa e ação. | Alternativa longa legítima não bloqueia por comprimento; erro objetivo não pode ser dispensado como alerta. Fórmulas/tabelas sem sinal verificável continuam exigindo evidência visual em vez de heurística inventada. |
| A4 | Validado com limite | Snapshots e evidências idempotentes; serviço recusa versão desatualizada; a tela recupera versão selecionável, vínculos, páginas, regiões, justificativas e estado. Versões históricas ficam em somente leitura. Revisões repetidas idênticas não duplicam registros. `test_attempt_uses_immutable_question_version_after_later_edit` cobre importação de teste, pendência inicial, aprovação sintética, geração/início, progresso, edição e nota calculada pelo snapshot usado. | Falhas de migração e staging têm rollback transacional; não há teste de interrupção de processo Qt no meio de uma decisão. |
| A5 | Validado com limites | `questoes.py` oferece filtros por fonte/identidade, numeração, estrutura/visual, alertas, conteúdo, gabarito e liberação. A avaliação é agendada em pequenos passos do loop Qt; tabela mostra códigos de motivo. A ação abre o diálogo de original, evidência, decisões e resolução de suspeitas. `tests/test_ui_regressions.py` verifica fila e layout em 960×640 e 1240×800. | Originais e extração ficam em abas, sem overlay/diff visual; não há agrupamento de itens por documento/página/contexto nem revisão em lote. A captura visual manual de PDFs longos não foi realizada. |
| A6 | Validado em inventário e execução | `diagnosticar_confiabilidade.py` agrega o avaliador de domínio em conexão somente leitura e informa denominador, etapas e motivos sobrepostos. Cache de hash existe apenas dentro de uma execução; ações críticas revalidam a fonte. JSON e Markdown atuais foram gerados em `reports/diagnostico_confiabilidade_luna_20261026_final.*`. | 1.385 versões avaliadas; 0 liberadas e 1.385 pendentes. Etapa principal: numeração em 1.385. Motivos sobrepostos: conteúdo não conferido 1.385, gabarito não confirmado 1.385, numeração ausente 1.385, integridade visual desconhecida 47. Sem estimativa de precisão/acurácia. O inventário atual ainda tem zero evidências ligadas. |
| A7 | Validado para migração, staging e caminho de aplicação | `init_db` agrupa criação/migração em transação. Backup API consistente e cópia de restauração verificadas antes da migração schema 5→7. `reimportacao_staging.py`, `reimportar_samples.py --stage` e `gerenciar_staging_reimportacao.py` persistem, decidem e aplicam propostas aprovadas. Aplicação revalida hash, vínculo prova/questão e snapshot atual; backup, alteração e novo snapshot são transacionais, com retry idempotente. Teste sintético comprovou preservação da versão e backup. Duas execuções completas: 1.385 propostas novas na primeira; 0 novas na segunda. | As 1.385 propostas reais continuam pendentes e nenhuma foi aplicada sem revisão humana. A ordem é candidata, não identidade certificada. Staging final em `reports/reimportacao_staging_v2.sqlite3`; a proposta detalhada está no JSON de reimportação mais recente. |
| A8 | Validado com divergência de referência registrada | `compileall` sem erros; suíte completa atual: **219 passed, 1 skipped**. Teste ignorado: `tests/test_cebraspe_2025.py:86`, PDF local fornecido pelo usuário indisponível nessa execução. Caminho integrado de importação sintética até tentativa/histórico exercitado nos testes de proveniência e UI. | `scripts/verificar_regressoes_perfis.py` terminou em **0/23 hashes preservados**, embora a quantidade extraída tenha coincidido em todos os 23 arquivos. Comparação com o parser de `HEAD`, sob as dependências/perfis locais atuais, também preservou 0/23; 3 PDFs diferem entre o parser atual e HEAD por remoção do sufixo de cabeçalho “Conhecimentos Básicos/Gerais” do enunciado. O relatório histórico `RELATORIO_EXECUCAO_CONFIABILIDADE_2026-10-26.md` registra 21/23, resultado que não foi reproduzido nesta auditoria; não foi possível reconciliar os dois resultados. Os outros hashes da referência também não foram reproduzidos por HEAD. Nenhum manifesto foi atualizado. |

## Migração e integridade do banco real

Backup criado antes da mudança estrutural:

`data/questoes.pre-migration-20261026-134426-612751-823df8.db`

O método `backup_before_structural_change` validou `integrity_check`, chaves estrangeiras, contagens e cópia restaurada. Após a migração, schema 7, `integrity_check=ok`, zero violações FK. Contagens: 1.385 questões, 4.545 alternativas, 23 provas cadastradas, 1.385 vínculos no catálogo (`prova_cadastrada_questoes`), 1.385 versões, 42 fontes, 6 tentativas, 400 posições em provas de tentativa (`prova_questoes`) e 4 progressos. Comparação linha a linha dos dados das tabelas históricas comuns ao backup não encontrou diferenças; alterações se limitaram à versão de schema, coluna de escopo de evidência com padrão vazio e nova tabela vazia de resoluções.

Fingerprint lógico atual após migração e suíte: `ad5f3a786c8d4c233802412adeb09ca639cdfeb9086c0d8ec72faf8cdd6ab7dc`. O arquivo principal foi verificado em leitura depois da suíte; somente a migração estrutural prevista alterou o banco real. Não foram reimportados itens no acervo.

Auditoria final independente em conexão SQLite somente leitura: `integrity_check=ok`, zero violações FK; SHA-256 do arquivo atual `261ece62de2aec6389bbc5f582728e189cabeaedd60c7987fac75de93bb6caeb`. O inventário distingue os 1.385 vínculos de catálogo dos 400 vínculos de tentativa.

## Comandos e resultados

- `venv\Scripts\python.exe -m compileall -q src scripts tests` — passou.
- `venv\Scripts\python.exe -m pytest -q -rs -p no:cacheprovider -p no:tmpdir tests` — 219 aprovados, 1 ignorado (PDF local ausente).
- `venv\Scripts\python.exe scripts/diagnosticar_confiabilidade.py --saida reports/diagnostico_confiabilidade_luna_20261026_final` — somente leitura; 1.385 questões/vínculos; nenhuma revisão humana registrada.
- `venv\Scripts\python.exe scripts/reimportar_samples.py --stage` — executado duas vezes; 23 arquivos e 1.385 questões em cada execução; staging idempotente, banco do acervo não alterado.
- `venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -p no:tmpdir tests/test_reimportacao_staging.py` — 3 aprovados; inclui aprovação sintética, backup, nova versão pendente, preservação histórica e reexecução idempotente.
- `venv\Scripts\python.exe scripts/verificar_regressoes_perfis.py` — divergência de referência: 0/23 hashes; quantidades coincidem; manifesto preservado.

## Pendências humanas e limitações

- **1.385 versões** precisam de identificação numérica explícita no original, conferência de conteúdo e decisão de gabarito. Esses motivos se sobrepõem e não devem ser somados como itens distintos.
- **47 recursos visuais** referenciados por versões legadas não têm hash histórico; sua integridade precisa ser verificada contra o documento original.
- **1.385 propostas de reimportação** aguardam revisão; nenhuma está certificada ou aplicada.
- As três diferenças de parser listadas em A8 são observáveis no diff de conteúdo. A divergência entre a execução atual (0/23) e o relatório histórico (21/23) permanece sem explicação, apesar do manifesto não ter sido alterado. As outras divergências do manifesto já ocorrem ao executar o parser de `HEAD` com o estado local atual de perfis/dependências. Não há base para atualizar as referências automaticamente.
- A revisão de contexto longo, diagramas, tabelas e fidelidade de OCR permanece humana. O sistema não promete precisão total.

## Conferência visual complementar da Transpetro

A pedido do usuário, as 70 questões da Transpetro foram confrontadas com os números impressos e o conteúdo dos PDFs, por leitura independente do parser de produção e inspeção visual das páginas 2–15, capa e imagens vinculadas. Resultado: 13 com falha material, 2 com destaque importante perdido, 27 com ruído e 28 sem divergência material observada. Os 70 gabaritos coincidem com o arquivo local fornecido no escopo Prova 1/Administração; isso não verifica a publicação definitiva. Um dos quatro recortes está errado: Q68 usa exatamente a imagem de Q70. A capa identifica CESGRANRIO, apesar do rótulo FGV no catálogo.

O registro por questão está em `docs/AUDITORIA_VISUAL_TRANSPETRO_2026-10-26.md`. Essa medida de fidelidade é diferente de revisão formal: zero liberadas não significa zero questões corretas. A inspeção não mudou dados nem registrou aprovações. Banco real após a conferência: mesmo SHA-256 de arquivo `261ece62de2aec6389bbc5f582728e189cabeaedd60c7987fac75de93bb6caeb`, integridade OK, zero erros FK, 1.385 questões e 6 tentativas.

A investigação também corrigiu a tela de provas importadas: o total não liberado era indevidamente rotulado como “sem gabarito”. Agora os totais de gabarito salvo, ausência de gabarito e liberação são distintos. **Ver questões** abre consulta navegável sem tentativa ou alteração de respostas, inclusive quando a prova ainda aguarda revisão. Fazer prova continua protegido pelas regras do domínio. Testes focados de consulta, repositório e UI: **20 aprovados**; a suíte completa anteriormente registrada não foi repetida nesta correção.

## Estado de entrega

Alterações locais em código, testes, README, `docs/PROJECT_BRAIN.md` e este relatório; working tree preexistente preservado. O banco real recebeu apenas a migração documentada. Arquivos diagnósticos/staging em `reports/` são saídas locais ignoradas pelo Git. Não houve commit, push ou PR.
