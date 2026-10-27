# Plano de implementação — máxima confiabilidade possível

Data: 26/10/2026. Destinatário: modelo Luna.

## 1. Objetivo e resultado esperado

Reduzir erros silenciosos de conteúdo, contexto, imagens e gabarito. Toda questão liberada para uma nova prova deve ter origem rastreável, versão preservada, conteúdo conferido e gabarito confirmado. Ambiguidade deve resultar em pendência, nunca em aprovação presumida.

Não prometer precisão de 100%. Mostrar separadamente o que foi extraído, validado automaticamente e conferido por pessoa. A conferência humana e a integridade do documento-fonte também possuem limites.

Decisão de produto: combinar conteúdo estruturado com consulta permanente ao original. Questões complexas podem ser apresentadas pelo original completo ou por recortes conferidos. Apenas gerar um recorte não comprova que ele está completo.

## 2. Regras de execução para o Luna

- Ler instruções aplicáveis, README.md, docs/PROJECT_BRAIN.md, docs/IMPORTACAO_HIBRIDA.md e docs/AUDITORIA_PROVAS_MANUAL.md antes de editar.
- Executar em etapas sequenciais. Cada etapa termina com diff revisado, evidências e pendências explícitas; testes verdes não substituem entrega integrada.
- Não criar, abrir ou solicitar pull request. Não fazer push, commit, rebase ou merge sem autorização correspondente. A entrega deste plano é código local validado e relatório das pendências humanas.
- Verificar branch e working tree antes de editar. Na preparação deste plano, a branch era main, data/questoes.db estava modificado e docs/AUDITORIA_PROVAS_MANUAL.md estava não versionado. Reinspecionar; não descartar nem incluir esses dados automaticamente na entrega.
- Autorização do usuário em 26/10/2026: pode usar o banco original e fazer reimportações para testar o resultado, desde que faça backup antes. Não pedir novamente essa autorização dentro deste escopo. Testes automatizados de falha/migração continuam usando bancos temporários.
- Antes da primeira mutação no banco original, criar backup SQLite consistente (API de backup do SQLite, contemplando WAL), verificar integridade e testar abertura/restauração em cópia. Preservar também imagens e documentos locais que possam ser alterados pela reimportação; não sobrescrever esses arquivos sem cópia recuperável. Registrar caminho do backup e contagens iniciais. Impedir gravações concorrentes do app durante a aplicação. Se o backup falhar, não alterar o original.
- Preferir reimportação transacional e idempotente, com comparação antes/depois. Esta autorização não implica apagar todo o banco, excluir histórico ou descartar correções manuais; adaptar scripts destrutivos antes de usá-los. Guardar o backup inicial até o usuário decidir removê-lo.
- Nunca usar o gabarito para escolher o texto extraído. Nunca preencher explicações, respostas ou trechos ausentes por suposição.
- Alterações já existentes e o histórico de tentativas devem ser preservados. Conferências que exigem uma pessoa são pendências externas; o agente não pode registrá-las como realizadas por humano.

## 3. Etapa 0 — diagnóstico e referência verificável

Áreas: scripts de diagnóstico, tests/fixtures e documentação.

1. Inventariar acervo em leitura: provas, questões, alternativas, contextos, imagens, gabaritos, vínculos, tentativas e fontes presentes/ausentes.
2. Identificar o ambiente Python realmente disponível; o checkout usa venv, enquanto parte do README cita .venv.
3. Executar a suíte existente e registrar falhas preexistentes. Auditar as regras atuais de elegibilidade e todos os caminhos de início, retomada e revisão.
4. Criar diagnóstico sem mutação e relatório JSON/Markdown com IDs, posições na prova e evidências. Não confundir número oficial, ordem visual e ID interno.
5. Montar uma referência dos casos conhecidos confrontando os PDFs disponíveis. Se o PDF faltar, registrar ausência, sem certificar a correção.

Casos prioritários observados:

- Transpetro Q10: alternativa E com 3.975 caracteres e texto de inglês agregado.
- Transpetro Q11–20: contexto de inglês ausente no campo de apoio.
- Transpetro Q1–8 e Q15: classificações suspeitas/incompatíveis com conteúdo.
- Transpetro Q8, Q20, Q68 e Q70: resíduos de rodapé, rascunho ou seção.
- Transpetro Q24, Q25 e Q36: alternativas longas legítimas; são contraprovas para evitar bloqueio apenas por comprimento.
- Transpetro Q41: conferir fórmula no original; não presumir que a sequência textual preserva sua notação.
- Transpetro Q55, Q57, Q68 e Q70: conferir tabelas, imagens e limites dos recortes.
- IBFC 2024, Analista Produção/Redes/Suporte de Banco de Dados/Sistemas, Q1: referência a texto sem apoio exposto na árvore de acessibilidade. Confirmar causa na fonte e no banco; a captura visual falhou.

Aceite: diagnóstico reproduzível sem alterar o acervo; lista de fontes ausentes; referência com status de conferência explícito. Os casos acima são observações, não um conjunto já certificado de respostas esperadas.

## 4. Etapa 1 — origem e versões imutáveis

Áreas: src/db/models.py, migrations.py, database.py; repositórios e importador.

Implementar entidades coerentes com o modelo existente para:

- Documento-fonte: hash SHA-256, tipo, identificação da prova/cargo/ano/versão, localização e disponibilidade. Identificação bibliográfica não deve ser inferida como certeza pelo nome do arquivo.
- Versão da questão: número oficial, conteúdo completo, alternativas, contextos vinculados, recursos visuais e hash do conteúdo. Edição cria nova versão; não sobrescreve versão já utilizada.
- Evidência por parte: documento, página e coordenadas, inclusive múltiplas regiões/páginas; trechos compartilhados precisam de vínculo explícito. Registrar sistema de coordenadas, dimensões e rotação da página.
- Execução da extração: versões do extrator/perfil, parâmetros relevantes e diagnósticos.
- Revisões e gabarito versionados: evidência, decisão, responsável declarado, data, justificativa e versão aprovada.
- Composição e tentativas vinculadas à versão exata utilizada. A consulta de resultados antigos não pode adotar silenciosamente conteúdo ou gabarito novos.

Para DOCX sem paginação estável, usar identificadores de parágrafo/tabela e manter arquivo original. A primeira entrega de recortes pode ser restrita a PDF, com limitação explícita para DOCX.

Migração aditiva e transacional. Usar backup SQLite consistente, adequado a conexões abertas/WAL, e testar restauração. Legado recebe origem/revisão desconhecida, nunca aprovação automática. Se não houver versão histórica disponível, identificar o snapshot como estado na migração, sem alegar reconstrução do passado.

Aceite: migração em banco novo e legado sem perda de registros; integridade e chaves estrangeiras válidas; edição posterior não modifica tentativa anterior; fonte alterada/ausente é detectada.

## 5. Etapa 2 — política única de liberação

Áreas: serviços/repositórios, geração aleatória, provas importadas, execução e revisão.

Separar revisão de conteúdo e de gabarito. Estados sugeridos para conteúdo: não revisado, pendente, conferido, rejeitado. Para gabarito: desconhecido, preliminar, definitivo confirmado, anulado, conflitante.

Uma nova prova normal só utiliza versões com conteúdo conferido, evidência acessível e íntegra, estrutura válida e gabarito definitivo confirmado para a versão/cargo corretos, sem bloqueadores. Questões anuladas continuam fora da avaliação. Gabarito preliminar pode ser consultado com aviso, mas não recebe a mesma liberação.

A política deve existir no domínio e valer para todos os pontos de entrada, não apenas para botões. Revalidar na criação e no início de tentativa nova. Tentativa já iniciada usa seu snapshot; se surgir erro crítico, avisar e permitir preservar/suspender a tentativa, sem trocar respostas nem finalizar automaticamente. Histórico continua acessível e itens afetados são sinalizados.

Alterar conteúdo, gabarito ou evidência invalida a aprovação da nova versão. Não herdar aprovação de conteúdo diferente. Documentar a mudança dos contratos anteriores em PROJECT_BRAIN.md.

Aceite: testes de tentativa de contornar a UI falham com mensagem clara; legado fica pendente; simulados antigos não perdem composição; nenhuma correção automática muda nota histórica.

## 6. Etapa 3 — segmentação e detecção de inconsistências

Áreas: src/importador/servico.py, pdf_texto.py, imagens.py, perfis/*, parser.py e validacao.py.

1. Propagar regiões e origem durante a extração, antes de perder a geometria na concatenação de texto.
2. Separar questão, alternativas, textos compartilhados, instruções e mudanças de seção. Contexto atravessando páginas precisa permanecer completo e vinculado ao intervalo correto.
3. Corrigir os casos reproduzidos em testes, sem regras por ID local nem acesso ao gabarito para escolher candidatos.
4. Registrar diagnósticos por código, severidade, evidência e ação: contexto ausente; alternativa desproporcional; numeração ambígua; resíduo; fórmula/tabela possivelmente degradada; imagem faltante; conflito de cargo/versão.
5. Diferenciar erro estrutural comprovado de suspeita. Comprimento, palavras como “texto” e números finais isoladamente não autorizam alteração ou rejeição definitiva. Revisão pode resolver suspeitas com justificativa registrada; conflitos objetivos devem ser corrigidos.
6. OCR somente quando necessário, preservando origem e divergências. Segunda extração pode sinalizar conflito, mas concordância não equivale a aprovação humana.

Não trocar toda a arquitetura ou adicionar IA/serviços externos inicialmente. Avaliar outra biblioteca apenas em benchmark com os mesmos PDFs, medindo erros introduzidos, recursos e reprodutibilidade. Novas dependências exigem documentação e atualização controlada do ambiente.

Aceite: Q10 deixa de absorver o texto seguinte; Q11–20 recebem contexto correto; alternativas longas válidas permanecem completas; regressões dos perfis passam e diferenças de referência são explicadas, não aceitas automaticamente.

## 7. Etapa 4 — conferência lado a lado e apresentação fiel

Áreas: QuestionEditor, importação, acervo, ExecucaoProvaPage e recursos compartilhados de visualização.

Criar acesso à origem na revisão e na execução: página/recorte com zoom, deslocamento e navegação pelas partes da questão e texto-base. Em janela estreita, usar abas ou alternância, preservando acesso a todo o conteúdo.

Na revisão: mostrar extraído e original; permitir corrigir limites do recorte, vínculo do contexto e campos; exigir decisão explícita para conteúdo e gabarito. Mostrar o que será aprovado e sua versão. Não aprovar automaticamente ao salvar, navegar ou concluir extração.

Na prova: oferecer apresentação pelo original conferido e conteúdo estruturado conferido. O original não pode exibir gabaritos, comentários de correção ou conteúdo de arquivo de respostas. Questões adjacentes e trechos incompletos devem ser sinalizados na conferência do recorte.

Arquivos ausentes ou adulterados geram aviso e bloqueio adequado, nunca área vazia silenciosa. Recortes derivados têm origem e limites registrados; usar original íntegro para regeneração.

Aceite: conferir questões curtas, longas, apoio multipágina, tabela e fórmula em 960×640 e 1240×800, escalas 100%, 125% e 150%; todo conteúdo e todas as alternativas acessíveis; nenhuma resposta revelada. Capturas offscreen ajudam, mas não substituem inspeção humana de fidelidade. Sem ferramenta de captura funcional, registrar pendência visual.

## 8. Etapa 5 — recuperação controlada do acervo

Produzir proposta de reparação em simulação: versão anterior e proposta, diferença por campo, origem, motivo, conflitos e tentativas afetadas. Não sobrescrever aprovações/correções manuais com reextração automática.

A aplicação e as reimportações de teste no banco original estão autorizadas pelo usuário, após backup consistente com restauração testada. Usar processamento transacional e idempotente, novas versões pendentes e preservação de IDs relacionais, composições e snapshots históricos. Interrupção não pode produzir aplicação parcial incoerente. Comparar contagens, conteúdo, contextos, alternativas, imagens e gabaritos antes/depois; registrar regressões e não tratar aumento de cobertura como prova de fidelidade.

Aceite: segunda execução não duplica questões/versões; histórico permanece igual; correções propostas passam por conferência antes de novas provas; relatório do que mudou e do que permaneceu pendente.

## 9. Validação e auditoria final

- Testes de migração, rollback e restauração; fonte e imagem ausentes/alteradas; versão nova invalidando revisão; isolamento das tentativas; gabaritos de cargos/versões distintos; anulações e conflito preliminar/definitivo.
- Testes de integração usando os caminhos reais: importar → salvar pendente → conferir conteúdo e gabarito → liberar → gerar/iniciar → responder/retomar → finalizar → consultar histórico → editar nova versão → conferir histórico inalterado.
- Executar suíte completa com banco temporário e compileall. Rodar scripts/verificar_regressoes_perfis.py com os PDFs disponíveis e explicar quais referências esse script realmente verifica. Não atualizar manifests apenas para fazer testes passarem.
- Manter referência separada conferida contra o original; incluir contraprovas de números legítimos em alternativas, longas alternativas válidas, duas colunas, múltiplos cargos e contextos multipágina.
- Revisar diff e estado final; não incluir bancos, backups, PDFs locais, logs ou artefatos temporários na entrega de código.

Métricas: questões extraídas; fontes rastreáveis; itens conferidos por pessoa; gabaritos confirmados; itens liberados; pendências; erros encontrados na revisão. A taxa de extração não pode aparecer como “precisão”. Sem revisão integral, métricas por amostra devem identificar tamanho, seleção e limites da amostra.

## 10. Critério de conclusão e ordem de execução

Executar 0 → 1 → 2 → 3 → 4 → 5 → auditoria. Entregar primeiro o mecanismo de confiança; depois recuperar o acervo com a autorização já concedida e o backup obrigatório. Não liberar legado automaticamente para contornar a queda inicial na quantidade de questões elegíveis.

Conclusão técnica exige funcionalidades integradas e validações comprovadas. O acervo só pode ser declarado conferido quando a revisão humana correspondente tiver ocorrido. Enquanto isso, entregar “implementado e validado tecnicamente; conferência humana pendente”, com quantidades e itens restantes.

Não fazem parte deste plano: redesign cosmético amplo, gamificação, IA gerando respostas, alteração de regras de pontuação e publicação remota.

## Prompt de execução para o Luna

Implemente sequencialmente o plano docs/PLANO_CONFIABILIDADE_MAXIMA.md no Banco-Questões. Comece pela Etapa 0 e preserve mudanças locais. O usuário autorizou usar o banco original e fazer reimportações de teste, desde que haja backup prévio consistente e verificado. Execute essa validação no acervo real quando a implementação estiver pronta; não solicite novamente a autorização já concedida. Preserve histórico, correções manuais e arquivos associados, registre diferenças antes/depois e evite gravações concorrentes. Testes automatizados de falhas devem usar bancos temporários. Prossiga nas etapas técnicas autorizadas, validando integração e revisando o diff a cada etapa. Não crie PR e não faça commit/push. Não certifique revisão humana nem fidelidade que não foi verificada. Documente evidências, localização do backup, falhas preexistentes, decisões e pendências externas. O objetivo é máxima confiabilidade possível, mesmo que isso reduza a quantidade inicialmente liberada de questões.
