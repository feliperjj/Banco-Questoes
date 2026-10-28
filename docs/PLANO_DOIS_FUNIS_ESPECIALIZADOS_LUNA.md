# Plano de ação — dois funis especializados de importação

Data: 28/10/2026. Destinatário: Luna 6.0.

## 1. Resultado exigido e contrato de execução

O usuário deve conseguir selecionar um PDF de prova e seu gabarito, acompanhar o reconhecimento dos dois documentos, conferir somente as exceções, salvar e resolver a prova na ordem original ou gerar um simulado aleatório com as questões elegíveis. O fluxo deve funcionar pela interface PySide6, sem comandos, scripts operacionais ou edição de JSON pelo usuário.

Este documento é um plano; sua criação não executa nem autoriza retroativamente alterações no acervo. Quando o usuário mandar executar este plano, implemente e valide o produto até a entrega descrita aqui, respeitando as fronteiras de dados e Git abaixo.

Não encerrar após investigar, criar módulos, passar testes unitários ou entregar uma primeira família. As etapas são dependências internas da mesma entrega, não motivos para devolver trabalho executável ao usuário. Manter um checklist de execução com evidências e continuar até todos os critérios obrigatórios estarem atendidos ou existir um impedimento externo comprovado.

Não prometer leitura universal de PDFs. A primeira entrega deve especializar e comprovar pelo menos três famílias de layout existentes na coleção: múltipla escolha com marcadores explícitos; múltipla escolha numerada com layout diferente da primeira; certo/errado com texto compartilhado. Selecionar os arquivos concretos no inventário, considerando a existência de gabaritos correspondentes. Classificar todos os demais documentos locais e preservar sua compatibilidade anterior; não é permitido estreitar silenciosamente o suporte para fazer os testes passarem.

Um perfil novo só é declarado suportado depois de passar pelo ciclo completo de importação, associação, persistência e execução. Um documento desconhecido ou ambíguo precisa ter um caminho funcional de identificação/conferência assistida. Se um dos três grupos não tiver fontes disponíveis suficientes, registrar a lacuna como impedimento externo; não substituí-lo por um caso fácil e declarar conclusão integral.

## 2. Instruções obrigatórias para o Luna

- Ler as instruções aplicáveis do repositório e este plano integralmente antes de editar.
- Não abrir, criar ou solicitar pull request em nenhuma situação. Não fazer merge.
- Não assumir que o pedido inclui commit ou push. A entrega padrão é código local validado, documentação e relatório; executar commit/push apenas se autorizados na conversa de execução. Nesse caso, torná-los parte do checklist final.
- Não alterar o banco real, seus recursos, respostas ou histórico como parte desta implementação. Usar bancos novos de teste e cópias consistentes do legado. Migração/reparação do original exige autorização específica que cubra aquela operação; não inferir autorização de planos antigos.
- Preservar mudanças pré-existentes. No diagnóstico de 28/10 havia `data/questoes.db` modificado e três arquivos não rastreados: `scripts/reconstruir_acervo.py`, `src/models/reconstrucao_canonica.py` e `tests/test_reconstrucao_canonica.py`. Reinspecionar, não excluir, incorporar, executar ou sobrescrever esse trabalho automaticamente. Se houver sobreposição indispensável, apresentar o conflito concreto.
- Não diminuir as exigências de elegibilidade para liberar mais questões. Salvar, selecionar um perfil ou concluir OCR não aprova conteúdo nem gabarito.
- Nunca fabricar números oficiais, metadados, respostas, evidências, revisão humana ou status definitivo de gabarito.
- Não pular falhas de teste, retirar assertions, adicionar `skip`/`xfail` ou atualizar referências para esconder regressões. Separar defeito do produto, isolamento de teste e diferença histórica de referência.
- Se delegar, respeitar as instruções de modelos e contexto do usuário: agentes nomeados, `fork_turns="none"`, contexto delimitado, sem Sol em subagentes. Apenas um responsável edita cada conjunto de arquivos. O Luna principal continua responsável pela integração e entrega.
- Comunicar progresso com resultados e incertezas concretas. Nunca apresentar trabalho apenas implementado como validado ou entregue.

## 3. Estado inicial conhecido — reconfirmar

Projeto: `C:\Users\Felipe\Desktop\Banco-Questões`, Python/PySide6/Peewee/SQLite. Branch observada: `main`; escolher uma branch de trabalho conforme instruções vigentes e autorização, preservando alterações locais.

Inventário somente leitura de 28/10: 1.385 questões ativas, 913 liberadas pela avaliação corrente, 868 elegíveis no sorteio, 472 pendentes e 23 provas cadastradas, das quais cinco tinham todos os itens cadastrados liberados. Não confundir essa condição com prova documental de que todos os itens do PDF foram extraídos. São métricas locais, não percentuais de precisão nem metas a inflar.

O fluxo atual já separa várias peças de provas e gabaritos, mas ainda combina estratégias gerais. A importação pela UI salva versões pendentes; a reparação/certificação automática está em outro caminho, operado por scripts. A tarefa é integrar e especializar, aproveitando o que existe, sem criar uma aplicação paralela.

Há seis padrões básicos em `perfis/segmentacao.py`, outros tratamentos de segmentação e sete rótulos de classificação de gabarito em `perfis/documentos.py`. Rótulos, extratores, templates e famílias validadas são contagens diferentes.

Na validação focada anterior, 41 testes passaram e `test_reaplicar_lote_nao_recria_versao_para_contornar_rejeicao` falhou em conjunto; o mesmo teste passou isoladamente. Investigar dependência de ordem/conexão/estado antes de considerar o baseline saudável. Não presumir a causa.

Fontes prioritárias: `docs/PROJECT_BRAIN.md`, `docs/CADERNO_TECNICO.md`, `docs/IMPORTACAO_HIBRIDA.md`, `docs/RELATORIO_REPARACAO_AUTOMATICA_2026-10-27.md` e código atual. Relatórios antigos não substituem o estado observado. Havendo contradição documental, explicitar e corrigir a documentação conforme a regra atual validada; não ressuscitar vínculo por posição visual.

## 4. Arquitetura alvo

```text
PDF da prova
  -> inspeção documental
  -> reconhecimento e seleção de perfil de prova
  -> extrator especializado
  -> validação de conteúdo, contexto e recursos
  -> lote de questões com proveniência
                                         \
                                          -> associação documental e numérica
                                         /   -> verificação/liberação ou exceções
PDF do gabarito                              -> persistência versionada
  -> inspeção documental                    -> prova original / simulado aleatório
  -> reconhecimento e seleção de perfil de gabarito
  -> extrator especializado
  -> validação de respostas e escopo
  -> mapa de respostas com proveniência
```

Dois funis de processamento e um serviço de associação. O funil existente de confiabilidade continua sendo a autoridade de liberação; não confundir suas etapas com o roteamento de leitores.

Especializar por estrutura/layout e versão, usando banca e metadados como evidência auxiliar. Uma banca pode usar vários layouts; um layout pode servir a várias bancas. Compartilhar leitura PDF, renderização, OCR, normalização segura, contratos e erros. Isolar regras que alteram limites, ordem, contexto e geometria.

O reconhecimento pode comparar candidatos, mas a extração principal deve usar um perfil selecionado e uma decisão explicável. Não executar todos os leitores e escolher o que devolve mais questões/respostas. Em documentos mistos, permitir roteamento por página/bloco, preservando escopo e contexto, e não forçar um único perfil global.

## 5. Etapa A — inventário e baseline reproduzível

1. Verificar branch, alterações locais, instruções e ambiente. Usar `venv\Scripts\python.exe` se existir; não recriar o ambiente sem necessidade.
2. Rodar a suíte atual em ambiente isolado. Reproduzir a falha citada isoladamente e com seus antecessores; corrigir o isolamento ou o defeito comprovado com regressão apropriada.
3. Inventariar todos os PDFs de prova e gabarito disponíveis, o catálogo e as referências. Reaproveitar `scripts/catalogar_padroes.py` e `scripts/diagnosticar_formato.py` quando adequados, respeitando efeitos de escrita em relatórios e recursos.
4. Criar matriz por documento: papel, hash, família/layout, natureza textual/escaneada/mista, leitor atual, total esperado conferido na fonte, total extraído, contexto/visual, gabarito correspondente, cargo/versão, conflitos, suporte atual e resultado final.
5. Distinguir total declarado pelo documento, total conferido e estimativa do parser. Ausência de referência fica explícita, nunca preenchida pelo próprio algoritmo como se fosse verdade independente.
6. Selecionar as três famílias iniciais e arquivos de desenvolvimento/validação antes de ajustar os leitores. Reservar, quando disponível, um documento não usado na calibração por família para verificar generalização. Não baixar novos PDFs por conta própria.
   Para cada família, fixar na matriz um ID de perfil, assinatura estrutural observável, par concreto prova/gabarito, referência conferida e condição de aprovação. As duas famílias de múltipla escolha precisam diferir em evidências de layout que determinem regras próprias de reconhecimento/extração, não apenas banca, nome ou rótulo. O caso C/E precisa conter um texto compartilhado cujo vínculo e limites sejam conferidos. Exigir um par real por família e, havendo material local, um segundo caderno independente reservado para validação; copiar/renomear o mesmo PDF não cria um caso independente. Sem segundo documento, registrar suporte comprovado apenas no primeiro e generalização não demonstrada. Não criar dois perfis idênticos para cumprir a quantidade mínima.
7. Registrar tempos de extração e de atualização das telas em arquivos representativos. Definir orçamento de desempenho mensurável com base nesse baseline, registrando tamanho/documento/equipamento; não inventar metas universais.

Aceite A: inventário reconciliado, famílias e corpus definidos, falhas iniciais explicadas, comandos reproduzíveis e dados reais preservados.

## 6. Etapa B — contratos e registro de especialistas

1. Definir interfaces tipadas e pequenas para reconhecimento de prova, reconhecimento de gabarito, extração de cada papel e associação. Reutilizar/evoluir `PerfilDocumento`, `Segmentacao`, `LoteImportado` e `MapaGabarito`; não duplicar estruturas sem necessidade.
2. Registrar cada especialista com ID estável, versão, capacidades, evidências positivas, incompatibilidades, limites conhecidos e referências de teste.
3. Retornar reconhecimento com candidatos, evidências, escopo de páginas/blocos e decisão `reconhecido`, `ambiguo` ou `nao_suportado`. Se houver pontuação, documentar regras e calibrar no corpus; não tratá-la como probabilidade de acerto.
4. Permitir escolha explícita de perfil em ambiguidades, mantendo validações estruturais/documentais. Uma escolha incompatível gera diagnóstico, não sucesso automático.
5. Contrato de questão: número oficial e localização separados; enunciado; alternativas; texto compartilhado; recursos/fac-símile; instruções gerais; fonte, páginas/regiões, perfil e versão; avisos.
6. Contrato de gabarito: resposta por número e escopo; cargo/código/versão; situação declarada do documento; origem/página/região; anulações, lacunas e conflitos. Nunca sobrescrever conflitos silenciosamente.
7. Manter as APIs usadas por testes/UI enquanto migra seus consumidores. Todo serviço novo precisa de consumidor real e teste do caminho integrado.

Aceite B: roteamento determinístico e testado para reconhecimento correto, ambiguidade, documento incompatível, desconhecido e documento misto. Contagens de perfis e capacidades não se confundem.

## 7. Etapa C — funil de provas

1. Encaminhar a importação de cadernos por inspeção -> perfil -> leitor -> validação. Partir de `servico.py`, `pdf_texto.py`, `parser.py`, `perfis/segmentacao.py`, `pdf_fonte.py` e leitores existentes.
2. Implementar/adaptar os especialistas das três famílias selecionadas. Conter regras específicas no perfil adequado; não adicionar exceções globais por nome de arquivo ou ID de questão.
3. Preservar número físico, ordem, alternativas e contexto entre páginas/colunas. Detectar duplicação, questões fundidas, enunciado incompleto, recurso perdido e troca de ordem.
4. Integrar extração geométrica/fac-símiles para preservar tabelas, fórmulas e figuras quando necessária. Não reutilizar imagem de gabarito como conteúdo da questão.
5. Tratar PDF escaneado por caminho OCR identificado; baixa qualidade vira exceção. Se OCR estiver indisponível, a UI informa a limitação e preserva o lote. Não prometer suporte automático a digitalizações sem caso real validado.
6. Formato desconhecido pode usar diagnóstico/prévia conservadora e seleção assistida; não pode ser certificado como especialista conhecido por fallback silencioso.

Aceite C: em cada documento declarado suportado, comparar todas as questões com referências conferidas na fonte: número, limites, enunciado, alternativas, contexto e apresentação visual. Conferência amostral serve para investigar, não para afirmar fidelidade integral do arquivo. Documento problemático permanece identificado como parcial ou pendente.

## 8. Etapa D — funil de gabaritos

1. Encaminhar leitura por inspeção -> identificação de blocos -> seleção de perfil -> extração -> validação, sem depender da extração do enunciado.
2. Reaproveitar `gabaritos.py`, `gabarito_fonte.py`, `templates.py` e `perfis/gabaritos_*`. Especializar as famílias necessárias aos cadernos escolhidos e preservar os demais leitores existentes.
3. Selecionar explicitamente cargo, código, versão e seções quando o documento tiver várias possibilidades. Mostrar opções reconhecidas em vez de exigir que o usuário adivinhe o identificador técnico.
4. Tratar pares, grades, linhas, listas, C/E, anulações e documentos mistos conforme capacidades declaradas. Lacuna preserva o número; não desloca a resposta seguinte.
5. Usar texto/tabela antes de OCR. Complementação OCR fica restrita ao escopo e não elimina conflito textual nem inventa número a partir da posição.
6. Verificar respostas extraídas contra os quadros originais, incluindo primeira/última resposta, transições de página/bloco e todos os itens das referências dos documentos suportados.
7. Manter colagem manual de sequência como entrada assistida. Não transformá-la em evidência documental automática; a falta de evidência ou confirmação exigida segue pelo fluxo de revisão atual.

Aceite D: mapas esperados idênticos às referências conferidas, seleção correta entre cargos/versões e testes negativos de gabarito trocado, lacunas, anulações, preliminar e conflito.

## 9. Etapa E — associação, verificação e persistência

1. Associar somente após os dois funis, pela identidade documental e números oficiais únicos dentro do mesmo escopo. Os números esperados podem validar cobertura; não devem forçar a extração a produzir os números ou respostas desejados.
2. Diferenciar `correspondente`, `incompleto`, `ambiguo` e `incompativel`. Explicar o motivo e a ação possível. Não usar semelhança do nome do arquivo como comprovação de correspondência.
3. Reutilizar a política de `provenance_service.py`. Revisões humana e automática continuam distintas; rejeição humana, fonte alterada, conflito e gabarito preliminar não são contornados.
4. Extrair da reparação os serviços reutilizáveis necessários para verificar um lote novo pela UI, sem depender do catálogo de samples, de `samples/`, de IDs antigos ou de um script de manutenção. Não chamar reparação destrutiva do acervo ao importar um documento novo.
5. Integrar o verificador real: produzir evidências e certificados apenas quando todos os requisitos atuais forem comprovados. Checagens booleanas preenchidas pelo próprio leitor sem confronto documental não bastam. O usuário deve ver o que foi verificado e o que ficou pendente.
6. Salvar fontes, extrações, questões, versões, alternativas, associação e composição original de forma transacional e recuperável. Se houver migração, validar banco novo, cópia do legado, falha intermediária e restauração; não executar no original sem autorização.
7. Repetir salvar/reabrir o mesmo lote não duplica itens. Nova importação do mesmo arquivo deve reconhecer a duplicidade e oferecer reutilização ou versão explícita, sem fundir provas distintas silenciosamente.
8. Preservar versões usadas em tentativas e histórico; edição posterior gera reavaliação. Revalidar fontes nas operações críticas sem reler todo o PDF desnecessariamente para cada questão.

Contrato obrigatório de integração com a autoridade de liberação:

- Criar um adaptador/orquestrador de lote consumido pela tela, recebendo as saídas dos dois funis, a associação e as decisões explícitas do usuário. Reaproveitar serviços existentes; a UI não deve montar flags de certificado por conta própria.
- Por questão e versão salva, registrar `DocumentoFonte` para cada PDF com hash e localização, `ExecucaoExtracao` com perfil/versão/parâmetros e `EvidenciaQuestao` para conteúdo, contexto/recursos aplicáveis e gabarito. As evidências precisam conter página, região válida, sistema de coordenadas, dimensão/rotação e escopo documental compatível, conforme os contratos atuais.
- O número e a resposta associados precisam ser confrontados com essas fontes. Preservar situação do gabarito e distinguir documento fornecido, preliminar, definitivo, anulado e conflitante conforme a política existente. Não chamar uma seleção do usuário de confirmação de publicação definitiva.
- O verificador deve formar manifesto reproduzível da versão exata, referenciar IDs de evidências e recursos íntegros e chamar `record_automatic_validation` somente quando suas verificações documentais realmente passarem. Não basta gravar o caminho do PDF em `ProvaCadastrada` ou a resposta em `Questao`.
- Se a verificação automática não passar, oferecer revisão humana pela UI com o original aberto na página/região pertinente, evidências pré-carregadas e decisões separadas de conteúdo e gabarito; persistir essas decisões pelos serviços atuais. Nenhuma decisão humana é criada automaticamente.
- Após persistir a transação coerente, executar `assess_version`/`version_is_eligible` nas versões resultantes e devolver ao lote os motivos e a elegibilidade efetiva. Atualizar a tela e a composição a partir desse resultado, não de um status otimista do importador.
- Acrescentar teste integrado que inicia as ações da UI de importação em banco vazio, seleciona os dois PDFs fora de `samples/`, salva, comprova evidências dos dois documentos e `version_is_eligible=True` para os itens comprovados, abre a prova original e finaliza uma tentativa. Um segundo cenário deve falhar na verificação automática e concluir pela revisão humana real da UI; outro deve continuar bloqueado por conflito. Não substituir o adaptador por mock que force aprovação nesses testes de integração.

Aceite E: importação de arquivo fora de `samples/` chega à persistência e liberação comprovada pelo mesmo fluxo de interface; itens não comprovados permanecem revisáveis; rollback, idempotência, fonte alterada e histórico são testados.

## 10. Etapa F — interface completa

1. Evoluir a tela existente em etapas compreensíveis: selecionar prova -> reconhecer/conferir perfil -> selecionar gabarito e seu escopo -> revisar resultado -> salvar e resolver. Os dois funis podem executar em sequência na UI sem perder sua independência técnica.
2. Mostrar os resultados dos dois reconhecimentos e permitir corrigir a seleção quando necessário. Exibir linguagem simples; coordenadas, hashes e IDs de perfil ficam em detalhes técnicos, não como campos obrigatórios do caminho comum.
3. Reaproveitar páginas/regiões e identidade já reconhecidas na conferência assistida. Não pedir abertura e identificação do mesmo documento para cada questão. Decisões em grupo precisam de evidência aplicável a cada item e escopo; não aprovar todo o lote por um clique genérico.
4. Mostrar quantidades separadas: esperadas quando conhecidas, extraídas, com resposta, verificadas, elegíveis e pendentes. Dar acesso às pendências com motivo e correção possível.
5. Oferecer as ações reais após salvar: resolver composição original quando pronta, resolver treino parcial explicitamente identificado, ver pendências e gerar prova aleatória. A composição parcial nunca se apresenta como prova original completa.
6. Manter filtro por disciplina/banca/categoria/tipo e quantidade no gerador; contar apenas itens elegíveis. Conteúdo sem classificação continua utilizável sem filtro; não inventar disciplina para preencher a UI.
7. Executar trabalhos demorados fora da thread da UI com conexões apropriadas, progresso e cancelamento seguro. Resultado antigo não substitui lote novo. Cancelamento/falha não deixa aprovação parcial incoerente.
8. Persistir rascunho recuperável com arquivos/seleções/correções e etapa atual, permitindo fechar e retomar a importação sem perder trabalho. Diferenciar rascunho de conteúdo liberado. Detectar alteração ou ausência de fonte ao retomar.
9. Testar 960×640 e 1240×800, texto longo, recursos visuais e todas as alternativas. Não congelar nem exigir rolagem horizontal para ações essenciais.

Aceite F: o usuário completa o ciclo pela interface, inclusive ambiguidade, correção de exceção, falha recuperável, fechamento/retomada e cancelamento, sem usar scripts ou editar configuração técnica.

## 11. Etapa G — validação de ponta a ponta e regressão

Usar bancos e diretórios de mídia isolados. Testes não podem tocar o banco real. Resolver problemas de isolamento antes de repetir execução em lote.

Checklist obrigatório:

- [ ] Uma importação completa por cada uma das três famílias, iniciada em banco novo e usando arquivo em diretório externo a `samples/`.
- [ ] Documento reservado por família, quando disponível, passa sem ajustes específicos para aquele arquivo. Ausência da referência externa deve ser declarada como limite de generalização; não inventar teste realizado.
- [ ] Prova e gabarito de layouts diferentes são reconhecidos e associados corretamente.
- [ ] Arquivo com vários cargos/versões exige a seleção correta; seleção errada é bloqueada.
- [ ] Documento desconhecido/ambíguo tem diagnóstico e escolha assistida funcionais; não libera por adivinhação.
- [ ] Documento misto e página sem texto não são tratados como se tivessem um único layout íntegro.
- [ ] Lacunas, números repetidos, ordem em colunas e quebra de páginas não deslocam gabarito.
- [ ] Texto compartilhado, imagem, tabela e fórmula aparecem completos na revisão e execução.
- [ ] Gabarito preliminar, conflito e fonte alterada preservam bloqueio e orientam uma ação.
- [ ] Salvar, reabrir e repetir a ação não duplicam questões, fontes ou composição indevidamente.
- [ ] Rascunho da importação sobrevive ao fechamento; fonte alterada na retomada é detectada.
- [ ] Resolver a prova original preserva sua composição/ordem; iniciar, responder, retomar e finalizar calcula o resultado esperado.
- [ ] Gerar um simulado usa somente questões elegíveis, respeita filtros/quantidade e conclui com correção esperada.
- [ ] Depois de editar uma questão, tentativa histórica mantém sua versão e nota original.
- [ ] Falha/cancelamento de extração e de gravação preservam estado recuperável e integridade.
- [ ] Telas permanecem utilizáveis nos dois tamanhos e operações respeitam o orçamento medido de desempenho.
- [ ] Todos os documentos do inventário têm resultado final registrado, incluindo os não suportados, sem regressões silenciosas.
- [ ] Suíte completa final executada em conjunto, sem exclusões para ocultar a falha conhecida; execução isolada não substitui o conjunto.

Comandos iniciais, ajustados apenas ao ambiente comprovado:

```powershell
venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
venv\Scripts\python.exe -m compileall -q src tests
venv\Scripts\python.exe scripts\verificar_regressoes_perfis.py
```

O script de referências históricas pode acusar diferenças pré-existentes ou melhorias reais. Classificar cada diferença por campo e comparar com o PDF; não exigir hash idêntico quando a mudança é intencional e comprovada, nem mudar o manifesto para ocultar defeito. Criar referências novas somente com expectativa conferida e justificativa registrada.

Executar smoke e jornada de UI em banco isolado, com os overrides de caminhos definidos antes de importar módulos. Não usar `python main.py` contra o banco real para uma verificação automática. Testes Qt podem provar navegação e persistência; também renderizar/inspecionar as telas para detectar cortes e sobreposição. Se não houver ferramenta para a validação visual relevante, declarar pendência externa em vez de afirmar aprovação visual.

## 12. Etapa H — revisão independente e documentação

1. Revisar o diff final procurando serviços sem consumidor, caminhos duplicados, acoplamento a samples, regras gerais que invadem especialistas, falhas de transação, thread incorreta, performance e afrouxamento da liberação.
2. Fazer uma revisão distinta da implementação: por agente revisor, quando disponível e conforme regras de equipe, ou por auditoria separada baseada nos critérios e evidências. Corrigir achados válidos e repetir as verificações afetadas.
3. Atualizar README, `docs/IMPORTACAO_HIBRIDA.md` e `docs/PROJECT_BRAIN.md`: arquitetura real, como importar/resolver, perfis efetivamente suportados, limites e comandos isolados. Remover contradições relevantes sem apagar o histórico de decisões.
4. Produzir `docs/RELATORIO_DOIS_FUNIS_ESPECIALIZADOS_LUNA.md` com matriz de aceite, arquivos alterados, corpus e hashes, famílias, resultados por documento, comandos/resultados, evidências de UI, desempenho e limitações. Relatórios volumosos, imagens derivadas, PDFs e bancos ficam em diretórios locais apropriados, fora da entrega de código.
5. Reinspecionar Git e conferir que mudanças pré-existentes, banco, mídias locais, temporários, segredos e reconstrução experimental não foram incorporados. Não descartar arquivos alheios para deixar o Git limpo.

## 13. Portão estrito de conclusão

Antes de encerrar, preencher uma linha por critério: requisito -> implementação/consumidor -> validação executada -> evidência -> estado. Não usar apenas nomes de testes como prova quando falta exercitar a ligação entre módulos.

Só declarar `CONCLUÍDO` quando:

1. os dois funis e a associação estão integrados à UI;
2. as três famílias mínimas e todos os documentos declarados suportados cumprem os respectivos aceites;
3. a verificação/liberação funciona para importações novas sem manutenção por scripts;
4. prova original, treino parcial e simulado aleatório funcionam com correção e histórico preservados;
5. casos negativos, recuperação, migração em cópia quando aplicável, regressões e validação visual relevante foram verificados;
6. falhas conhecidas da execução estão resolvidas ou demonstradas como externas, sem mascaramento;
7. o relatório e a documentação correspondem ao comportamento observado;
8. a auditoria do diff e do estado final foi concluída, com o banco real e trabalho alheio preservados;
9. não existe trabalho necessário, autorizado e executável restante; commit/push, se explicitamente exigidos na execução, estão no estado pedido. Nenhum PR foi aberto.

Se faltar apenas evidência/acesso externo indispensável, usar `CONCLUÍDO COM PENDÊNCIA EXTERNA` somente quando a implementação autorizada estiver entregue e a limitação for descrita precisamente; isso não significa aceite integral. Se faltar implementação ou o fluxo principal não funcionar e depender de algo que o agente não pode resolver, usar `BLOQUEADO`.

Quando uma tentativa falhar, investigar a causa e tentar uma alternativa segura e materialmente diferente. Não repetir indefinidamente nem concluir bloqueio após uma única tentativa. Reportar causa, evidência, alternativas, trabalho preservado e a menor ação externa necessária. Não interromper todo o plano por tarefa independente ainda executável.

Formato final: estado; entregável; famílias/documentos comprovados; evidências dos ciclos original e aleatório; testes e eventuais falhas; preservação de dados; estado real de Git/commit/push; limitações e pendências. Não usar “pronto” se ainda depender de o usuário executar comandos que o Luna poderia ter executado com segurança.

## 14. Prompt de execução para colar no Luna 6.0

> Execute integralmente `docs/PLANO_DOIS_FUNIS_ESPECIALIZADOS_LUNA.md`, respeitando as instruções aplicáveis e a proibição permanente de abrir PR. Esta é uma tarefa de implementação e validação ponta a ponta dos dois funis especializados, sua associação e uso pela interface. Leia o plano completo, mantenha checklist e evidências por critério e continue até a entrega verificável. Preserve alterações pré-existentes e o acervo real; use bancos temporários e cópias consistentes, sem reparar ou reimportar o original. Não pare em plano, módulos, testes unitários, primeira família ou integração parcial. Investigue a falha conhecida em conjunto, complete as três famílias mínimas, valide a prova original e o simulado aleatório pela UI, revise o diff e atualize documentação/relatório. Não crie commit nem faça push sem autorização específica. Se houver impedimento externo indispensável, demonstre-o, tente alternativa segura, complete o trabalho independente e informe o estado correto sem declarar conclusão integral. Use o portão de conclusão do plano antes da resposta final.
