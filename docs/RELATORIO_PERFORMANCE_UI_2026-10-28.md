# Correção de desempenho e leitura da prova — 28/10/2026

## Problema observado

A disponibilidade era recalculada de forma síncrona ao abrir o gerador e mudar filtros ou quantidade. A listagem de provas e a abertura de tentativas também verificavam fontes na thread da interface. A última abertura no log levou aproximadamente 36 segundos. Na cópia de 1.385 questões, a contagem instrumentada levou 43,33 segundos, com 22.403 consultas SQL.

O fac-símile era ampliado até a largura inteira da janela, dentro de uma área pequena, enquanto o cartão reservava espaço vazio abaixo das alternativas.

## Alterações

- Listas e contagens usam prefetch dos registros necessários, limitado a uma leitura. O snapshot é descartado ao terminar; não é um cache permanente de aprovações. Os arquivos e hashes continuam verificados. Geração e início de tentativa continuam passando pela autoridade de liberação com fontes atuais.
- Contagem, listagem, prévia, criação da prova e início de tentativa executam fora da thread da interface, com conexão própria. Requisições antigas não substituem a seleção mais recente; mudanças rápidas de filtros são agrupadas. Alterar somente quantidade atualiza a mensagem sem reconsultar o acervo.
- A inicialização do banco deixa de executar DDL a cada chamada. Confere a versão do schema e a identidade da conexão; alterações externas do schema invalidam a otimização e são verificadas pelo caminho normal.
- A janela não carrega antecipadamente a elegibilidade das páginas ocultas. Mostra progresso durante o carregamento. O encerramento aguarda as tarefas para evitar destruir threads com trabalho em andamento.
- O fac-símile não é ampliado além do tamanho nativo nem de 800 px. A área de leitura aproveita a altura disponível. Em telas largas, as respostas ficam ao lado; em telas menores, A–E ficam numa faixa compacta. Texto de apoio e questão alternam no mesmo visor. Os indicadores de seleção têm tamanho e contraste definidos.

## Evidência

Mesma cópia do acervo, mesmos 609 itens elegíveis:

| Medição | Antes | Depois |
| --- | ---: | ---: |
| Consultas SQL na contagem | 22.403 | 12 |
| Contagem com cProfile | 43,33 s | 10,16 s |
| Inicialização registrada no Windows | cerca de 36 s | 2,50 s após reabrir a versão corrigida |

As medições são locais. A construção da janela também levou 0,68 s na cópia Qt/offscreen; no Windows, o intervalo do início do log até a aplicação iniciada foi de 17:43:23,143 a 17:43:25,645, com a janela identificada como respondendo. A contagem sem instrumentação levou aproximadamente 8,28 s no ensaio final e permaneceu em segundo plano. Não se afirma que toda análise de integridade seja instantânea.

No ensaio de abertura, contagem, preparação e início de uma prova real de 70 questões, o timer da interface registrou 947 eventos; maior intervalo de 65,9 ms. Quatro mudanças de quantidade não causaram uma segunda consulta de disponibilidade. Nenhum diálogo de erro foi registrado.

Foram renderizadas e inspecionadas telas de 1920×1080, 1240×800 e 960×640. Enunciado, cinco opções e navegação permaneceram acessíveis, sem rolagem horizontal. Fórmulas/figuras continuam sendo apresentadas pelos recortes originais. Um teste cobre também a alternância do apoio em janela pequena.

Artefatos locais, ignorados pelo Git: `reports/performance-ui-20261028/resultado-ui.json`, `count-after.json`, perfis cProfile, capturas `execucao-*.png` e banco de ensaio. A medição anterior permanece em `reports/reimportacao-novas-regras-20261028-163447/perfil-disponibilidade.pstats`.

## Validação e limites

- Suíte integral final: **323 passed, 1 skipped em 187,86 s**. O skip já existente depende de PDFs CEBRASPE/2025 ausentes. Sem exclusões adicionais.
- Testes específicos: resposta do timer durante uma contagem bloqueada, descarte de resultado antigo, quantidade sem nova consulta, igualdade da avaliação com/sem prefetch, fonte alterada permanecendo bloqueada, inicialização leve detectando alteração de schema e opções visíveis nos três tamanhos.
- `compileall` e `git diff --check` passaram. Testes de jornada aguardam a conclusão assíncrona real, sem substituir o verificador ou enfraquecer as assertions de elegibilidade/histórico.
- Bancos de teste e ensaio isolados. O acervo real, seus PDFs e os arquivos experimentais de reconstrução não foram alterados por esta correção. A modificação já existente em `data/questoes.db` é da operação de reimportação anterior.
- Até o fechamento da validação não havia novo commit ou push. O usuário autorizou posteriormente o commit e o envio desta correção na branch de trabalho; nenhum PR será aberto. A contagem continua exigindo alguns segundos de conferência em segundo plano; novos documentos ou hardware diferente podem ter outros tempos.
