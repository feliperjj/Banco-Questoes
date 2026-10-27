# Plano de ação — evolução completa do funil de análises

Data: 26/10/2026. Destinatário: GPT-5.6 Luna. Projeto: Banco-Questões.

## 1. Ordem expressa ao executor: complete a entrega

**Execute este plano de ponta a ponta. Não encerre a tarefa depois de analisar, editar alguns arquivos, criar um serviço, apresentar um protótipo ou obter testes verdes. A entrega inclui integração nas telas e nos caminhos reais, validação isolada, auditoria do acervo e relatório verificável.**

O trabalho só termina quando todos os critérios técnicos deste plano estiverem atendidos e comprovados. Enquanto houver uma ação necessária, autorizada e executável, continue trabalhando. Não entregue como instrução ao usuário uma etapa que você ainda consegue executar. Não peça confirmação entre etapas nem ofereça continuar depois: a execução completa já é o objetivo.

Antes de começar, crie uma lista de acompanhamento com os IDs de aceite deste documento. Para cada item, registre: estado, arquivos envolvidos, evidência executada, resultado e pendência real. Atualize-a durante o trabalho. Uma marcação sem evidência não comprova conclusão. Faça checkpoints de progresso sem encerrar a tarefa.

Conferência humana de conteúdo é uma pendência externa legítima. Implementação ausente, teste não executado, tela desconectada, script apenas em simulação ou ambiente de teste sem isolamento são trabalho técnico incompleto. Não use a pendência humana para encerrar essas partes antes da hora.

Se encontrar uma falha, investigue e corrija; tente uma alternativa segura e materialmente diferente quando a primeira abordagem não funcionar. Só pare por falta indispensável de acesso, informação, autorização ou capacidade técnica, depois de esgotar o trabalho independente. Identifique a causa concreta, a evidência, as tentativas e a menor ação que desbloqueia. Não declare bloqueio por dificuldade, duração ou volume de arquivos.

## 2. Objetivo, escopo e entrega

Construir um funil explicável que encaminhe cada questão para a análise necessária e impeça liberação por suposição. Fluxo esperado:

Fonte identificada → extração rastreável → análise de numeração, estrutura, contexto e recursos → associação de gabarito → conferências independentes de conteúdo e gabarito → liberação.

As conferências de conteúdo e gabarito são dimensões independentes. Uma etapa principal organiza a fila, mas não apaga as demais pendências da questão. O motor deve informar todos os motivos encontrados, inclusive quando já existe um bloqueio anterior.

Entregáveis obrigatórios: código local integrado; migrações necessárias testadas; fila de revisão utilizável; retomada persistente; testes reproduzíveis e isolados; diagnóstico JSON/Markdown do acervo real; relatório de implementação, limitações e revisão humana restante. Não incluir redesign cosmético amplo, serviços externos, IA gerando conteúdo ou alteração de pontuação.

Este plano complementa docs/PLANO_CONFIABILIDADE_MAXIMA.md. Corrigir e integrar o que já existe; não recomeçar a arquitetura inteira. A entrega é local. **Não criar, abrir ou solicitar PR; não fazer commit, push, merge, rebase, force push ou descarte de mudanças.**

## 3. Contexto e preparação obrigatória

Leia integralmente as instruções aplicáveis e estes documentos antes de editar:

- README.md e docs/PROJECT_BRAIN.md.
- docs/IMPORTACAO_HIBRIDA.md e docs/AUDITORIA_PROVAS_MANUAL.md.
- docs/PLANO_CONFIABILIDADE_MAXIMA.md.
- docs/RELATORIO_EXECUCAO_CONFIABILIDADE_2026-10-26.md e este plano.

Reinspecione branch, working tree e arquivos modificados. No último levantamento, a branch era main e havia diversas alterações locais desta implementação, além de documentos não versionados. Preserve integralmente essas mudanças e as alterações do usuário. Não trate HEAD como se fosse a implementação atual, nem substitua arquivos para limpar o diff.

O último estado verificado do banco era schema 5, com 1.385 questões, 4.545 alternativas, 23 provas cadastradas, 1.385 vínculos de catálogo, 6 tentativas, 4 progressos, 1.385 snapshots pendentes e 42 fontes. Esses números são referência histórica; obtenha um inventário atual em leitura antes de trabalhar.

Houve um incidente na execução anterior: inicializações de testes tocaram o banco original e criaram índices inválidos antes da migração. A migração corrigiu esses índices, mas o incidente prova que a suíte anterior não estava completamente isolada. Os 204 testes aprovados e 1 ignorado são evidência anterior, não substituem a validação deste plano.

O backup data/questoes.pre-migration-20261026-124424-120372-2c39d5.db foi validado, mas contém o estado schema 4 anterior à migração, inclusive os índices inválidos. Preserve-o. Não o trate como banco limpo nem o restaure sobre o atual.

## 4. Etapa 0 — isolar testes e estabelecer a referência

Áreas: src/config.py, src/db/database.py, tests/conftest.py, testes e processos auxiliares.

1. Disponibilize configuração explícita de banco e diretórios de trabalho para testes, carregada antes de importar módulos que inicializam conexão ou UI. Testes e subprocessos devem usar caminhos temporários distintos do acervo.
2. Impeça fallback silencioso para data/questoes.db dentro da execução de testes. Inclua uma proteção verificável que rejeite conexão de escrita ao original nesse contexto. Evite efeitos colaterais de importação que abram ou migrem o banco real.
3. Isole também imagens, logs, checkpoints e documentos gerados. Todos devem ir para diretórios de teste; não substituir recursos referenciados pelo acervo.
4. Garanta encerramento dos processos Qt/pytest e conexões, inclusive em falhas. Identifique processos por comando, caminho e contexto antes de encerrá-los; não finalize processos apenas pelo nome python ou por proximidade de horário.
5. Resolva o uso do diretório temporário de forma reproduzível. A validação final não pode depender de reports.pytest_no_tmp_cleanup ou de outro helper ignorado e ausente da entrega. Se precisar de infraestrutura auxiliar, incorpore-a de forma documentada ao projeto.
6. Registre o inventário atual, integridade e fingerprint lógico do acervo em leitura. Quando houver WAL ou aplicativo ativo, use snapshot SQLite consistente; hash apenas do arquivo principal não demonstra ausência de mudança lógica.
7. Análises e diagnósticos em leitura não devem chamar init_db ou disparar create_tables/migração implicitamente.

**Aceite A0:** teste que tenta atingir o original é recusado; suíte e subprocessos utilizam bancos temporários; interrupção não deixa processo de teste ativo; acervo e recursos reais permanecem logicamente iguais após a execução de testes.

## 5. Etapa 1 — numeração explícita e associação segura

Áreas: src/importador/validacao.py, diagnostico.py, parser.py, perfis, importação e scripts.

1. Remova o uso do índice ou da ordem como substituto do número oficial em associar_gabaritos, diagnosticar_caderno e todos os demais caminhos equivalentes. Procure o padrão em todo o repositório.
2. Separe ID interno, ordem visual e número explicitamente extraído. Registre a origem do número, documento e localização. Nome de arquivo, posição e quantidade esperada não certificam numeração.
3. Valide números ausentes, inválidos, duplicados e ambíguos. A unicidade é relativa à prova/cargo/código/versão pertinentes: um PDF com vários cargos pode repetir números legitimamente.
4. Associe gabarito somente por correspondência inequívoca de escopo e número. Questão omitida no meio não pode deslocar as seguintes. Ausência de número gera diagnóstico com localização pela ordem, sem preencher o número.
5. Preserve e exponha os motivos numeracao_ausente, numeracao_ambigua, numeros_duplicados e escopo_divergente. Não descarte motivos desconhecidos silenciosamente por whitelist.

**Aceite A1:** números 1 e 3 não recebem respostas de 1 e 2 por posição; itens sem número não são associados; duplicidade no mesmo escopo bloqueia; repetição entre escopos corretamente identificados permanece válida; nenhum outro ponto de entrada reintroduz fallback posicional.

## 6. Etapa 2 — evidência da parte e da prova corretas

Áreas: src/models/provenance_service.py, src/db/models.py, migrações e diálogo de revisão.

1. Defina vocabulário de partes de evidência e valide-o no domínio. Aprovação de conteúdo exige evidência de conteúdo; confirmação de gabarito exige evidência de gabarito. A UI não pode ser a única proteção.
2. Confira que todos os IDs solicitados existem, pertencem à versão exata e à finalidade esperada. Não aceitar apenas o subconjunto de IDs encontrado pelo SELECT. Rejeitar referências de outra questão, versão ou parte com mensagem clara.
3. Verifique fonte acessível, hash íntegro, página existente, coordenadas finitas e não degeneradas, dimensões, rotação e sistema de coordenadas. Para DOCX, valide identificador de parágrafo/tabela e explicite a limitação de paginação.
4. Faça a identidade da prova, cargo, código, versão e situação do gabarito integrar a associação e a decisão. Conflito conhecido bloqueia. Informação ausente exige identificação explícita com evidência; não inferir certeza do nome do arquivo nem considerar desconhecido como compatível.
5. Um documento pode conter vários cargos, versões ou tipos de parte. Modele o escopo no vínculo/registro pertinente, sem atribuir um único cargo a todo PDF misto. O mesmo arquivo físico pode ser fonte de partes diferentes: exija regiões e finalidades adequadas, não arquivos obrigatoriamente distintos.
6. Registre decisão, responsável declarado, data, versão, escopo, evidências e justificativa. Gabarito preliminar, definitivo, conflitante e anulado devem ter tratamentos distintos. Não converter preliminar em definitivo por haver uma resposta armazenada.
7. Valide imagens e derivados: origem, limites, disponibilidade e integridade do recurso efetivamente exibido. Arquivo de gabarito e região com resposta não podem ser mostrados na execução da prova.

**Aceite A2:** chamadas diretas ao serviço não aprovam conteúdo usando só gabarito, nem gabarito usando só conteúdo; ID inexistente não é ignorado; cargo/versão divergentes e fonte alterada são recusados; evidência legítima de documento misto pode ser registrada com seu escopo; regiões e recursos inválidos são diagnosticados.

## 7. Etapa 3 — diagnóstico estruturado e política única de liberação

Áreas: validacao.py, provenance_service.py, questoes_repo.py e consumidores.

1. Substitua a decisão opaca por uma avaliação estruturada. Cada diagnóstico deve conter código estável, etapa, severidade, natureza objetiva/suspeita, mensagem, parte/localização, evidência disponível e ação necessária.
2. Retorne, no mínimo: versão avaliada, liberada, etapa principal, todas as pendências, bloqueios objetivos, alertas, decisões humanas necessárias e estados de conteúdo/gabarito. Ausência de análise significa não verificado, nunca aprovado.
3. Diferencie impedimentos comprovados, como enunciado vazio ou alternativa do gabarito ausente, de sinais heurísticos, como alternativa longa, possível fusão ou possível fórmula degradada. Comprimento ou uma palavra isolada não justificam cortar conteúdo nem rejeitar definitivamente.
4. Suspeitas podem ser resolvidas por pessoa com evidência e justificativa vinculadas ao código, à versão e à execução da regra. Registre a resolução; não apenas esconda o aviso. Nova versão, nova evidência relevante ou mudança da regra que invalide a análise exige reavaliação. Bloqueio objetivo não pode ser dispensado por justificativa genérica.
5. Mantenha uma única política de liberação no domínio, consumida por UI, scripts, geração aleatória, provas importadas, criação e início de tentativa. O helper booleano pode permanecer como adaptador do resultado completo; não manter uma segunda implementação de regras.
6. Diferencie a elegibilidade de uma versão para novo uso da consulta/retomada de uma tentativa já iniciada. Preservar snapshot, respostas e notas históricos; sinalizar problemas sem trocar conteúdo ou finalizar automaticamente.
7. Mostrar todos os motivos e a próxima ação sem transformar um score agregado ou o campo confianca em aprovação. Concordância entre extratores é sinal técnico, não conferência humana.

**Aceite A3:** todos os caminhos retornam decisões coerentes; resultado explica cada impedimento; suspeita revisada não fica eternamente bloqueada; erro objetivo continua bloqueando; análise não gera aprovação nem altera histórico. Incluir contraprovas com alternativas longas legítimas, números em alternativas e fórmulas/tabelas.

## 8. Etapa 4 — retomada persistente e versões preservadas

Áreas: src/ui/components/question_source_review.py, serviços e persistência de revisão.

1. Ao abrir a questão, carregue do banco a versão selecionada, fontes, evidências por parte, páginas/regiões, decisões e resoluções existentes. As listas em memória não são a fonte definitiva.
2. Reabrir, navegar, visualizar ou salvar o mesmo estado não pode gerar nova versão nem duplicar evidência. Use operações idempotentes e restrições transacionais adequadas.
3. Mudança real de conteúdo, resposta, fonte ou conjunto de evidências deve produzir a revisão/versionamento apropriados sem modificar o material já usado. Preserve as versões anteriores e invalide as aprovações necessárias da nova versão; não copie aprovação por conveniência.
4. Defina explicitamente a fronteira entre rascunho de evidência e versão aprovada. Completar um rascunho pendente não precisa multiplicar snapshots a cada clique. Alterar uma versão aprovada exige nova revisão/versionamento, preservando sua trilha anterior.
5. Mostre o snapshot exato que será conferido, e não campos atuais que possam divergir dele. Recuperar estado não pode marcar conferência nem reaplicar justificativa antiga a uma nova decisão.
6. Trate duas janelas abertas para a mesma questão: detectar versão desatualizada e impedir salvar/aprovar contra outro estado silenciosamente. Falhas devem fazer rollback e manter um estado coerente recuperável.

**Aceite A4:** registrar evidências → fechar → abrir recupera os mesmos vínculos; repetir abertura/salvamento não duplica; edição relevante cria a revisão necessária; versão usada em tentativa permanece igual; conflito entre janelas é informado; falha intermediária não deixa aprovação parcial incoerente.

## 9. Etapa 5 — fila de análise e revisão assistida

Áreas: telas de importação/acervo/revisão, repositórios e apresentação da avaliação.

1. Integre a avaliação à UI. Exiba etapa principal, motivo específico, gravidade, estado de conteúdo/gabarito e ação necessária. Não deixar um serviço novo sem consumidor real.
2. Crie filtros úteis: fonte/identidade pendente, problema de extração, numeração, contexto, imagem/fórmula/tabela, revisão de conteúdo, confirmação de gabarito, conflito, rejeitada e liberada. Mantenha acessíveis as demais pendências quando um item aparece em uma etapa principal.
3. Priorize deterministicamente: fonte alterada e conflito de identidade; falhas objetivas; contexto/visual de maior risco; suspeitas; questões estruturalmente prontas para conferência. A prioridade organiza trabalho, não altera elegibilidade.
4. Agrupe por documento, página, perfil e contexto compartilhado para reduzir repetição. Revisar um grupo não pode aprovar automaticamente cada questão; uma evidência compartilhada só se aplica aos vínculos e ao escopo registrados.
5. Abra automaticamente o original na página/região pertinente e mostre o extraído ao lado, com zoom, navegação multipágina, diferenças e alertas. Permita corrigir conteúdo, limites e contexto pelo fluxo versionado. Ofereça ações separadas para conteúdo e gabarito e resolução explícita dos alertas.
6. Permita interromper e retomar a fila preservando posição e filtros. Sem evidência suficiente, a ação é manter pendente com motivo registrado. Salvar, navegar e terminar extração não aprovam questões.
7. Em 960×640 e 1240×800, verifique conteúdo longo, texto-base multipágina, tabela, fórmula, imagens e todas as alternativas. Usar abas/adaptação quando necessário; não esconder partes essenciais.

**Aceite A5:** da fila é possível localizar a causa, abrir sua origem, corrigir ou registrar a decisão, fechar, retomar e ver o estágio atualizado. A pessoa não precisa reabrir o mesmo PDF manualmente para cada item. Questão somente é liberada quando todas as exigências forem satisfeitas.

## 10. Etapa 6 — métricas, desempenho e análise incremental

1. Mostre contagens por etapa e motivo, fontes rastreáveis, conteúdo conferido, gabarito confirmado, itens liberados e pendências humanas. Contagem por etapa principal deve fechar com o universo; contagens por motivo podem se sobrepor e devem ser identificadas assim.
2. Separe questões, versões, documentos e propostas para não inflar números. Registre o denominador e a execução de origem. Taxa de extração/associação não deve ser chamada de precisão.
3. Registre erros confirmados e alertas descartados pela pessoa para permitir medir utilidade das regras. Estimativa de acurácia exige referência independente, amostra e método declarados; métricas inexistentes ficam indisponíveis.
4. Faça consultas em lote e reutilize o hash do mesmo documento dentro de uma execução consistente, evitando reler o PDF para cada questão. Cache persistente não pode esconder mudança de arquivo: revalide a fonte nas operações críticas de aprovação e início de tentativa.
5. Mantenha a UI responsiva durante análise longa, com progresso, cancelamento seguro e resultados identificados pela versão. Respeite conexões de banco por thread; resultado antigo não pode atualizar uma versão mais recente.
6. Reanalise os itens afetados por edição, nova fonte, novo gabarito ou atualização de regra. Registre versão das regras e parâmetros para reproduzir o diagnóstico.

**Aceite A6:** totais reconciliados; métricas não confundem cobertura com fidelidade; fonte alterada continua detectável; mesma análise sobre mesmo estado é estável; fila não recalcula repetidamente o mesmo arquivo nem congela em operação longa.

## 11. Etapa 7 — acervo real, migrações e aplicação controlada

A autorização existente permite usar o banco original e executar reimportações de teste com backup prévio consistente e verificado. Não pedir novamente essa autorização dentro deste escopo. Ela não autoriza descartar histórico, correções manuais ou documentos.

1. Primeiro valide as mudanças em banco temporário novo e em cópia consistente do legado. Se houver nova migração, englobe criação de tabelas, índices e alterações numa transação coerente; uma falha entre create_tables e apply_migrations não pode deixar schema parcialmente atualizado.
2. Antes de nova mutação do original, assegure ausência de gravações concorrentes, crie backup SQLite via API com WAL contemplado, valide integridade/FKs/contagens e teste restauração em cópia. Preserve arquivos associados que possam ser alterados. Registre o novo caminho; mantenha os backups anteriores.
3. Rode o novo diagnóstico no acervo real em leitura e reconcilie todos os itens com as filas e métricas. Regenere a proposta de reimportação mostrando versão anterior/proposta, diferença por campo, origem, motivo, conflitos e tentativas afetadas.
4. Complete e teste o caminho de aplicação controlada previsto no plano anterior. Se correspondência e preservação forem comprovadas, grave novas propostas/versões pendentes transacionalmente, com idempotência, preservando IDs, composições e histórico. Não encerrar esta parte apenas porque existe um script de simulação.
5. Correspondência somente por ordem é candidata; não a promova a identidade certificada. Quando o legado não permitir vínculo inequívoco, mantenha propostas em staging identificado, sem sobrescrever a questão. A ambiguidade exige decisão humana, mas a criação e a validação técnica desse staging continuam sendo trabalho do executor.
6. Execute duas vezes em banco de teste para comprovar que não duplica questões, versões, fontes ou propostas. Simule interrupção e rollback. Só depois aplique ao original as operações seguras e autorizadas; itens ambíguos permanecem identificados para conferência.
7. Compare contagens e conteúdo das tabelas históricas, alternativas, contextos, recursos e tentativas antes/depois. Contagens iguais sozinhas não provam preservação. Use fingerprints lógicos/campos pertinentes, permitindo apenas mudanças explicitamente esperadas da migração.
8. Não restaurar um backup sobre alterações mais recentes para resolver falha automaticamente. Preserve o estado e informe o conflito se a recuperação exigir sobrescrita.

**Aceite A7:** acervo real analisado com métricas reconciliadas; aplicação/staging integrado e validado; segunda execução idempotente; falhas não geram estado parcial; histórico e correções anteriores comprovadamente preservados; nenhuma proposta é registrada como conferida por humano.

## 12. Etapa 8 — validação ponta a ponta e auditoria de conclusão

Execute os testes necessários em isolamento e registre resultados atuais. Mantenha dados de teste explicitamente sintéticos; responsáveis usados nos testes não podem aparecer como pessoas que revisaram o acervo real.

Cobertura mínima obrigatória:

- Numeração ausente, inválida, repetida, questão faltante no meio e múltiplos cargos/versões.
- IDs de evidência inexistentes, finalidade errada, outra versão/questão, fonte ausente/alterada, região inválida e recurso visual ausente/alterado.
- Gabarito preliminar, definitivo, anulado e conflitante; metadados ausentes e divergentes.
- Suspeita legítima resolvida com evidência e justificativa; erro objetivo não dispensável; mudança de regra/versão invalidando resolução quando necessário.
- Retomada persistente, idempotência, concorrência entre janelas e rollback.
- Tentativa/histórico preservados após nova versão; proteção de respostas na apresentação do original.
- Migração nova/legada com falha intencional em diferentes pontos, backup/restauração e proteção do banco original durante testes.
- Caminho real integrado: importar → salvar pendente → diagnosticar → aparecer na fila → abrir fonte → corrigir/resolver alertas → conferir conteúdo e gabarito → liberar → gerar/iniciar → responder/salvar progresso → fechar/retomar → finalizar → consultar histórico → editar nova versão → confirmar histórico inalterado.

Execute a suíte completa, compileall e scripts/verificar_regressoes_perfis.py. O último verificador preservava 21/23 referências; as divergências de administrador-FGV.pdf e agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf também apareciam com o parser de HEAD. Reproduza e registre a referência atual. Não atribua toda falha nova ao problema antigo e não altere manifests apenas para obter resultado verde.

Faça uma segunda passagem de auditoria baseada no diff e no comportamento observado. Verifique que serviço, persistência, migração, telas, mensagens, documentos e scripts estão conectados. Inspecione processos restantes, banco e recursos reais, arquivos gerados e estado final do Git. Diferencie o que foi executado do que foi apenas inspecionado ou proposto.

**Aceite A8:** A0–A7 comprovados; fluxo integrado executado; verificações atuais registradas; divergências explicadas com evidência; diff e estado final reinspecionados; nenhuma pendência técnica executável escondida como trabalho humano.

## 13. Portão final obrigatório — não encerrar antes

Antes de responder como concluído, preencha a matriz A0–A8. Para cada critério informe evidência concreta e resultado. Se houver item técnico necessário ainda não feito e você puder executá-lo, **não envie resposta final: continue**.

É proibido declarar conclusão quando ocorrer qualquer uma destas situações:

- O serviço foi criado, mas a tela, a fila ou outro caminho ainda usa a regra antiga.
- Testes passam, mas a integração real não foi exercitada.
- O processo de teste continua ativo ou o banco original foi usado sem proteção.
- O executor deixou de executar uma validação pertinente e a tratou como aprovada.
- Apenas a simulação de reimportação existe, sem aplicação/staging seguro implementado e testado.
- Existe falha conhecida de identidade, evidência, numeração, integridade ou histórico.
- O relatório descreve ações planejadas como realizadas ou usa números antigos como atuais.
- Ainda é necessário pedir ao usuário uma ação técnica que o executor consegue realizar com o acesso e a autorização existentes.

Crie docs/RELATORIO_FUNIL_ANALISES_LUNA.md contendo a matriz de aceite, implementação por área, comandos/resultados, testes ignorados e justificativas, comparações do acervo, caminhos de backup, limitações reais e pendências humanas quantificadas. Atualize README e PROJECT_BRAIN para refletir o comportamento efetivamente entregue.

A resposta final deve começar com CONCLUÍDO, CONCLUÍDO COM PENDÊNCIA EXTERNA, BLOQUEADO ou REVISÃO/DIAGNÓSTICO CONCLUÍDO, conforme o resultado real. Para esta implementação, revisão/diagnóstico por si só não satisfaz a entrega. Use CONCLUÍDO COM PENDÊNCIA EXTERNA apenas quando o trabalho técnico estiver integrado e validado e restarem ações realmente externas, como a pessoa conferir o acervo. Informe qualquer impedimento técnico real com precisão; não use esse estado para encobrir implementação ausente.

Informe objetivo, principais decisões, arquivos/áreas alterados, evidências de validação, estado do banco, quantidade de pendências humanas e localização do relatório. Declare que não houve commit/push/PR. Não prometa precisão de 100%.

## 14. Prompt pronto para iniciar a execução

Luna, implemente integralmente docs/PLANO_ACAO_FUNIL_ANALISES_LUNA.md no Banco-Questões. Leia as fontes indicadas, preserve todo o working tree existente e comece pelo isolamento dos testes. Execute as etapas 0 a 8 sequencialmente, integrando domínio, persistência, UI, scripts e documentação. Mantenha a matriz A0–A8 com evidência concreta. O usuário já autorizou o uso do banco original e reimportações de teste com backup SQLite consistente e restauração verificada; não repita a solicitação dentro desse escopo. Preserve histórico e correções manuais; não certifique revisão humana. Não crie PR, commit ou push. Não pare depois de implementar parte das regras ou passar a suíte: conclua os caminhos reais, a retomada, a fila, a análise do acervo, a aplicação/staging seguro e a auditoria final. Se existir trabalho necessário, autorizado e executável, continue até terminá-lo. Só encerre com o entregável integrado e comprovado, ou com um bloqueio indispensável demonstrado e todo o trabalho independente concluído. Entregue o relatório exigido e diferencie claramente conclusão técnica de conferência humana pendente.
