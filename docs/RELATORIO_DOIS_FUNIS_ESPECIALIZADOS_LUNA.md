# Relatório de execução — dois funis especializados de importação

Fechamento em 28/10/2026. Branch `codex/two-specialized-import-funnels`.

**Implementação local validada nos três casos reais selecionados, com ressalvas externas e sem aceite irrestrito do catálogo.** A Dataprev permanece bloqueada por fonte preliminar e identidade documental incompleta. Generalização cega e digitalização real por OCR não foram comprovadas.

## Resultado atual das famílias reais

| Estrutura / perfil | Par real | Extraídas / respostas | Elegíveis | Duas jornadas pela interface |
| --- | --- | ---: | ---: | --- |
| Números com caixas A–E e duas colunas / `multipla_escolha_numerada_v1`, leitor `pdf_caixas_duas_colunas_v1` | EPAGRI/S201, Downloads | 50 / 50 | 46 | Treino parcial com retomada e aleatória: 46/46, nota 100 em ambos. |
| Rótulo QUESTÃO e bloco sublinhado / `questoes_nomeadas_v1` | Morungaba/AVANÇA SP, Agente Administrativo I, gabarito oficial definitivo | 40 / 40 | 38 | Treino parcial com retomada e aleatória: 38/38, nota 100 em ambos. |
| Itens C/E recuados e artigo compartilhado / `certo_errado_contexto_v1` | EMBRAPA/Sistemas de Informação, CG2/C05/028, gabarito oficial definitivo nas páginas 2/7/50 | 100 / 100 | 94 | Treino parcial com retomada e aleatória: 94/94, nota 100 em ambos. |

As três importações começaram em bancos novos pela janela principal, usando fontes fora de samples. São estruturas distintas, com delimitação, ordem e tratamento de contexto próprios. As composições preservam todos os números originais. Somente as anuladas ficaram bloqueadas: S201 16/18/19/36; Morungaba 21/31; EMBRAPA 22/36/54/57/93/99. A interface identifica explicitamente o treino parcial; não foram apresentadas como provas com todos os itens avaliáveis. O ciclo de prova completa sem anulações também foi exercitado pelos testes integrados.

Os mapas completos coincidem com transcrições dos quadros originais. Auditoria separada confrontou enunciado e todas as alternativas dos 190 itens com suas regiões físicas e exigiu regiões de apoio quando aplicável: **zero divergências**, incluindo os itens anulados (`closing-source-audit.json`). Esse confronto automatizado integral e as inspeções visuais não constituem prova estatística de generalização.

Raiz dos artefatos: `C:/Users/Felipe/.codex/visualizations/2026/10/28/01a1827a-652a-78c1-b750-c72fabb9e791`.

- S201: `real-pair-20261028/final-ui/resultado-ui.json` e `resultado-resolucao.json`.
- Morungaba: `named-real-ui/closing-ui/resultado-ui.json` e `resultado-resolucao.json`.
- C/E: `ce-real-ui/final/resultado-ui.json` e `resultado-resolucao.json`.
- Capturas de prévia/execução em 960×640 e 1240×800; texto longo e opções acessíveis por rolagem vertical.
- Auditoria integral: `closing-source-audit.json`; hashes originais: `closing-original-hashes.json`.

Esses três pares pertencem ao conteúdo conhecido. As cópias S201 com bytes diferentes têm texto/pixels equivalentes em todas as páginas. Copiar para fora de samples verifica o caminho de importação, não independência do corpus. A autoridade recalcula equivalência integral dos dois documentos; não aprova por semelhança de nomes. O caminho independente para novos pares mantém a exigência de identidade impressa suficiente.

## Dataprev tipo 4: leitura validada, liberação bloqueada

Caderno de 20 páginas, SHA-256 `714aeee8056575bf88fcfa5705d6c8ebc04613f875f365babe4754e6543fe82e`; gabarito de 22 páginas, SHA-256 `77fef273e696ca3a540d3febb00caa4985cd12794ce6efd5fd92127af5e47ae0`. A fonte declara **GABARITOS PRELIMINARES**, aplicação em 11/10/2026. O nome do arquivo não confere definitividade.

A UI extraiu 70 questões, recusou tipo 3 para o caderno tipo 4 e vinculou todas as 70 respostas do quadro correto da página 14. A comparação integral com transcrição visual independente coincidiu. Foram persistidas 70 versões e dois DocumentoFonte, com zero certificados/elegíveis. A composição fica disponível para conferência; iniciar resolução está desabilitado e o gerador não cria simulado. Motivos: `gabarito_preliminar;evidencia_documental_incompleta`.

CNS003 aparece no nome do caderno, sem comprovação impressa suficiente para o contrato de identidade automática. O gabarito definitivo correspondente é necessário para avançar, mas não garante sozinho certificação: também é necessária identidade documental comprovável ou revisão humana efetiva na interface. Nenhuma aprovação humana foi fabricada.

Preservados cinco grupos de texto compartilhado, gráfico de cloud computing e charge. O recorte final do gráfico começa na instrução READ TEXT II, sem Q19. O caso chegou novo, expôs falhas e recebeu ajustes; passou a ser calibração e não é contado como teste cego aprovado. Artefatos: `dataprev-real/closing-ui/resultado-ui.json`, `conferencia-70-respostas.json`, prévias e hashes.

## Desempenho observado

| Caso | Caderno | Gabarito/escopo | Salvar/verificar |
| --- | ---: | ---: | ---: |
| S201 | 6,46 s | 12,14 s | 49,34 s |
| Morungaba, fechamento | 15,47 s | 2,54 s | 24,26 s |
| EMBRAPA/Sistemas | 6,88 s | 11,09 s | 78,56 s |
| Dataprev, fechamento | 15,76 s | 18,63 s | 78,21 s |

Medições locais, inclusive concorrência de validações, abaixo do orçamento local de cinco minutos por salvamento de até 100 itens. O processamento demorado usa worker. Intervalos máximos de timer S201 4,89 s e Dataprev 2,82 s incluem transições/capturas; não comprovam ausência absoluta de pausas. Nenhum dos 45 PDFs locais é uma digitalização real: OCR conserva diagnóstico e revisão assistida, sem promessa de suporte automático irrestrito.

## Matriz final de aceite

| # | Requisito e consumidor | Evidência / estado |
| ---: | --- | --- |
| 1 | Três famílias reais pela UI em bancos novos | Três pares acima; fontes externas a samples; persistência e duas tentativas concluídas por par. Validado nos casos selecionados. |
| 2 | Documento reservado quando disponível | Corpus cego não reservado antes dos ajustes. Dataprev ajustada não é avaliação cega. Limite explícito de generalização. |
| 3 | Prova e gabarito de layouts diferentes | Três pares associados nos escopos corretos; Dataprev lida com bloqueio preliminar. |
| 4 | Múltiplos cargos/versões | UI lista opções, exige escopo; cabeçalhos invertidos e cargos homônimos testados; Dataprev tipo 3 recusado e tipo 4 lido. |
| 5 | Desconhecido/ambíguo | Diagnóstico, seleção e reprocessamento funcionais, com rascunho e sem certificação por adivinhação. Teste integrado aprovado. |
| 6 | Misto e página sem texto | Roteamento por página/bloco e escolhas persistidas; perfil incompatível recusado. OCR de digitalização real não comprovado. |
| 7 | Lacunas, repetidos e colunas | Testes negativos e confronto dos 23 documentos preservam contagens/números. Diferenças por campo ficam registradas, sem regravar referências. |
| 8 | Contexto, imagens, tabela e fórmula | Confronto físico integral de 190 itens; recursos S201/C/E e gráfico/charge Dataprev preservados; testes de pixels/hashes e inspeções de tela. Demais arquivos não recebem aceite universal. |
| 9 | Preliminar, conflito, fonte alterada | Dataprev 70 salvas/zero liberadas/nenhum simulado; testes negativos de conflito e adulteração aprovados. |
| 10 | Idempotência e nova versão | Reimportação reutiliza IDs/evidências; lote parcial completa ausentes; rejeição humana preservada; mudança exige versão explícita. Testes aprovados. |
| 11 | Rascunho recuperável | Gravação atômica e testes de fechamento/retomada, fonte ausente/alterada aprovados. |
| 12 | Ordem, retomada e nota | Composições 50/40/100 preservadas; respostas/posição/tempo retomados; treinos 46/46, 38/38, 94/94. |
| 13 | Aleatório, filtros e quantidade | Três jornadas reais somente com elegíveis e redução informada; filtros exercitados nos testes integrados. |
| 14 | Histórico após edição | Tentativa conserva snapshot/versão/nota anteriores no teste integrado. |
| 15 | Falha/cancelamento/rollback | Leitura recuperável e transação revertida; remove somente recursos novos. Testes aprovados. |
| 16 | UI e desempenho | Capturas nos dois tamanhos e medições acima, com latências documentadas. |
| 17 | Inventário e continuidade | 45 PDFs, 21 pares e quatro sem associação inventariados. Demais casos parciais continuam explícitos. O manifesto histórico não foi relaxado. |
| 18 | Suíte integral | Resultado do fechamento na seção abaixo; reconstrução experimental somente como teste isolado autorizado. |

## Auditoria final das referências históricas

Os 23 snapshots do código de referência `2e8797c` foram reproduzidos e coincidiram com os 23 hashes do manifesto. O código final mantém as 23 contagens e as sequências de números. Resultado final: **0/23 assinaturas integrais e 0/23 projeções antigas idênticas**, com **23/23 contagens e sequências preservadas**. O comando estrito permanece com saída 1 e nenhuma referência foi regravada. Isso é registrado como diferença, não como teste estrito aprovado.

Os campos novos de apoio/instruções explicam parte das diferenças. As diferenças restantes incluem separação de apoio do enunciado, limpeza de cabeçalhos/rodapés, nomes de glifos de caixas, títulos de disciplinas e recuperação de banca/ano a partir da fonte. A disciplina conserva a primeira atribuição: um número interno posterior não sobrescreve o item anterior. A inspeção identificou e corrigiu regressões intermediárias de perda de banca/ano e reintrodução de rodapés; a suíte final inclui suas regressões.

A tabela informa toda alteração dos campos anteriores, sem ocultar casos ainda parciais. `agente_administrativo_i-4.pdf` continua com identificação OCR residual no último item e não recebeu declaração de suporte integral. Os totais antigos de 16/23 e 15/23 projeções são históricos e não descrevem esta rodada. A fidelidade integral ao PDF nos demais documentos não é inferida apenas da preservação de contagens.

Artefatos: `parser-reference-all.json`, `parser-all-final-audited.json`, `regression-final-field-differences.json` e `regression-final-audited.json`. As alterações de alternativas foram examinadas campo a campo: os trechos removidos são títulos/rodapés; o caso OCR residual acima permanece explícito.

| Documento | Campos anteriores alterados (quantidade de itens) |
| --- | --- |
| `samples/administrador-FGV.pdf` | alternativas: 4, disciplina: 4 |
| `samples/agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf` | alternativas: 50, disciplina: 50, enunciado: 3 |
| `samples/agente_especializado_analista_de_sistemas.pdf` | alternativas: 4, disciplina: 13 |
| `samples/analista_analise_de_sistema_desenvolvimento_de_sistema.pdf` | confianca: 6, disciplina: 120, enunciado: 120 |
| `samples/analista_de_planejamento_e_orcamento_especialidade_governanca_e_gestao_de_projetos_de_ti-CEBRASPE.pdf` | ano: 100, enunciado: 1 |
| `samples/lote_2026_08_22/agente_administrativo_auxiliar_i.pdf` | alternativas: 3, ano: 30 |
| `samples/lote_2026_08_22/agente_administrativo_i-1.pdf` | enunciado: 4 |
| `samples/lote_2026_08_22/agente_administrativo_i-2.pdf` | alternativas: 1 |
| `samples/lote_2026_08_22/agente_administrativo_i-3.pdf` | alternativas: 1, disciplina: 36, enunciado: 11 |
| `samples/lote_2026_08_22/agente_administrativo_i-4.pdf` | alternativas: 4, disciplina: 39 |
| `samples/lote_2026_08_22/agente_administrativo_i.pdf` | alternativas: 4, disciplina: 39 |
| `samples/lote_2026_08_22/agente_nivel_superior_analista_de_sistemas.pdf` | alternativas: 1, enunciado: 10 |
| `samples/lote_2026_08_22/analista_adm_desenvolvimento_sistemas.pdf` | alternativas: 2, disciplina: 1, enunciado: 4 |
| `samples/lote_2026_08_22/analista_administrativo_iii_analista_de_sistemas.pdf` | alternativas: 2, disciplina: 60 |
| `samples/lote_2026_08_22/analista_analista_de_sistemas.pdf` | disciplina: 9 |
| `samples/lote_2026_08_22/analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf` | confianca: 7, disciplina: 99, enunciado: 100 |
| `samples/lote_2026_08_22/analista_area_ciencias_exatas_e_da_terra_subarea_sistemas_de_informacao.pdf` | confianca: 7, disciplina: 99, enunciado: 100 |
| `samples/lote_2026_08_22/analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf` | alternativas: 4, disciplina: 20 |
| `samples/lote_2026_08_22/analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf` | alternativas: 6, disciplina: 1 |
| `samples/lote_2026_08_22/auditor_fiscal.pdf` | alternativas: 1, banca: 40, disciplina: 23 |
| `samples/lote_2026_08_22/prova1_auditor_fiscal.pdf` | alternativas: 1, disciplina: 11, enunciado: 6 |
| `samples/lote_2026_08_22/provas_2e3_auditor_fiscal.pdf` | enunciado: 2 |
| `samples/TRANSPETRO.pdf` | alternativas: 2, disciplina: 12 |

A auditoria distinta do diff conferiu consumidores da UI, transação/rollback, cancelamento, identificação independente, equivalência recalculada, preservação de rejeição humana, revalidação de fontes e ausência de alteração operacional do acervo. Não houve delegação.

## Validação final e preservação

Suíte integral final: **318 passed, 1 skipped em 192,00 s**, comando `venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`, sem exclusões. O único skip é `tests/test_cebraspe_2025.py:86`, por ausência dos PDFs externos específicos; os PDFs fornecidos nesta tarefa não são esses arquivos. `venv\Scripts\python.exe -m compileall -q src tests` e `git diff --check` passaram. Nenhuma migração de esquema é necessária. Até o fechamento da validação não houve commit, push ou PR. O usuário autorizou posteriormente commit e push desta entrega na branch indicada; nenhum PR será aberto. `data/questoes.db` já estava modificado; não foi alvo dos testes nem reimportado. Os três arquivos experimentais de reconstrução foram preservados; somente o teste autorizado entrou na suíte, com banco isolado. Os quatro PDFs fornecidos mantêm os hashes originais.

As ressalvas externas são: fonte definitiva/identidade verificável para a Dataprev; novos pares ainda não usados, se for exigida comprovação de generalização; PDFs CEBRASPE/2025 ausentes para o teste já condicionado a essas fontes. Isso não significa aceite integral sem ressalvas nem suporte universal.

---

## Histórico de execução e inventário

**Histórico: os resultados abaixo são de rodadas anteriores; a síntese de fechamento acima prevalece.** Este relatório registra a implementação e as evidências já obtidas, inclusive os bloqueios de extração observados. Não significa que todos os documentos do catálogo estejam suportados.

## Caso real enviado pelo usuário — EPAGRI/S201 (28/10)

Os PDFs de Downloads foram usados somente como fontes: caderno de 16 páginas,
SHA-256 `606c7e18348de8e79329b4c4938483406caa3f1f8a432799a84be2d92827de86`, e
gabarito de quatro páginas, SHA-256 `134e1ae3d8ddc2391d385b6ce1a7e165d878bcef887fedbec3320adb383fcdc4`.
O conteúdo textual normalizado e os pixels de todas as páginas coincidem com
um par já catalogado; os bytes diferem. Portanto, é um caso real externo a
`samples`, mas não um documento reservado nem prova de generalização cega.

A jornada real da janela principal selecionou os dois arquivos, escolheu
Analista de Sistemas/S201, extraiu 50 itens, vinculou 50 respostas, salvou 50
versões e obteve 46 elegíveis. As únicas quatro pendências finais são as
anulações 16, 18, 19 e 36, conferidas no quadro S201. Não foi criada revisão
humana e o documento não foi chamado de definitivo com base no nome.
A composição original conserva os 50 números e a consulta oferece explicitamente
**treino parcial de 46/50**. Não é uma prova completa com 50 itens avaliáveis.

As respostas foram confrontadas com uma transcrição visual independente do
quadro, incluindo a alteração da questão 14 para C. O treino parcial manteve a
ordem, registrou cinco respostas pelos controles da interface, retomou posição,
respostas e tempo e concluiu com **46/46, nota 100**. O gerador solicitou 50,
informou disponibilidade de 46, sorteou apenas elegíveis e concluiu também com
**46/46, nota 100**. As anulações ficaram fora das duas tentativas.

A validação encontrou e corrigiu: cargo quebrado na capa; T11/T12 tratados como
versões; escopo do gabarito lido pelo leitor de caderno; seleção entre códigos
de cargos homônimos; cabeçalhos e redação anexados à alternativa final; números
internos cortando enunciados; variável de região contextual substituindo o recorte
da questão; aviso de parcial desaparecendo ao navegar e recorte anterior ainda
visível até a exclusão adiada do widget. O perfil físico de caixas de seleção
é reconhecido pela estrutura, sem regra pelo nome do arquivo. Preserva o
expoente em Q11, a tabela/fórmula em Q20 e o contexto de Q1–3 nos fac-símiles.

Cópias fora de `samples` só reutilizam uma associação conhecida mediante confronto
integral de texto e pixels de ambos os documentos, com hashes, dimensão, rotação
e fingerprint das páginas. A autoridade recalcula a comprovação; prova forjada
ou alteração de gráfico é recusada. Esse caminho é específico de equivalência
a uma fonte conhecida; o caminho independente para novos pares continua exigindo
identidade impressa verificável. Ele não demonstra suporte automático a qualquer
par novo sem versão declarada.

Artefatos em `real-pair-20261028/final-ui/`, sob a raiz de visualizações desta tarefa:
`resultado-ui.json`, `resultado-resolucao.json`, prévias das 50 questões e capturas
de execução em 960×640 e 1240×800. O teste de regressão `test_pdf_caixas.py`
confronta enunciados e todas as alternativas dos 50 itens com as regiões físicas,
sem usar as respostas para reconstruir texto. A inspeção visual examinou as páginas
objetivas, a redação, o quadro de respostas e as telas de fórmula/tabela.

Tempos observados: caderno **6,46 s**, leitura/seleção de gabarito **12,14 s**,
salvamento/verificação **49,34 s**. Houve 955 eventos do timer da interface;
o maior intervalo medido foi **4,89 s**, incluindo processamento e capturas.
Isso comprova execução no worker, mas não comprova ausência de pausas em todas
as transições da interface; essa latência permanece identificada para auditoria.
O banco real e os arquivos de Downloads não foram usados como destino de gravação.

## Entregue nesta execução

- Registro de perfis de caderno e gabarito em `src/importador/perfis/registro.py`, reconhecimento por documento e reprocessamento explícito pelo perfil escolhido.
- Associação documental com estados `correspondente`, `incompleto`, `ambiguo` e `incompativel`, ligada à tela de importação.
- Persistência em lote por `src/importador/lote_verificado.py`: salva questões revisadas em transação e só tenta liberação automática quando há par PDF, escopo, número, conteúdo e regiões físicas suficientes. Falta de evidência mantém a questão pendente.
- Perfis de gabarito e diagnóstico por página. A tela não oferece uma única seleção global quando o documento apresenta layouts mistos.
- Salvamento em segundo plano e criação da composição original junto com o último lote pendente; fluxo manual sem fonte disponível continua salvando como pendente.
- Cobertura de teste para perfil selecionado, associação sem confirmação por código digitado, persistência de evidências e jornada de UI.

## Continuação de 28/10 — pendências verificadas e resolvidas

- A auditoria encontrou rollback que podia excluir fac-símiles de importações anteriores. A operação agora rastreia e remove somente arquivos novos, inclusive em falha na preparação antes da transação. Dois testes reproduzem falhas distintas e comprovam a preservação.
- Cargo, código e versão passaram a oferecer as opções reconhecidas na fonte. A UI exige escopo quando há várias opções, bloqueia versão incompatível com o caderno e permite reler a seleção. A evidência física agora seleciona a coluna pelo rótulo impresso, inclusive quando os cabeçalhos estão invertidos.
- Caderno e gabarito têm conferência de leitura por página; blocos consecutivos preservam contexto e continuação. Escolhas incompatíveis ficam pendentes; páginas sem texto permanecem identificadas. As escolhas sobrevivem no rascunho.
- Documento desconhecido com zero questões mantém a seleção assistida habilitada e pode ser retomado. Falha real de leitura preserva a edição anterior e permite repetir a importação.
- A renderização de figuras e páginas para OCR foi transferida para o processo isolado. O lote reaproveita o renderizador; recortes contextuais completos são preservados quando a geometria ainda é ambígua. Foram removidas as substituições do recorte nos testes integrados das três famílias e no caderno real de 50 itens.
- Uma questão com tabela e fórmula passou pelo recorte nativo e revisão humana real da UI. Após a correção dos números internos, o mesmo teste comprova o recorte completo e sua validação automática, além da revisão explícita e resolução com imagem íntegra.
- O adaptador reconcilia os itens com `assess_version` antes de devolver a elegibilidade. A tela distingue verificadas de elegíveis e oferece atalhos reais para abrir a prova/pendências e o gerador.
- O treino parcial usou duas de três questões, preservou ordem e retomou resposta, posição e tempo. O simulado respeitou disciplina, banca, categoria, tipo e limite de quantidade, excluindo o item pendente. As duas tentativas foram finalizadas com resultado esperado.
- A reimportação agora reconhece salvamentos parciais pela identidade das fontes e do escopo: reutiliza IDs e evidências, acrescenta somente itens ausentes e preserva rejeições humanas. Metadados legados podem ser reaproveitados quando a evidência já comprova o mesmo gabarito; sem identificação suficiente, a operação orienta conferência em vez de duplicar ou fundir registros. Cópias íntegras dos PDFs restauram localizações ausentes sem recriar questões. Escopos distintos não são fundidos.
- A revisão independente do código foi feita em uma passagem separada pelo próprio agente; não houve delegação. A suíte completa final desta continuação passou com **296 passed, 1 skipped em 167,72 s**. O teste OCR existente foi adaptado à nova fronteira de renderização; sua expectativa de cargo, tipo e números permaneceu intacta.

## Auditoria adicional desta continuação

Após as correções do S201, a suíte integral passou com **301 passed, 1 skipped
em 171,37 s**, sem exclusões; o único skip continua ligado aos PDFs externos
CEBRASPE/2025 ausentes. Uma execução intermediária revelou que o teste da tabela
esperava o defeito antigo de corte por número interno. O teste passou a exigir
certificação do recorte completo e manteve a conferência humana explícita;
os testes negativos de conteúdo alterado e conflito permaneceram ativos.

O confronto histórico foi repetido sem regravar referências: 0/23 assinaturas
integrais, 15/23 projeções antigas e 23/23 contagens preservadas. A projeção FGV
adicional mudou somente a disciplina das questões 23–26, de Informática para
Raciocínio Lógico e Matemática, coerente com o título impresso “Raciocínio Lógico
e Matemático”. As diferenças do S201 incluem remoção dos cabeçalhos e redação
indevidos e dos nomes textuais de ícones de seleção. Os números históricos da
seção abaixo descrevem a rodada anterior a essas correções.

Na continuação C/E, a inspeção das duas primeiras páginas de exatas identificou
um fragmento da barra de seção dentro do artigo e a marca PCI cortada ao dividir
colunas. A limpeza é feita na página inteira; a área objetiva abaixo da barra
orienta a detecção das colunas e a região contextual. Os bloqueios restantes
continuam sendo confrontados com a fonte, sem tolerância menor.

## Evidências de validação

- Baseline anterior à implementação: `250 passed, 1 skipped` (registrado durante a execução).
- Execuções integrais anteriores: `265 passed, 1 skipped` em 97,22 s; `271 passed, 1 skipped` em 136,57 s; `272 passed, 1 skipped` em 109,79 s; `276 passed, 1 skipped` em 119,08 s; `287 passed, 1 skipped` em 137,78 s; `288 passed, 1 skipped` em 147,50 s; `290 passed, 1 skipped` em 147,37 s. A continuação final passou com **`296 passed, 1 skipped` em 167,72 s**. A primeira rodada desta continuação encontrou um mock OCR ainda ligado à fronteira antiga; corrigido o isolamento do teste, a suíte foi repetida inteira. Uma coleta antiga sem diretório-alvo incluiu pastas inacessíveis; as execuções finais foram limitadas a `tests/`, sem excluir casos.
- O teste ignorado é `tests/test_cebraspe_2025.py:86`: depende de PDFs fornecidos pelo usuário que não estão disponíveis para essa execução automatizada.
- `python -m compileall -q src tests`: passou.
- `scripts/verificar_regressoes_perfis.py`: a assinatura integral continua em **0/23**, com as 23 contagens coincidentes e saída estrita 1. O diagnóstico acrescentado explica **16/23** como extensão do contrato dos dicionários. Os sete restantes foram reproduzidos no código de `2e8797c`, que coincidiu com os sete hashes históricos, e comparados campo a campo com o código atual. A classificação está abaixo. O resultado estrito não foi relaxado e nenhum manifesto foi atualizado.
- Inspeção visual com o renderizador Windows, usando banco isolado, em `960×640` e `1240×800`: conteúdo e ações principais permanecem acessíveis; em `960×640` a etapa inicial requer rolagem vertical, sem rolagem horizontal. A captura encontrou uma barra horizontal desnecessária no menu lateral; ela foi removida e ganhou teste de regressão.
- Rascunhos da importação agora são gravados atomicamente em `data/importacao_rascunhos/atual.json`, incluem hashes SHA-256 fixados das fontes, restauram a etapa e as questões ao reabrir e recusam retomada quando a fonte desapareceu ou mudou. Testes cobrem fechamento/retomada da tela e detecção da alteração.
- Metadados e limpeza de caracteres da mesma página são reutilizados dentro da leitura de uma fonte; testes confirmam invalidação quando o arquivo muda. O lote C/E de exatas caiu de 435,52 s para **50,78 s** no salvamento/verificação; a extração real levou 4,71 s. O lote de produção animal levou **52,44 s**, com extração de 5,72 s. As contagens e bloqueios permaneceram iguais.
- Cancelamento cooperativo foi ligado à tela de importação e ao adaptador de lote. Leituras são descartadas ao término da etapa corrente; cancelamento durante a persistência reverte a transação toda. Dois testes focados passaram, incluindo rollback.
- Testes integrados selecionam PDFs temporários fora de `samples/` pela UI para três famílias: questões nomeadas, múltipla escolha numerada e C/E com texto compartilhado. Cada cenário extrai, persiste evidências, confirma elegibilidade, abre a composição original e conclui tentativas original e aleatória com correção esperada.
- Testes integrados de revisão humana pela UI cobrem decisão definitiva com evidências dos dois PDFs e decisão conflitante que mantém a questão bloqueada; os dois cenários passaram.
- Reimportação do mesmo par com conteúdo igual reutiliza IDs/composição existentes; conteúdo diferente exige a opção explícita de nova versão. Teste pela UI confirma que o reimport idêntico não duplica questões/provas, que a nova versão bloqueia divergências da fonte e que a tentativa anterior continua ligada ao snapshot histórico.
- O caderno real de tecnologia foi importado e reprocessado com 50 questões nos dois modos. A falha nativa inicial de `pypdfium2` foi isolada em subprocesso; os testes atuais executam o recorte real, exigem ao menos uma imagem e conferem a existência dos recursos. O caso sintético de tabela/fórmula também verifica pixels coloridos, persistência, conferência humana e execução.
- A validação integral identificou e corrigiu um elo ausente: respostas extraídas do gabarito não eram inseridas no snapshot persistido quando o caderno vinha sem resposta. O adaptador agora preenche somente respostas únicas extraídas, preserva respostas já informadas e continua submetendo o snapshot ao verificador normal. Testes sintéticos verificam o salvamento e que status preliminar continua bloqueado.
- Nova execução do par de tecnologia em banco temporário isolado: 50 itens persistidos, 28 versões elegíveis e 22 pendentes. O diagnóstico independente no banco confirmou `version_is_eligible=True` para 28/50. Os 22 permanecem pendentes por divergências localizadas de conteúdo/fac-símile e avisos geométricos; não foram aprovados por tolerância relaxada.
- A grade EMBRAPA/C/E tinha zeros de preenchimento depois das linhas parciais 61–70 e 91–100. O extrator agora aceita o preenchimento somente quando as respostas úteis ainda correspondem à quantidade de marcadores; os três blocos do catálogo foram extraídos sem conflitos, totalizando 100/100 respostas. A persistência normaliza `C/E` para `Certo/Errado` no snapshot, conforme o tipo da questão.
- Execução profunda do par EMBRAPA/C/E de produção animal: 100 itens persistidos, 71 versões elegíveis e 29 pendentes. As pendências incluem 17 itens sem região de contexto comprovada, 9 sem status/fac-símile liberável e 3 sem evidência física. A repetição final após a otimização levou 52,44 s para salvar/verificar, mantendo esses resultados.
- Inventário de leitura dos arquivos confirmados no catálogo: 21 pares, todos com caderno e gabarito presentes; 18 cadernos classificados como múltipla escolha e 3 como certo/errado. Os 21 pares têm execução profunda confiável sem duplicação nos bancos limpos registrados abaixo; o último foi repetido depois que uma tentativa anterior deixou banco vazio. O reteste do gabarito preliminar, após corrigir a detecção singular, não liberou nenhum item. Dois cadernos receberam aviso de segmentações equivalentes; quatro gabaritos tiveram família `desconhecida` no classificador, embora o extrator textual os rotule.
- Um segundo par definitivo de múltipla escolha, com layout pontuado: execução isolada persistiu 50 itens, liberou 38 e manteve 12 pendentes (7 divergências de conteúdo e 5 conjuntos de alternativas incompletos).

## Auditoria das 23 diferenças históricas

A comparação foi reproduzida com uma cópia do código de `2e8797c` extraída por
`git archive` para a área de visualizações. Os sete casos que não coincidiam na
projeção do contrato antigo reproduziram os sete hashes do manifesto naquele
código. A comparação atual preserva contagem, número oficial e alternativas nos
23 documentos. A assinatura integral continua diferente e o verificador
continua retornando falha estrita; nenhuma referência foi regravada.

| Documento com diferença além dos campos novos | Campos alterados | Classificação comprovada na comparação |
| --- | --- | --- |
| `agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf` | 3 enunciados | O texto anterior é exatamente apoio + enunciado atuais, após normalizar espaços, marcadores e acentos. |
| `analista_analise_de_sistema_desenvolvimento_de_sistema.pdf` | 120 enunciados; 6 sinais de confiança | Separação exata de apoio/enunciado; confiança recalculada sobre o corpo separado. |
| `lote_2026_08_22/agente_administrativo_i-3.pdf` | 11 enunciados | Separação exata de apoio/enunciado. |
| `lote_2026_08_22/analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf` | 100 enunciados; 7 sinais de confiança | 89 separações exatas; 11 remoções exatas do apoio + enunciado do item anterior + cabeçalho “Conhecimentos Gerais”, que haviam contaminado o item seguinte. |
| `lote_2026_08_22/analista_area_ciencias_exatas_e_da_terra_subarea_sistemas_de_informacao.pdf` | 100 enunciados; 7 sinais de confiança | Mesma classificação: 89 separações exatas e 11 remoções de contaminação pelo item anterior/cabeçalho. |
| `lote_2026_08_22/prova1_auditor_fiscal.pdf` | 6 enunciados | Separação exata de apoio/enunciado. |
| `lote_2026_08_22/provas_2e3_auditor_fiscal.pdf` | 2 enunciados | Separação exata de apoio/enunciado. |

Resultado: 16 assinaturas projetadas preservam os campos antigos; nos sete
restantes há 420 separações exatas de contexto, 22 remoções exatas de
contaminação e 20 alterações do sinal heurístico de confiança. Essa análise
explica as diferenças, sem converter confiança em aprovação nem substituir
uma referência independente de fidelidade completa ao PDF.

Os snapshots e diferenças completos ficam fora da entrega de código, em
`C:\Users\Felipe\.codex\visualizations\2026\10\28\01a1827a-652a-78c1-b750-c72fabb9e791`:
`regression-fields.json`, `parser-old.json`, `parser-current.json`,
`parser-field-differences.json`, `parser-context-classification.json` e
`parser-contamination-classification.json`.

## Áreas alteradas

- `src/importador/`: registro, reconhecimento/roteamento, seleção de escopo, leitores de prova/gabarito, evidências, renderização isolada e adaptador transacional de lote.
- `src/ui/pages/importacao.py`, `src/ui/components/import_choices.py`, `src/ui/main_window.py` e `src/ui/background.py`: escolhas assistidas, rascunho, worker/cancelamento, contagens e navegação após salvar.
- `src/models/importacao_rascunho.py`: persistência atômica do rascunho e integridade das fontes; não acrescenta tabelas ou colunas ao SQLite.
- `tests/test_importacao_continuacao.py`, `test_importacao_lote_verificado.py`, `test_funis_especializados.py`, `test_importacao_rascunho.py`, `test_gabarito_fonte.py`, `test_gabaritos_seguranca.py` e `test_ui_reforma.py`: integração, casos negativos e regressões.
- `scripts/catalogar_padroes.py`, `scripts/verificar_regressoes_perfis.py`, `scripts/verificar_ui_reforma.py`, README e documentação: diagnóstico reproduzível, capturas e comportamento observado.

## Corpus verificado parcialmente

Os hashes abaixo são SHA-256 integrais dos arquivos locais lidos. Os pares estão marcados como confirmados no catálogo; isso é evidência de vínculo catalogado, não de extração bem-sucedida.

| Caderno / gabarito | Família e contagem observadas | Resultado da validação profunda |
| --- | --- | --- |
| `samples/administrador-fgv.pdf` / `samples/GABARITO-FGV.pdf` | Caderno: `multipla_escolha_sequencia_isolada_v3`, 80 questões. Com escopo exato `ADMINISTRADOR` / `PROVA TIPO 1`, o gabarito preliminar produz 80 respostas sem conflitos. | Certificação bloqueada corretamente: o cabeçalho da fonte diz “Gabaritos preliminares”. Uma tentativa anterior à correção de detecção de plural classificou incorretamente o documento e não é evidência válida de aprovação. |
| `samples/agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf` / `samples/gabarito_definitivox.pdf` | Caderno: perfil `multipla_escolha_numerada_v1`, 50 questões após correção do roteamento. Gabarito associado com escopo `S201 Analista de Sistemas`. | Resultado anterior: 28/50. A continuação com os PDFs equivalentes de Downloads obteve 46/50; quatro anulações bloqueadas, treino parcial e aleatória concluídos pela UI. |
| `samples/lote_2026_08_22/analista_analista_de_sistemas.pdf` / `samples/lote_2026_08_22/gabaritos_definitivos.pdf` | Caderno: `multipla_escolha_pontuada_v2`, 50 questões. Gabarito: 50 respostas sem conflitos, escopo `IBFC_04_ANALISTA` / `ANALISTA DE SISTEMAS`. | Salvou 50; 38 elegíveis e 12 pendentes (7 alegações de conteúdo divergentes e 5 conjuntos de alternativas incompletos). |
| `samples/lote_2026_08_22/analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf` / `samples/lote_2026_08_22/gabarito_definitivo.pdf` | Caderno: `certo_errado_contexto_v1`, 100 itens. Gabarito associado pelos três códigos confirmados `CG2`, `C03` e `015`; 100 respostas, sem conflitos. | Salvou 100; 71 elegíveis e 29 pendentes. Salvamento/verificação final: 52,44 s. Importação é parcial; pendências documentais permanecem. |

| Arquivo | SHA-256 |
| --- | --- |
| `administrador-fgv.pdf` | `0ade2ba073e4bd8add373ff009e6f435ea0ab9484773d340a8f98c34b2fb3703` |
| `GABARITO-FGV.pdf` | `ba5f08c8cc4a3d04f0611c9a188a9e39bd3d5d87d11813ede17b62e2e578c817` |
| `agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf` | `318cae0762e6c523079219645772a9327ae08198919a9a2d96a31ca2b4bfab3a` |
| `gabarito_definitivox.pdf` | `d1980621ceede73dd342782e4a36cbbf6a2e09784a1771f9d866fccc5086d557` |
| `analista_analista_de_sistemas.pdf` | `b48a028e30606cfe6ce8ad64587a7e32a7f80cef8d273c62c04c68271e764b64` |
| `gabaritos_definitivos.pdf` | `fb562f3f69d8731ae1e9a60bdf7f4c4462e3eeda0585c41ad469343460857e18` |
| `analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf` | `284da4909dbf954ae8094b38681103ed784f93fadd038a267948981365bc91c8` |
| `gabarito_definitivo.pdf` | `8ac9a838176be1cf4089483f67f38dc58acfeab15bcc9217e33674e9f0cb93bb` |

O catálogo contém 21 pares confirmados e 20 arquivos de gabarito distintos, incluindo complementos (há gabaritos compartilhados). Foram executados em bancos isolados os 21 pares; quatro outros PDFs do diretório não têm papel/par confirmado no catálogo. A tabela registra a execução profunda por caderno.

| Caderno | Perfil reconhecido | Gabarito / família | Resultado de execução profunda |
| --- | --- | --- | --- |
| `administrador-fgv.pdf` | sequência isolada v3; reconhecimento ambíguo | listas por bloco / múltipla escolha | 80/80 respostas com escopo; preliminar, certificação bloqueada |
| `agente_especializado_analista_de_sistemas.pdf` | sequência isolada v3 | listas por bloco / múltipla escolha | Salvou 60; 0 elegíveis e 60 pendentes por ausência de fac-símile/região liberável. |
| `lote_2026_08_22/analista_administrativo_iii_analista_de_sistemas.pdf` | sequência isolada v3; aviso de limites equivalentes | listas por bloco / múltipla escolha | Salvou 80; 76 elegíveis e 4 pendentes por divergência de conteúdo alegado. |
| `lote_2026_08_22/analista_analista_de_sistemas.pdf` | múltipla escolha pontuada v2 | matriz / múltipla escolha | 38/50 elegíveis; 12 pendentes |
| `lote_2026_08_22/agente_administrativo_i.pdf` | questões nomeadas v1 | pares / múltipla escolha | Salvou 40; 36 elegíveis e 4 sem validação automática (banco isolado `deep-rest-03`). |
| `lote_2026_08_22/agente_administrativo_i-1.pdf` | múltipla escolha numerada v1 | pares / família desconhecida | Salvou 25; 24 elegíveis e 1 pendente por divergência de conteúdo. |
| `lote_2026_08_22/agente_administrativo_i-3.pdf` | questões nomeadas v1 | pares / múltipla escolha | Salvou 55; 48 elegíveis e 7 pendentes (3 divergências de conteúdo, 2 alternativas incompletas, 1 resposta ausente, 1 evidência física ausente). |
| `lote_2026_08_22/agente_administrativo_i-4.pdf` | questões nomeadas v1 | pares / múltipla escolha | Salvou 40; 0 elegíveis e 40 pendentes por âncora geométrica ambígua. |
| `agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf` | múltipla escolha numerada v1 | matriz / família desconhecida | Resultado anterior: 28/50. Reteste do par equivalente enviado pelo usuário: 46/50; somente quatro anulações bloqueadas. |
| `lote_2026_08_22/analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf` | múltipla escolha numerada v1 | lista / família desconhecida | Salvou 50; 32 elegíveis e 18 pendentes (16 conjuntos de alternativas incompletos, 2 divergências de conteúdo). |
| `lote_2026_08_22/analista_adm_desenvolvimento_sistemas.pdf` | múltipla escolha pontuada v2 | pares / família desconhecida | Reteste após correção: salvou 40; 0 elegíveis, 40 pendentes por estado preliminar (37) e alternativas incompletas (3). A tentativa inicial com 34 liberações foi invalidada. |
| `lote_2026_08_22/analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf` | sequência isolada v3; aviso de limites equivalentes | listas por bloco / múltipla escolha | Salvou 70; 64 elegíveis e 6 pendentes (5 divergências de conteúdo, 1 evidência física ausente). |
| `lote_2026_08_22/auditor_fiscal.pdf` | questões nomeadas v1 | listas por bloco / múltipla escolha | Salvou 40; 0 elegíveis e 40 pendentes. O gabarito primário é preliminar; há também lacunas de evidência física. |
| `lote_2026_08_22/prova1_auditor_fiscal.pdf` | múltipla escolha traço v2 | pares / múltipla escolha | Salvou 45; 0 elegíveis e 45 pendentes por ausência de evidência física liberável. |
| `lote_2026_08_22/provas_2e3_auditor_fiscal.pdf` | múltipla escolha traço v2 | pares / múltipla escolha | Salvou 70; 0 elegíveis e 70 pendentes por ausência de evidência física liberável. |
| `analista_de_planejamento_e_orcamento_especialidade_governanca_e_gestao_de_projetos_de_ti-cebraspe.pdf` | certo/errado sequencial v1 | listas por bloco / classificado como múltipla escolha | Salvou 100; 87 elegíveis e 13 pendentes (8 divergências de conteúdo, 5 sem status/fac-símile liberável). |
| `transpetro.pdf` | sequência isolada v3 | matriz multiversão / múltipla escolha | Salvou 70; 57 elegíveis e 13 pendentes (9 vínculos de texto compartilhado não confirmados, 4 divergências de conteúdo). |
| `lote_2026_08_22/agente_nivel_superior_analista_de_sistemas.pdf` | múltipla escolha pontuada v2 | lista / família desconhecida | Salvou 40; 34 elegíveis e 6 pendentes (4 alternativas incompletas, 2 divergências de conteúdo). |
| `lote_2026_08_22/agente_administrativo_i-2.pdf` | múltipla escolha numerada v1; reconhecimento ambíguo | listas por bloco / múltipla escolha | Salvou 30; 0 elegíveis e 30 pendentes por ausência de evidência física. O gabarito foi classificado como preliminar; reconhecimento levou 0,8 s e persistência/verificação 5,7 s. |
| `lote_2026_08_22/analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf` | certo/errado com contexto v1 | grade C/E | Repetição final: salvou 100; 71 elegíveis e 29 pendentes; 52,44 s para salvar/verificar. |
| `lote_2026_08_22/analista_area_ciencias_exatas_e_da_terra_subarea_sistemas_de_informacao.pdf` | certo/errado com contexto v1 | grade C/E | Repetição final: salvou 100; 74 elegíveis e 26 pendentes; 50,78 s. Banco íntegro: 100 versões, 240 evidências e 74 validações automáticas. Pendências incluem contexto/evidência de contexto (17), estado/fac-símile (6) e evidência física (3), com motivos sobrepostos. |

`Família desconhecida` é o resultado do classificador, não uma prova de que a extração de respostas falha. A triagem verifica arquivos e reconhecimento; as 21 linhas da tabela correspondem a gravações em bancos isolados, cada uma com o resultado declarado na última coluna.

## Critérios ainda pendentes

- O aceite integral de fidelidade das três famílias em pares reais ainda não foi demonstrado. Além dos ciclos sintéticos, o par real S201 enviado pelo usuário concluiu a jornada da UI com 46/50 elegíveis e somente quatro anulações bloqueadas. Os outros pares reais mantêm as pendências documentais listadas; a conferência integral das três famílias ainda falta. Esses estados não podem ser apresentados como aprovação integral dos arquivos.
- Não houve reserva de documentos antes dos ajustes: todos os PDFs locais já foram inspecionados. Uma avaliação cega de generalização precisa de referências independentes ainda não utilizadas; copiar ou renomear PDFs não atende a esse critério.
- Os quatro PDFs sem associação confirmada continuam sem vínculo automático. Gabaritos preliminares e itens sem âncora, contexto ou fac-símile suficiente permanecem bloqueados; sua aprovação exige evidência válida ou revisão explícita, não tolerância menor do verificador.
- Não há caso real escaneado validado de ponta a ponta. OCR e renderização isolada têm cobertura funcional, mas isso não comprova qualidade de OCR em qualquer digitalização.
- O manifesto histórico permanece preservado. A classificação das diferenças não cria referências independentes para os campos novos de contexto e instruções nem prova fidelidade visual integral dos 45 PDFs.

## Desempenho e reprodução

Documento de exatas: 162.802 bytes, 100 itens C/E. Ambiente Windows, Python 3.12.10
do `venv`, `Intel64 Family 6 Model 165 Stepping 3, GenuineIntel`, 12 processadores
lógicos expostos. As durações são desse ambiente e desses documentos.

Histórico do salvamento/verificação do lote de exatas: 435,52 s (baseline),
385,04 s (metadados), 387,78 s (pré-checagem de contexto), 354,17 s (âncoras),
292,56 s (renderizador reutilizado), 324,05 s (reconciliação da elegibilidade),
316,13 s (remoção de validações duplicadas) e **50,78 s** (leitura derivada da
página reutilizada). Houve concorrência com testes em algumas medições
intermediárias; a medição de 50,78 s foi feita sem outra suíte ativa. A
extração final levou 4,71 s. O lote de produção animal mediu 5,72 s para extrair
e 52,44 s para salvar/verificar, mantendo 71 elegíveis e 29 pendentes.

O teste de invalidação confirma que uma fonte alterada abre outro documento e
refaz a leitura; a redução de tempo não dispensa confronto de fonte, pixels,
conteúdo, escopo ou decisão humana. `PRAGMA integrity_check` no banco final de
exatas retornou `ok`, com 100 questões, 100 versões, 240 evidências e 74
validações automáticas.

As medições usaram `run_deep_pair_real.py` na área de visualizações, com
`BANCO_QUESTOES_TEST_MODE=1` e raízes `deep-readable-cache-final` e
`deep-animal-cache-final`, sem substituição do recorte de imagens. As capturas
finais ficam em `visual-continuation/screens/`, na mesma área, com inspeção de
960×640 e 1240×800.

## Estado de dados e Git

- Testes e smoke usaram `BANCO_QUESTOES_TEST_MODE=1`. O `conftest.py` cria diretórios `.t<processo>-<id>` isolados no workspace e sobrescreve o override de raiz; medições e capturas independentes ficaram na área de visualizações. Nenhum desses caminhos aponta para o banco real. A reconstrução do acervo não foi executada.
- `data/questoes.db` já estava modificado antes desta execução e foi preservado. Não foi revertido nem usado como banco de teste.
- Foram preservados os arquivos não rastreados preexistentes `docs/PLANO_DOIS_FUNIS_ESPECIALIZADOS_LUNA.md`, `scripts/reconstruir_acervo.py`, `src/models/reconstrucao_canonica.py` e `tests/test_reconstrucao_canonica.py`.
- Branch atual: `codex/two-specialized-import-funnels`. Estado naquela rodada: alterações locais não commitadas, sem push e sem PR. A autorização posterior de commit/push não inclui o banco nem a reconstrução experimental.

## Inventário integral dos PDFs de `samples/`

O inventário final incluiu os complementos do catálogo e corrigiu a contagem
anterior de cinco para **quatro** arquivos sem associação. `gabaritos-1.pdf` é
complemento confirmado das provas de auditor, não um documento sem vínculo.
Todos os 45 PDFs locais têm texto; não foi identificado um documento real
escaneado. O JSON completo registra páginas, caracteres/imagens, natureza,
papel, hash, escopo catalogado, reconhecimento, contagem declarada detectada e
contagem extraída observada. `total_conferido_independentemente` fica ausente de
valor quando não existe referência validada; a contagem do parser não o
preenche.

Artefato fora do código: `inventario-documental-final.json`, na área de
visualizações citada acima. Comando de reprodução:

```powershell
venv\Scripts\python.exe scripts/catalogar_padroes.py --inventario-integral "caminho/inventario.json" --resultados-extracao "caminho/regression-fields.json"
```

Inventário calculado a partir dos arquivos presentes e de `config/gabaritos.json`: 45 PDFs: 21 cadernos com par confirmado, 20 arquivos gabarito distintos, incluindo complementos (há gabarito compartilhado) e quatro arquivos sem papel/par confirmado no catálogo. Entre os quatro arquivos sem papel catalogado há dois cadernos: `samples/analista_analise_de_sistema_desenvolvimento_de_sistema.pdf` (parser observou 120 itens C/E; o antigo resultado 57/57 foi superado pela auditoria documentada em RELATORIO_CORRECAO_LACUNAS.md, que exige a sequência 1–120; não há gabarito catalogado) e `samples/lote_2026_08_22/agente_administrativo_auxiliar_i.pdf` (30 itens de múltipla escolha; nenhum gabarito catalogado), além de dois PDFs com nome de gabarito sem associação confirmada. Os hashes abaixo cobrem o PDF inteiro.
Os quatro arquivos sem papel catalogado foram triados: os dois cadernos foram reconhecidos com 120 itens C/E e 30 itens de múltipla escolha, respectivamente; `samples/gabarito.pdf` é uma matriz multi-versão (tipos 1 e 2), com status preliminar e sem mapa inequívoco sem selecionar cargo/versão; `samples/lote_2026_08_22/gabarito_definitivo-1.pdf` tem grade C/E e vários códigos EMBRAPA, mas o extrator não produziu mapa inequívoco sem escolher escopo. Nenhum foi associado por semelhança de nome.

| Arquivo | Papel/associação | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `samples/administrador-FGV.pdf` | caderno — par catalogado | 878167 | `0ade2ba073e4bd8add373ff009e6f435ea0ab9484773d340a8f98c34b2fb3703` |
| `samples/agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf` | caderno — par catalogado | 1108177 | `318cae0762e6c523079219645772a9327ae08198919a9a2d96a31ca2b4bfab3a` |
| `samples/agente_especializado_analista_de_sistemas.pdf` | caderno — par catalogado | 1277543 | `2ccdf39df44c243b79b941d51e3966166ceb5e359ba8e9cd10c665f0ab240af6` |
| `samples/analista_analise_de_sistema_desenvolvimento_de_sistema.pdf` | documento sem par confirmado no catálogo | 526401 | `00953555fb958be93b32d782816f63a1d91f4a5b8c384dc09729d602ca37ce61` |
| `samples/analista_de_planejamento_e_orcamento_especialidade_governanca_e_gestao_de_projetos_de_ti-CEBRASPE.pdf` | caderno — par catalogado | 680031 | `4368d3b239ed1a4675c9dbc7e417745515045ab0ac36243983f2379b2af9be2f` |
| `samples/GABARITO-FGV.pdf` | gabarito — associado a administrador-fgv.pdf | 286831 | `ba5f08c8cc4a3d04f0611c9a188a9e39bd3d5d87d11813ede17b62e2e578c817` |
| `samples/gabarito.pdf` | documento sem par confirmado no catálogo | 358261 | `350ede47259b8ad0287f2c5d01d655689d37b3ea6d3f6d43ee34967c400b0b63` |
| `samples/gabarito_definitivo.pdf-CEBRASPE.pdf` | gabarito — associado a analista_de_planejamento_e_orcamento_especialidade_governanca_e_gestao_de_projetos_de_ti-cebraspe.pdf | 438144 | `b1c423410be11187d7e9ef468cdc779cdbd3e48556ea3d1586d8f0c3f357f192` |
| `samples/gabarito_definitivox.pdf` | gabarito — associado a agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf | 2997256 | `d1980621ceede73dd342782e4a36cbbf6a2e09784a1771f9d866fccc5086d557` |
| `samples/gabarixccxto.pdf` | gabarito — associado a agente_especializado_analista_de_sistemas.pdf | 575718 | `72ae6e3df2b129ca337588621ea8cab25fccc224596dec916f1ea994327cc7f4` |
| `samples/lote_2026_08_22/agente_administrativo_auxiliar_i.pdf` | documento sem par confirmado no catálogo | 188748 | `cdc73973be9561ef9364d1a4462b5fba8a7c78b34f0c21c1233ba4bfae92ad4a` |
| `samples/lote_2026_08_22/agente_administrativo_i-1.pdf` | caderno — par catalogado | 590599 | `5a0c867b2cf8f790dbc375a68b65359af315d2b2cbd8450ff573084f72a2f32e` |
| `samples/lote_2026_08_22/agente_administrativo_i-2.pdf` | caderno — par catalogado | 737005 | `74b8cfa1e033920be75f9e3ea51f338dcc3f49acdabb53f002a1e58bc41aba77` |
| `samples/lote_2026_08_22/agente_administrativo_i-3.pdf` | caderno — par catalogado | 380095 | `c2337afb48de51a4559f5e2b20c298c392beba11e8c47e3cb1930ba902306d7f` |
| `samples/lote_2026_08_22/agente_administrativo_i-4.pdf` | caderno — par catalogado | 712019 | `b7506c9d837c353a5148cf2399b09104e2f588a03a1d6c2025f78d8a4daa83c7` |
| `samples/lote_2026_08_22/agente_administrativo_i.pdf` | caderno — par catalogado | 576398 | `5fda45a4bc8432a75e569a035365b6cf11e8805152343a84a7468691d55986bf` |
| `samples/lote_2026_08_22/agente_nivel_superior_analista_de_sistemas.pdf` | caderno — par catalogado | 155624 | `3deb163bfab90bb2947f4428dac66b8dc47d501c28b60c796c6aa89364e90d50` |
| `samples/lote_2026_08_22/analista_adm_desenvolvimento_sistemas.pdf` | caderno — par catalogado | 338096 | `dced4ae770d04fc8ffe5cced4307b1b4d083ac0ed65e37d532253b71ac2dad6a` |
| `samples/lote_2026_08_22/analista_administrativo_iii_analista_de_sistemas.pdf` | caderno — par catalogado | 609412 | `617d85b4491c4e3de3ca9c6132c235182b5a7c4dfd893646fe3795a714ec951a` |
| `samples/lote_2026_08_22/analista_analista_de_sistemas.pdf` | caderno — par catalogado | 339031 | `b48a028e30606cfe6ce8ad64587a7e32a7f80cef8d273c62c04c68271e764b64` |
| `samples/lote_2026_08_22/analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf` | caderno — par catalogado | 388405 | `284da4909dbf954ae8094b38681103ed784f93fadd038a267948981365bc91c8` |
| `samples/lote_2026_08_22/analista_area_ciencias_exatas_e_da_terra_subarea_sistemas_de_informacao.pdf` | caderno — par catalogado | 162802 | `44caa6bda6039c4eb64dcfa266806574e1856815edd6f3456f9e7ca72d7114cb` |
| `samples/lote_2026_08_22/analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf` | caderno — par catalogado | 1276735 | `63c7fe67c95184b5cec43132f0ae1487b71b582b3e6e967199feb645f9293344` |
| `samples/lote_2026_08_22/analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf` | caderno — par catalogado | 675682 | `dc9f3a2c2fdda14aa869a45a22fe0ff381c3883f90ef66cfc7ad5bb474ca6f74` |
| `samples/lote_2026_08_22/auditor_fiscal.pdf` | caderno — par catalogado | 1307028 | `0a3b56eb3228acd0dd569177371a4d26516877e6bfbdf6514f7621fcdba85a0e` |
| `samples/lote_2026_08_22/gab_preliminar_todos_cargos.pdf` | gabarito — associado a lote_2026_08_22/analista_adm_desenvolvimento_sistemas.pdf | 192091 | `50d549c8241760cd3369e3b0ca945d1272fcbc36b5569168d177f1bb4a592d92` |
| `samples/lote_2026_08_22/gabarito-1.pdf` | gabarito — associado a lote_2026_08_22/analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf | 2385277 | `576d607971c27300e087406a9028d800ec1571a587167d139fc39ca35bc6701c` |
| `samples/lote_2026_08_22/gabarito-2.pdf` | gabarito — associado a lote_2026_08_22/analista_administrativo_iii_analista_de_sistemas.pdf | 265842 | `a65f65f1d80683dab3b770220c6f1e8e0f5d3e27aad1f0c27a04841a57d76981` |
| `samples/lote_2026_08_22/gabarito-3.pdf` | gabarito — associado a lote_2026_08_22/agente_administrativo_i-1.pdf | 91589 | `7ddeba468d972f33c8924f0c692a2d9f0c5af516001463e58ac65e8bdc80ab78` |
| `samples/lote_2026_08_22/gabarito-4.pdf` | gabarito — associado a lote_2026_08_22/agente_administrativo_i-2.pdf | 477851 | `508f1804541516f738126ba8def7dfa0dfbfec18412c724415d9503e4ed0db2e` |
| `samples/lote_2026_08_22/gabarito-5.pdf` | gabarito — associado a lote_2026_08_22/agente_administrativo_i-3.pdf | 448222 | `64f8e38b9e718d2e3a8856c53a3f1c4dd2d3f6ba94f456d624cec5f876dc3c8f` |
| `samples/lote_2026_08_22/gabarito-6.pdf` | gabarito — associado a lote_2026_08_22/agente_administrativo_i-4.pdf | 543848 | `238a6aa61648ceb1ce3a4b7d677220d49ec5edd65f0d576f213c34b4e7bc4185` |
| `samples/lote_2026_08_22/gabarito-7.pdf` | gabarito — associado a lote_2026_08_22/auditor_fiscal.pdf | 523910 | `856b083894e2b6d4878f6b56984d9f35daae2f521201ff2830bc9669635d65b1` |
| `samples/lote_2026_08_22/gabarito_definitivo-1.pdf` | documento sem par confirmado no catálogo | 420916 | `35c966140658e3c1b8be2072eda5fca879688520d1f3c7673dee9d0f92bf902e` |
| `samples/lote_2026_08_22/gabarito_definitivo.pdf` | gabarito — associado a lote_2026_08_22/analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf; gabarito — associado a lote_2026_08_22/analista_area_ciencias_exatas_e_da_terra_subarea_sistemas_de_informacao.pdf | 421025 | `8ac9a838176be1cf4089483f67f38dc58acfeab15bcc9217e33674e9f0cb93bb` |
| `samples/lote_2026_08_22/gabarito_definitivo_auditor.pdf` | gabarito — associado a lote_2026_08_22/prova1_auditor_fiscal.pdf; gabarito — associado a lote_2026_08_22/provas_2e3_auditor_fiscal.pdf | 30259 | `5f798778df48039ff2e4cbfda78e86690151329491b3b21ebd502f3c86fd9292` |
| `samples/lote_2026_08_22/gabarito_oficial-1.pdf` | gabarito — associado a lote_2026_08_22/agente_administrativo_i.pdf | 101207 | `b64a3804689f3a0fda9a39872a9c0c71b42d0c53b177839b07d433d3701e2880` |
| `samples/lote_2026_08_22/gabarito_oficial.pdf` | gabarito — associado a lote_2026_08_22/analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf | 1044249 | `70ddfb0f68b644801b97f920e88b4989374215426da92e186d3c82cc48295d66` |
| `samples/lote_2026_08_22/gabaritos-1.pdf` | gabarito — complemento confirmado de prova1_auditor_fiscal.pdf e provas_2e3_auditor_fiscal.pdf | 26452 | `1d98ae54646c65336cd4b2c8bc50eb7dcde624ae1223c893158e4cf340e3cefc` |
| `samples/lote_2026_08_22/gabaritos.pdf` | gabarito — associado a lote_2026_08_22/agente_nivel_superior_analista_de_sistemas.pdf | 145767 | `e274b9b99d7227e30deece2fca448fe20758fa1a02162a5fd85039a8e6ca925e` |
| `samples/lote_2026_08_22/gabaritos_definitivos.pdf` | gabarito — associado a lote_2026_08_22/analista_analista_de_sistemas.pdf | 865763 | `fb562f3f69d8731ae1e9a60bdf7f4c4462e3eeda0585c41ad469343460857e18` |
| `samples/lote_2026_08_22/prova1_auditor_fiscal.pdf` | caderno — par catalogado | 148863 | `2c1b0f41c2e73e100ba7c596410456a6ce698a02031e7e4b15b7144ddbd3d968` |
| `samples/lote_2026_08_22/provas_2e3_auditor_fiscal.pdf` | caderno — par catalogado | 158064 | `9b7499d0554cf4e57788e6d2f6f7b73f17236f2685e47029806c4a478ab8a8cc` |
| `samples/TRANSPETRO GABARITO.pdf` | gabarito — associado a transpetro.pdf | 611334 | `eb71012fd21909a4c999a8b17496fa2f80247bd1479a6fd48faa773493e681ec` |
| `samples/TRANSPETRO.pdf` | caderno — par catalogado | 327826 | `b3ce9b933a725a60f438bd9ae4420c900fc37f6e20f72cf23b7a6d90f450a7a5` |
