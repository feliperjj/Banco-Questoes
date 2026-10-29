# Cérebro do projeto — Banco de Questões

Este arquivo é a referência operacional antes de qualquer alteração. Ele registra os contratos que precisam continuar verdadeiros, os fluxos que já foram quebrados anteriormente e o roteiro mínimo para evitar novas regressões de usabilidade.

## 1. Mapa rápido

| Área | Entrada principal | Fonte de verdade | Saída |
|---|---|---|---|
| Inicialização | `main.py` | `src/db/database.py` | QApplication, estilo, janela |
| Banco | Peewee | `src/db/models.py` | SQLite em `data/questoes.db` |
| Extração | PDF/DOCX | `src/importador/extrator.py` | texto normalizado |
| Parser | texto | `src/importador/parser.py` | dicionários de questões |
| Catálogo | caminho + cargo/prova | `config/gabaritos.json` | associação rastreável de gabarito |
| Diagnóstico | samples + catálogo | `src/importador/diagnostico.py` | cobertura por caderno |
| Reconhecimento documental | PDF + estrutura | `src/importador/perfis/documentos.py`, `perfis/registro.py` | perfis e evidências por documento |
| Associação documental | caderno + gabarito + escopo | `src/importador/associacao_documental.py` | correspondência, ambiguidade ou pendências |
| Certificação de importação | conteúdo + gabarito + regiões | `src/importador/lote_verificado.py` | questões elegíveis ou pendentes |
| Releitura com IA local | recorte + fonte íntegra + campo | `src/importador/ia_revisao.py`, `ia_runtime.py`, `ia_ocr.py` | leituras e proposta pendente, sem aprovação |
| Lote | questões + tokens | `src/importador/lote.py` | gabaritos/classificação aplicados |
| Persistência | dicionários | `src/models/questoes_repo.py` | questões, provas, tentativas |
| UI | páginas PySide6 | `src/ui/main_window.py` | navegação e interação |
| Estilo | QSS | `src/ui/styles.qss` | aparência global |

Fluxo de importação:

```text
arquivo -> extrair_texto -> parsear_questoes -> revisar/aplicar gabarito
        -> associar documentos -> revisar -> salvar lote verificado -> SQLite
```

O salvamento não libera uma questão por si só: a certificação depende de
evidência física e de escopo suficiente. A implementação dos dois funis está
parcial e os limites medidos estão no relatório
[`RELATORIO_DOIS_FUNIS_ESPECIALIZADOS_LUNA.md`](RELATORIO_DOIS_FUNIS_ESPECIALIZADOS_LUNA.md).

A tela oferece as opções documentais de cargo/código/versão e correção de
leitura por página. Seleção incompatível não aprova respostas. Documentos sem
questões mantêm diagnóstico e rascunho recuperável. Os atalhos após salvar
abrem a prévia da prova/treino parcial ou o gerador; os totais de liberação são
reconciliados com `assess_version`. Renderização de recursos e páginas OCR usa
processo isolado reutilizado durante o lote. Rollback preserva recursos de
importações anteriores e remove somente os arquivos novos da operação.
Reimportação de lote parcial reconhece os hashes e o escopo antes de reutilizar
IDs; rejeição humana não gera versão nova por repetição. Legado sem identidade
suficiente exige conferência e não é fundido nem duplicado automaticamente.

Fluxo de prova:

```text
criar_prova -> listar provas pendentes -> iniciar_tentativa
            -> responder -> finalizar_tentativa -> estatísticas/revisão
            -> prova fica no histórico como concluída
```

## 2. Contratos que não podem quebrar

### Banco e repositório

- `init_db()` deve criar as tabelas de `ALL_MODELS` sem apagar dados.
- `Questao.texto_apoio` mantém passagens compartilhadas separadas do enunciado; `ProvaCadastrada.instrucoes_prova` guarda as orientações gerais da prova de origem.
- A chamada `init_db(caminho_temporario)` é usada pelos testes; não deixar o caminho global preso ao banco de produção entre testes.
- `criar_questao` e `criar_questoes_em_lote` devem salvar alternativas dentro da mesma transação da questão.
- `listar_provas()` sem argumentos significa provas iniciáveis/pendentes.
- `listar_provas(incluir_concluidas=True)` inclui o histórico e cada item deve informar `concluida`.
- Uma prova com tentativa finalizada não pode voltar a ter ação “Iniciar”.
- Novas provas só podem conter questões ativas com gabarito avaliável; questões sem gabarito ou anuladas permanecem no banco, mas não entram na seleção.
- Iniciar novamente uma tentativa aberta reutiliza o mesmo registro; uma prova finalizada é rejeitada também pelo repositório.
- O limite de tempo escolhido na geração deve ser persistido na configuração da prova e aplicado pelo timer da execução; zero significa sem limite.
- A nota usa a quantidade de questões avaliáveis da composição da prova; questões sem resposta contam como não acertadas e questões anuladas ficam fora do denominador, sem erro ou revisão espaçada.
- Uma tentativa finalizada não pode ser finalizada novamente, e respostas devem pertencer à composição daquela prova.
- `ativa=False` é exclusão lógica; não remover silenciosamente registros que possuem respostas, provas ou revisões.

### Parser e importador

- A saída de `parsear_questoes` precisa conter, no mínimo: `enunciado`, `tipo`, `alternativas`, `gabarito`, `confianca`, `disciplina`, `topico`, `banca` e `ano`.
- Texto-base compartilhado fica em `texto_apoio` e orientações gerais em `instrucoes_prova`; nenhum dos dois deve ser concatenado ao campo `enunciado`. Quando o limite não for seguro, mantenha o bloco separado para conferência.
- `tipo` só pode ser `multipla_escolha` ou `certo_errado`.
- Alternativa de múltipla escolha tem `letra` e `texto`; não descartar alternativas por causa de quebra de linha.
- Marcadores de texto-base, paginação, cabeçalho, rodapé e grade de respostas não podem virar questões.
- A ordem numérica oficial deve ser preservada mesmo quando o PDF estiver em duas colunas.
- O parser não deve presumir uma banca para interpretar o documento; heurísticas específicas precisam ser opt-in ou claramente isoladas.
- `parsear_gabarito_em_lote` só aceita tokens inteiros (`A`–`E`, `CERTO`, `ERRADO`), nunca letras no meio de palavras.
- O vínculo usa `questao["numero"]`; índice visual só é fallback quando o documento não fornece número oficial.
- Associações automáticas de gabarito precisam estar confirmadas em `config/gabaritos.json` por caminho relativo, cargo/prova e arquivo de resposta; não associar por semelhança de nome.
- Respostas só são vinculadas pela interseção de números oficiais únicos. Respostas extras, faltantes ou números duplicados devem gerar diagnóstico, nunca deslocamento posicional.
- Texto e tabelas têm precedência sobre OCR. OCR só complementa números esperados ausentes e nunca adiciona números fora do caderno.
- PDF escaneado pode não produzir texto; nesse caso a UI deve oferecer OCR ou colagem manual, sem apagar a prévia existente.

### UI e estado

- A navegação usa os mesmos índices da ordem criada em `MainWindow`: Dashboard 0, Questões 1, Importar 2, Gerar Prova 3, Provas importadas 4, Modo Prova 5, Estatísticas 6, Revisão 7.
- `GeradorProvaPage` gera provas aleatórias; provas cadastradas por importação são iniciadas em `ProvasImportadasPage`, copiando a composição e ordem originais.
- Lotes antigos sem registro em `ProvaCadastrada` são recuperados pelas pausas maiores que um minuto entre os horários sequenciais de criação; preservar essa regra e a ordem crescente dos IDs ao montar essas provas.
- Uma página que exibe dados do banco deve recarregar no `showEvent` ou após uma operação que altera os dados.
- `ExecucaoProvaPage.em_andamento` é a autoridade visual para saber se há tentativa ativa.
- Estado inativo: timer parado, botão de finalizar desabilitado, navegação desabilitada, alternativas vazias e texto neutro.
- Ao finalizar: salvar tentativa, exibir resultado, limpar enunciado/alternativas/timer e voltar ao gerador.
- Ao voltar à aba de execução sem tentativa ativa, não reutilizar conteúdo da prova anterior.
- Questões ou alternativas longas devem quebrar linha e rolar dentro do cartão; nunca impor largura mínima maior que a tela.
- No modo prova, a barra conta questões respondidas, enquanto o rótulo de posição indica a questão aberta. Trocar uma resposta não aumenta o total; navegar restaura a seleção e seu destaque. O resumo é limpo ao sair da tentativa.
- Texto de apoio e instruções gerais aparecem em áreas próprias no modo prova e nunca devem ser concatenados ao enunciado.
- A janela deve iniciar com o Dashboard selecionado e respeitar o mínimo de 960×640.
- A tela de importação deve permanecer utilizável em 960×640, sem rolagem horizontal no formulário de revisão.
- O botão `table-action-button` deve manter pelo menos 132 px de largura e 40 px reais de altura. A linha de prova usa 60 px e o seletor específico `QTableWidget#exam-table::item` não pode herdar padding vertical que comprima o widget.
- Diálogos e mensagens visíveis ao usuário devem estar em português e explicar uma ação possível.
- A revisão guiada usa a lista filtrada de questões, diagnostica em worker e navega sem transportar decisões, escopo ou justificativa da questão anterior. Reabrir a fila sempre reavalia a autoridade do domínio.
- Correções parciais verificam a versão base dentro de transação, alteram apenas o campo selecionado e registram execução própria. A nova versão não herda decisões/certificado/apresentação automática da versão anterior. Tentativas existentes conservam seus snapshots.
- A releitura assistida do recorte propõe texto sem gravar ou aprovar. Fonte ausente/alterada bloqueia a releitura e a aplicação da proposta. Sem texto extraível, a interface orienta correção manual; não presume sucesso por OCR.
- A opção separada **Conferir com IA local** pode confrontar PDF/OCR/IA. Alternativa exige marcador físico único e limites suficientes; ausência, recorte cortado ou delimitação ambígua não chama o modelo. Uma saída `encontrado=true` não comprova fidelidade. Toda proposta permanece sujeita à conferência e ao fluxo normal de correção, nunca a certificado automático. OCR e inferência usam processos próprios canceláveis. Cache de transcrição inclui fonte/imagem/alvo/modelo/configuração e não guarda aprovação. Exemplos de treino exigem confirmação humana explícita, preservando separação por fonte/prova; veja `docs/IA_LOCAL.md`.
- **Triar lista automaticamente** usa só a seleção filtrada, mantém uma sessão de OCR/IA por lote e não grava no acervo. O filtro inicial esconde campos cujo valor salvo foi mantido, sem aprová-los; pendências documentais de enunciado, contexto, imagem e gabarito continuam visíveis. Cancelamento preserva resultados parciais válidos. Alterações de fonte/versão invalidam propostas; salvar sem mudança não apaga pendências. Após correção real, só a questão editada é reanalisada, sem perder as outras linhas.
- O prefetch de elegibilidade aceita IDs e carrega apenas alternativas, versões e fontes relacionadas. A contagem filtrada usa lotes de até 250 e a fila usa até 100; leituras fora do escopo usam o banco normalmente. O snapshot termina com a leitura e nunca envolve gravações.
- Listagem de provas e contagem usam um snapshot de arquivos por operação: hashes continuam reais; caminhos/metadados compartilhados são reaproveitados e reconferidos ao terminar. Mudança durante a leitura impede devolver a contagem. Nada persiste entre operações; criação/início de prova continuam revalidando sem esse snapshot de leitura.
- Apenas versões com revisão humana suficiente ou certificado da regra atual precisam preparar recursos para elegibilidade. Essa triagem só pode descartar; a liberação continua vindo de `assess_version`. A pré-leitura de hashes usa até oito workers de I/O, sem SQLite/PDF/Qt nesses workers.
- Novos recortes documentais usam WebP sem perdas quando Pillow oferece suporte; os pixels precisam coincidir com o original. PNGs já existentes são reutilizados sem trocar caminhos/hashes. A renderização PNG explícita e o fallback sem WebP permanecem disponíveis.
- Botão de uma prova concluída deve ser um estado (`Concluída`), não um botão inativo que parece quebrado.

## 3. Pontos de risco conhecidos

Correção de simulados em 05/09/2026: alternativas horizontais são separadas;
números no meio de frases não abrem novas questões sem evidência de marcador;
o corte de colunas respeita divisórias verticais (linhas e retângulos estreitos).
Comandos repetidos não são removidos como rodapés. Gabaritos com seções Prova I
e Provas II e III exigem seleção exata do bloco. Questões 736, 833 e 7 foram
corrigidas pontualmente com backup; gabaritos 736: A→D, 833: A→B, 7: D mantido.
O critério compartilhado `problemas_estrutura` filtra novas provas e sinaliza
o editor/acervo. Detectou 83 pendências no banco local; não é revisão semântica
completa. Provas já criadas preservam a composição. Rolagem volta ao topo ao
navegar, e V/F e enumerações I–V recebem separação visual sem mudar o banco.

Correção de 05/09/2026: a repetição de “língua” em uma frase não identifica um
cabeçalho. A heurística de línguas exige linha curta iniciada por “Língua”. No
sample administrador-fgv, isso recupera 80 números oficiais e as alternativas
A–E da questão 1. Início em minúscula reduz a confiança do parser e exibe alerta
no editor, sem capitalizar, cortar ou excluir automaticamente. A questão ID 1
do banco local foi corrigida pontualmente, preservando o gabarito e os IDs;
backup: `data/questoes.pre-correcao-q1-20260905-121044.db`. Demais registros
existentes não foram reimportados. Suíte após a correção: 86 testes aprovados.

1. **PDFs variam muito.** Aumentar uma heurística de colunas pode recuperar uma banca e deslocar questões de outra. Toda mudança no extrator deve ter um caso positivo e um caso negativo.
2. **Metadados de banca/disciplina são incompletos.** O parser só reconhece marcas explícitas; nome do arquivo não deve ser confundido com texto extraído sem uma regra documentada.
3. **Tentativa interrompida.** A estrutura suporta tentativa sem `finalizada_em`, e a UI oferece “Retomar prova”, restaurando respostas, índice e tempo ativo da tabela `progresso_tentativas`. Não tratar tentativa aberta como concluída.
4. **QSS é global.** Alterar um seletor genérico pode afetar tabelas, revisão e importação. Prefira `objectName` específico de página.
5. **Dados locais não são descartáveis.** Scripts de reimportação recriam questões e IDs e apagam provas, tentativas, respostas e revisões dependentes. Nunca executar limpeza/reimportação sem pedido explícito e criar backup do banco antes da transação.
6. **Layout mínimo.** O tamanho mínimo deve ser validado em 1240×800 e 960×640; layouts com `minimumSize` implícito podem gerar `QWindowsWindow::setGeometry`.
7. **Cobertura não é só diagnóstico.** Mudanças de gabarito só estão comprovadas quando a contagem prevista pelo diagnóstico também aparece persistida em `Questao.gabarito` após uma reimportação completa.
8. **PySide6 no CI depende do sistema.** O runner Ubuntu precisa instalar `libegl1` antes de importar `PySide6.QtWidgets` e deve executar a suíte com `QT_QPA_PLATFORM=offscreen`.

## 4. Checklist antes de mudar código

### Antes

- Ler esta seção e localizar o contrato afetado.
- Verificar `git status`; alterações existentes pertencem ao usuário.
- Identificar se a mudança toca dados, parser, estado de tela ou somente aparência.
- Para parser, escolher um sample representativo e um caso que antes funcionava.

### Durante

- Fazer a menor alteração que resolve o problema.
- Manter operações de banco transacionais.
- Não mover regra de domínio para callback de UI se ela puder ser testada no repositório/serviço.
- Não usar `showEvent` para iniciar operações destrutivas; ele deve apenas atualizar a tela.
- Não esconder um registro para corrigir um botão: representar o status explicitamente.

### Depois

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall -q src
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; from src.ui.main_window import MainWindow; app=QApplication([]); w=MainWindow(); assert w.minimumWidth() >= 960; print('UI smoke OK')"
```

Para mudanças no importador, também conferir contagem de questões, alternativas, gabaritos e tipos por arquivo. Para mudanças na prova, executar o ciclo criar → iniciar → responder parcialmente → finalizar → voltar ao gerador.

Diagnóstico não destrutivo e reimportação manual autorizada:

```powershell
.venv\Scripts\python.exe scripts\diagnosticar_samples.py
.venv\Scripts\python.exe scripts\reimportar_samples.py
```

O segundo comando é destrutivo para o banco local. Só deve ser executado após pedido explícito e backup de `data/questoes.db`.

## 5. Matriz de regressão manual

| Fluxo | Resultado esperado |
|---|---|
| Abrir o app | Janela abre sem mensagem de geometria e sem tamanho mínimo impossível |
| Importar PDF com alternativas | Todas as questões e alternativas aparecem na prévia |
| Importar gabarito | Quantidade reconhecida é informada; questões sem gabarito permanecem revisáveis |
| Revisar importação em 960×640 | Formulário quebra em linhas verticais e não cria rolagem horizontal |
| Salvar lote | Banco cresce uma vez; alternativas acompanham suas questões |
| Criar prova | Nova prova aparece na tabela com status Pendente |
| Botão Iniciar prova | Área clicável não fica esmagada; botão mantém altura mínima de 40 px |
| Iniciar prova | Questão e alternativas aparecem, timer começa, finalizar fica habilitado |
| Questão longa | Texto quebra/rola sem estourar monitor |
| Finalizar parcialmente | Nota considera todas as questões; prova vira Concluída |
| Voltar para execução | Tela neutra, sem questão antiga e sem timer rodando |
| Voltar para gerador | Prova continua salva como Concluída, sem iniciar novamente |
| Abrir estatísticas/dashboard | Indicadores refletem a tentativa recém-finalizada |
| Revisão | Questão errada entra na fila; questão acertada é reagendada |

## 6. Histórico de regressões já observadas

- Alternativas sumiram porque `QButtonGroup` não existia e os botões não estavam agrupados.
- Questões longas estouraram a largura da janela; a execução agora usa quebra de linha e área rolável.
- Prova finalizada reaparecia como iniciável; o repositório agora distingue pendente de concluída e a UI limpa o estado da execução.
- A prova concluída desaparecia da tabela; o histórico agora permanece visível com status.
- O parser FGV/TRANSPETRO perdeu questões quando a detecção de duas colunas era rígida; a heurística precisa continuar coberta por samples.
- Gabarito em lote podia interpretar letras dentro de palavras; tokens agora precisam estar isolados.
- Nota de prova parcial podia usar somente o número de respostas dadas; o total agora vem da composição da prova.
- Aplicar gabarito depois de salvar uma questão individual podia usar a posição visual errada; a prévia agora usa o índice original da questão.
- Trocar uma questão de múltipla escolha para certo/errado podia deixar alternativas órfãs; a atualização agora as remove.
- O botão “Iniciar prova” ficava esmagado porque o padding global das células reduzia a geometria do widget; a tabela de provas agora possui padding específico, linha de 60 px e botão de 40 px.
- O formulário de importação criava rolagem horizontal em janela mínima; os rótulos agora ficam acima dos campos e o painel cresce dentro da área rolável.
- O CI Linux falhava durante a coleta com `ImportError: libEGL.so.1`; o workflow agora instala `libegl1` e força o backend Qt offscreen.

## 7. Como consultar este cérebro

- **“Que arquivo devo mudar?”** Use o mapa rápido e preserve a direção do fluxo: UI chama serviço/repositório; parser não conhece widgets; banco não conhece UI.
- **“Posso alterar este campo?”** Procure o contrato da saída do parser, modelo em `src/db/models.py` e consumidores em `questoes_repo.py`/páginas.
- **“A mudança melhorou um PDF, mas quebrou outro?”** Compare contagens e tipos nos samples; nunca concluir apenas olhando uma página.
- **“A UI está mostrando dado antigo?”** Verifique `showEvent`, recarga após salvar/finalizar e o estado explícito da página.
- **“Posso apagar dados para testar?”** Só quando solicitado explicitamente; prefira banco temporário nos testes.

## 8. Fontes de verdade

- Modelo e relações: `src/db/models.py`.
- Inicialização/conexão: `src/db/database.py`.
- Regras de persistência e provas: `src/models/questoes_repo.py`.
- Regras de revisão: `src/models/revisao_service.py`.
- Extração: `src/importador/extrator.py`.
- Parsing: `src/importador/parser.py`.
- Contratos de lote: `src/importador/lote.py`.
- Catálogo de associações: `config/gabaritos.json` e `src/importador/catalogo.py`.
- Diagnóstico de cobertura: `src/importador/diagnostico.py` e `scripts/diagnosticar_samples.py`.
- Reimportação transacional: `scripts/reimportar_samples.py`.
- Navegação: `src/ui/main_window.py`.
- Aparência: `src/ui/styles.qss`.
- Testes automatizados: `tests/`.
- Integração contínua e dependências Qt do runner: `.github/workflows/ci.yml`.

## 9. Estado verificado em 23/08/2026

- 23 PDFs de questões processados sem falha técnica.
- 979 questões e 4.100 alternativas persistidas.
- 820 questões com gabarito e 159 sem gabarito: **83,76% de cobertura**.
- Meta de 80% superada em 37 vínculos; ganho de 269 vínculos e 27,48 p.p. sobre os 551/979 históricos.
- Distribuição persistida: A 146, B 158, C 153, D 143, E 109, Certo 41, Errado 50 e Anulada 20.
- Após a reimportação: 0 provas, 0 tentativas, 0 respostas e 0 revisões, conforme a limpeza referencial esperada.
- Backup anterior à reimportação: `data/questoes.pre-reimport-2026-08-23.db` (arquivo local ignorado pelo Git).
- UI validada em 960×640 e 1240×800; botão “Iniciar prova” medido em 142×40 px com o QSS carregado.
- Suíte automatizada: **49 testes passando**.
- Após o refactor de `src/importador/extrator.py`: 23 cadernos, 979 questões,
  996 respostas extraídas e 820 vínculos (**83,76%**), com paridade campo a
  campo confirmada nas rodadas com e sem OCR; suíte automatizada: **50 testes
  passando**.
- Relatórios versionados: `docs/RELATORIO_REIMPORTACAO_SAMPLES.md` e `docs/RELATORIO_DIAGNOSTICO_GABARITOS.md`.

## Melhorias de edição e retomada — setembro de 2026

- `atualizar_questao` altera somente campos presentes no dicionário recebido.
- O editor preserva ausência de gabarito e anulação, permite alternativas A–E e
  valida enunciado, quantidade mínima de alternativas e alternativa correta existente.
- `contar_questoes_elegiveis` compartilha a consulta usada para criar provas.
- `ProgressoTentativa` armazena rascunhos separados de `Resposta`; respostas parciais
  não alteram estatísticas. A finalização apaga o rascunho na mesma transação.
- A retomada restaura respostas, posição e tempo ativo; o tempo fechado é pausado.
- A limpeza manual de samples inclui os rascunhos antes de apagar tentativas.
- Regressões adicionais: `tests/test_melhorias.py`.

## Reimportação de setembro de 2026 — resultado validado

- 23 cadernos, 984 questões, 909 vínculos (92,38%), 75 pendências; 66 testes passaram.
- SQLite conferido por ID/gabarito, integridade e chaves estrangeiras sem falhas.
- Grades T1–T4 exigem tipo explícito; grades horizontais exigem cargo exato e
  números nas células. Cabeçalhos “CARGO 1:” não são grades horizontais.
- FGV/IESES: formato alternativo só substitui o anterior se melhorar a numeração
  de blocos com alternativas, sem consultar gabaritos para escolher segmentação.
- MPO usa o bloco comum da página 9 para a P1; P2 ainda requer seção separada.
- A reimportação agora cria backup automaticamente e aceita `--min-cobertura 90`.
- Evidências e limites: `docs/RELATORIO_MATCH_90.md`. Não confundir cobertura de
  vínculo com precisão aferida por revisão humana integral ou completude do PDF.

## Reforma estrutural e visual — setembro de 2026

- `QuestionEditor` é compartilhado pelo acervo e pela importação; a validação
  centralizada não deve inventar gabaritos nem apagar metadados não exibidos.
- `ImportacaoSession` mantém rascunhos e índices já salvos fora dos widgets.
  Salvar individualmente e depois em lote deve inserir apenas pendentes.
- A classificação e o gabarito usam o número oficial, nunca a posição filtrada.
- As etapas Arquivo/Gabarito/Revisão têm rodapé fixo. O editor rola internamente.
- `BackgroundTask` executa uma leitura por vez e espera a limpeza nativa da
  thread antes de liberar referências Python, necessário no Windows.
- A leitura pode ser cancelada cooperativamente; a etapa atual termina antes de
  descartar o resultado e o cancelamento da gravação reverte a transação. O
  rascunho da importação persiste a etapa e os hashes das fontes, detectando
  arquivos ausentes ou alterados ao retomar.
- Falhas de leitura preservam o lote anterior; falhas de gravação permitem retry.
- `tests/test_ui_reforma.py` cobre navegação, persistência, falhas e ciclo da thread.
  `scripts/verificar_ui_reforma.py` gera capturas isoladas do banco real em duas
  dimensões, respeitando a escala definida por `QT_SCALE_FACTOR`.
- Validação final: 76 testes aprovados; capturas em 960×640 e 1240×800,
  escalas 100%, 125% e 150%. `tests/conftest.py` mantém uma QApplication por
  processo e destrói widgets entre testes para não deixar eventos de telas
  antigas acessarem o banco temporário do próximo caso.


### 2026-09-05 — Perfis de importação e PF 2025

Separação inicial por formato em `src/importador/perfis`; preservar os perfis legados ao adicionar layouts. PF 2025 fornecida: 120 itens salvos, com 96/97 anulados; não reimportar novamente sem verificar duplicatas. Relatório e limites em `RELATORIO_REGRESSOES_FORMATOS.md`. Rodar `python scripts/verificar_regressoes_perfis.py` para comparar conteúdo dos 23 PDFs com referência fixa, além do pytest. Não atualizar o manifesto automaticamente para esconder diferenças. Dois cadernos Embrapa seguem com apenas 2 itens: cobertura não equivale a qualidade.


### 2026-09-07 — Arquitetura híbrida completa por etapas

`extrator.py` virou fachada; PDF, DOCX, segmentação, contexto/grades/texto/OCR de gabarito e coordenação foram separados. A tela usa `servico.importar_caderno` e mostra avisos. Candidatos especializados concorrem com o geral sem consulta a respostas ou restrição de banca no seletor textual.

23 cadernos: 1.042 → 1.239 itens; Embrapa 100+100, FEPESE 50 números oficiais e textos de apoio. Não confundir cobertura com correção integral. Gabaritos antigos tinham vazamento de cargos; Transpetro é multiprova e foi configurada explicitamente como PROVA 1 / Administração. Esta etapa não regravou o banco existente.

A referência atual é `tests/fixtures/perfis_hibridos_manifest.json`; a antiga permanece separada. Verificação passou em 23/23 PDFs. Relatório: `docs/RELATORIO_IMPORTACAO_HIBRIDA.md`; arquitetura e formatos: `docs/IMPORTACAO_HIBRIDA.md`. Acrescentar evidências positivas e negativas ao alterar um perfil; não rebater referências automaticamente para esconder diferenças.

Validação final desta etapa: 145 testes aprovados. Limpeza posterior de fragmento de cabeçalho no perfil Embrapa verificada por testes direcionados e atualização explícita das duas referências afetadas.

### 2026-09-07 — Correção das lacunas identificadas pelo usuário

Nova auditoria dos 23 PDFs: 1.239 → 1.385 questões, todas com sequência 1–N
sem duplicatas. Corrigidos corte de texto-base longo, marcas d'água diagonais,
colunas com alternativas recuadas, números de figuras/frações confundidos com
questões, listas internas A–E e variáveis lógicas confundidas com alternativas.
IADES: 120 itens com contexto; CRF: 55; Transpetro: 70 números distintos.
Os arquivos antes considerados possivelmente parciais continham as questões
iniciais. Não repetir a afirmação de que eram recortes sem conferir a fonte.

164 testes completos aprovados e 16 direcionados após ajuste do falso aviso
em expressão lógica. Referência atual: `perfis_corrigidos_manifest.json`, com
as duas anteriores preservadas. Detalhes: `RELATORIO_CORRECAO_LACUNAS.md` e
`reports/auditoria_lacunas.json`. Fidelidade de imagens/diagramas não é garantida
por contagem completa. Não houve limpeza ou regravação automática do banco.

### 2026-09-24 — Recortes de elementos visuais

Na importação normal de PDFs, questões que citam figuras, gráficos, tabelas ou
quadros recebem um recorte contextual do trecho relevante, em vez da página
inteira. O recorte usa o texto da referência e os limites da questão/coluna;
figuras complexas ainda exigem conferência na fonte. Os arquivos são gravados
com sufixo `_crop` para não substituir imagens antigas já referenciadas pelo
banco local.

### 2026-10-26 — Origem, versões e liberação confiável

- `scripts/diagnosticar_confiabilidade.py` abre o banco em modo somente leitura,
  registra integridade, fontes, imagens, composição, tentativas e casos de
  referência. Número oficial, ordem na prova e ID interno são reportados em
  campos distintos. Um diagnóstico ou hash de extração não certifica conteúdo.
- `DocumentoFonte` identifica arquivos por SHA-256. Nome de arquivo não é
  evidência de banca, cargo, ano ou versão. `EvidenciaQuestao` registra página ou
  identificador documental, coordenadas, dimensões e rotação.
- A importação em lote registra fonte, perfil, parâmetros e avisos da extração
  junto da versão inicial. Anexar nova evidência reabre as revisões de conteúdo e
  gabarito; uma evidência acrescentada não mantém aprovações antigas.
- Cada edição por `questoes_repo` cria um novo `QuestaoVersao` com hash e JSON
  canônico, inclusive alternativas e número oficial. Revisões de conteúdo e de
  gabarito são registros separados e ligados àquela versão. Estado ausente ou
  legado permanece pendente/desconhecido.
- A liberação exige revisão explícita do conteúdo, gabarito definitivo
  confirmado, estrutura válida e toda fonte de evidência ainda íntegra. A regra
  é revalidada na criação e no início de tentativa nova, inclusive no
  repositório; esconder o botão não é controle de domínio.
- `ProvaQuestao` e `Resposta` guardam a versão efetivamente usada. Finalização e
  nota leem o snapshot, nunca o conteúdo atual. Composição ou tentativa legada
  sem snapshot não recebe conteúdo histórico presumido e não é finalizada
  silenciosamente.
- Antes de criar tabelas ou aplicar migração estrutural em banco existente,
  `init_db` cria snapshot via API de backup SQLite, verifica integridade,
  contagens, chaves estrangeiras e restauração em cópia. Falha no backup
  interrompe a inicialização antes da primeira alteração.
- Reimportação não é limpeza: preserve IDs, versões, imagens, tentativas e
  correções manuais. Antes de testar uma aplicação no acervo real, faça backup
  verificável do banco e dos arquivos que o script pode sobrescrever.
- `scripts/reimportar_samples.py` agora produz apenas uma proposta comparativa
  em leitura; recortes são gravados em pasta temporária exclusiva de `reports/`.
  A ordem existente é somente candidata de correspondência, e nenhuma proposta
  é aplicada nem altera histórico.

### 2026-10-26 — Funil de análise, evidência e numeração explícita

- O campo `numero` da extração representa exclusivamente o marcador oficial explícito. `ordem_visual` serve para localizar um bloco sem inventar sua numeração; associação de gabarito exige número e escopo inequívocos.
- `assess_version` é a política explicável de liberação e retorna todos os bloqueios, alertas, estado de conteúdo/gabarito e próxima etapa. `version_is_eligible` permanece apenas como adaptador. A análise é somente leitura.
- Conteúdo, contexto/recurso visual e gabarito são partes de evidência distintas. A conferência direta ao serviço valida IDs, versão, escopo, fonte, página, região, dimensões e rotação; PDF com hash alterado bloqueia. DOCX usa identificador de parágrafo/tabela e não promete paginação estável.
- Snapshot legado sem hash de imagem mantém compatibilidade sem reescrita; o recurso visual continua pendente com integridade desconhecida até nova conferência. Regras de diagnóstico têm versão; resoluções de suspeita guardam justificativa, responsável e fingerprint da evidência.
- A tela de questões oferece ação de análise/conferência. O diálogo mostra a versão congelada, motivos, originais por finalidade, registro de evidência, decisões separadas para conteúdo/gabarito e resolução de suspeitas. PDF rotacionado usa dimensões e rotação lidas da página original.
- Testes usam banco, logs, relatórios, imagens e diretórios temporários próprios; `BANCO_QUESTOES_TEST_MODE=1` recusa caminhos sob `data/` real. Use `-p no:tmpdir` neste ambiente Windows; a fixture `tmp_path` local evita diretórios de sistema inacessíveis.
- Reimportação de samples gera propostas, não aprovação nem sobrescrita. `--stage` persiste em `reports/reimportacao_staging_v2.sqlite3`; `scripts/gerenciar_staging_reimportacao.py` lista, registra decisão humana e aplica somente propostas aprovadas, após revalidar fonte, vínculo e snapshot atual e criar backup consistente. A aplicação cria versão pendente e preserva a anterior.
- Estado, comandos, contagens reais, backup e limitações desta execução: `docs/RELATORIO_FUNIL_ANALISES_LUNA.md`. O diagnóstico JSON/Markdown do acervo é gerado pelo script somente leitura `scripts/diagnosticar_confiabilidade.py`.
- Provas importadas têm consulta por **Ver questões**, inclusive durante a revisão, sem criar tentativa ou salvar respostas. `qtd_com_gabarito`/`qtd_sem_gabarito` medem os valores salvos; `qtd_avaliaveis` mede a liberação pela política. Não rotule questões pendentes de conferência como sem gabarito.
- Fidelidade observada não equivale ao percentual formalmente liberado. Auditoria completa das 70 questões da Transpetro em `docs/AUDITORIA_VISUAL_TRANSPETRO_2026-10-26.md`: 13 falhas materiais, 2 destaques importantes perdidos, 27 com ruído, 28 sem divergência material observada; 70/70 respostas iguais ao arquivo local, 3/4 recortes corretos. Q68 usa imagem de Q70; a capa informa CESGRANRIO, embora o catálogo diga FGV. Essas constatações não aprovam versões nem corrigem o banco automaticamente.

### 2026-10-27 — Reparação documental e liberação automática autorizada

- O usuário autorizou reparar em lote e liberar somente itens aprovados pela verificação automática contra a fonte. O relatório atualizado é `docs/RELATORIO_REPARACAO_AUTOMATICA_2026-10-27.md`; os relatos anteriores representam estados históricos.
- Schema 8 registra certificados automáticos separados das revisões humanas. A regra verifica hashes, catálogo/cargo/tipo, número físico, campos extraídos, contexto integral e pixels dos fac-símiles. Rejeições humanas do mesmo conteúdo não podem ser contornadas reaplicando um lote.
- `scripts/reparar_acervo.py --saida reports/NOME` prepara uma proposta sem alterar o banco. `--aplicar reports/NOME/proposta.json` cria backup SQLite com teste de restauração e aplica em transação; conserva IDs, versões anteriores, composições históricas, tentativas e respostas. `--db` permite validar em cópia; use também `BANCO_QUESTOES_IMAGE_DIR` para isolar os derivados.
- A apresentação usa recortes do PDF, preservando fórmulas, destaques e tabelas. O texto de apoio é separado e pode ter várias regiões. PDFs e PNGs são vinculados por SHA-256; o renderizador trabalha em processo isolado e reutiliza páginas somente dentro do lote.
- Texto digital com sobreimpressão ou marca d'água pode ser normalizado para comparação; os pixels exibidos continuam sendo os originais. A cobertura de liberação não representa probabilidade estatística de acerto.
- A Transpetro foi reparada, incluindo contexto em inglês, fórmula da Q41 e a imagem correta da Q68; sua banca é CESGRANRIO segundo a capa. Provas sem gabarito físico, preliminares, anuladas e itens que não passaram nas verificações continuam com motivos explícitos.
- Até o fechamento da validação não havia commit/push. O usuário autorizou posteriormente commit e push da entrega; nunca abrir PR nesta tarefa.
## Continuação real de 28/10: par EPAGRI/S201

- PDFs originais em Downloads usados como fontes somente leitura. Jornada na
  janela principal em banco isolado: 50 itens e respostas, 46 elegíveis, anulações
  16/18/19/36 bloqueadas. Treino parcial com retomada e aleatória: 46/46 em ambos.
- Leitor físico `perfis/pdf_caixas.py`: caixas de seleção, cabeçalhos repetidos
  removidos antes das colunas, encerramento na redação; recursos preservados nos
  fac-símiles. Limites geométricos não confundem valores internos com marcadores.
- T11/T12 são códigos de cargo. Escopo do gabarito vem do próprio documento,
  independentemente do extrator textual de cadernos; cargos homônimos exigem código.
- `comparacao_fontes.py` comprova cópias por hash ou texto e pixels de todas as
  páginas. A autoridade recompõe a prova de equivalência antes da certificação;
  o caminho não substitui identidade impressa para pares novos desconhecidos.
- A prévia conserva o aviso de treino parcial ao navegar. Widgets de recortes e
  alternativas anteriores são ocultados antes da exclusão adiada.
- Esse caso é real, mas já pertence ao conteúdo conhecido da coleção. O relatório
  agora registra as três famílias reais; generalização cega permanece sem comprovação.

## Fechamento real dos dois funis — 28/10

Três famílias passaram pela interface em bancos isolados: EPAGRI/S201 (50 itens/46 elegíveis), Morungaba com rótulos QUESTÃO (40/38) e EMBRAPA/Sistemas C/E com texto compartilhado (100/94). Os itens restantes são anulados. Composições completas preservadas; treinos parciais com retomada e simulados aleatórios concluídos com 46/46, 38/38 e 94/94.

Dataprev tipo 4: 70 respostas conferidas no quadro da página 14; tipo 3 recusado. O gabarito é preliminar e a identidade impressa é insuficiente para certificação independente. São 70 questões para conferência e zero elegíveis, sem simulado. O código no nome do arquivo não substitui comprovação documental. Permanecem necessários gabarito definitivo e identidade verificável/revisão humana efetiva.

Apoios relativos e recursos compartilhados foram preservados. Cabeçalhos/rodapés saem do corpo mantendo banca/ano documentais; números internos não sobrescrevem a disciplina de questões anteriores. O relatório de execução reúne evidências, limites e validações finais. Os três pares conhecidos e a Dataprev ajustada não comprovam generalização cega. OCR de digitalização real também não foi comprovado.


## Gabaritos fornecidos para estudo — 29/10/2026

O usuário confirmou o uso dos gabaritos fornecidos, inclusive preliminares. O rótulo preliminar não é impedimento absoluto: pares aceitos em `config/gabaritos_estudo.json`, identificados por chave de catálogo e hashes dos PDFs, podem receber certificação documental automática. O status preliminar permanece registrado; respostas ainda exigem vínculo e extração corretos, e vetos humanos, conflitos e anulações continuam bloqueados. Esta decisão substitui a exigência anterior de gabarito definitivo para esses pares. Detalhes em `docs/GABARITOS_ESTUDO.md`.
