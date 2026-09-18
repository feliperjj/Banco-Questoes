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
| Lote | questões + tokens | `src/importador/lote.py` | gabaritos/classificação aplicados |
| Persistência | dicionários | `src/models/questoes_repo.py` | questões, provas, tentativas |
| UI | páginas PySide6 | `src/ui/main_window.py` | navegação e interação |
| Estilo | QSS | `src/ui/styles.qss` | aparência global |

Fluxo de importação:

```text
arquivo -> extrair_texto -> parsear_questoes -> revisar/aplicar gabarito
        -> classificar -> criar_questoes_em_lote -> SQLite
```

Fluxo de prova:

```text
criar_prova -> listar provas pendentes -> iniciar_tentativa
            -> responder -> finalizar_tentativa -> estatísticas/revisão
            -> prova fica no histórico como concluída
```

## 2. Contratos que não podem quebrar

### Banco e repositório

- `init_db()` deve criar as tabelas de `ALL_MODELS` sem apagar dados.
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

- A navegação usa os mesmos índices da ordem criada em `MainWindow`: Dashboard 0, Questões 1, Importar 2, Gerar Prova 3, Modo Prova 4, Estatísticas 5, Revisão 6.
- Uma página que exibe dados do banco deve recarregar no `showEvent` ou após uma operação que altera os dados.
- `ExecucaoProvaPage.em_andamento` é a autoridade visual para saber se há tentativa ativa.
- Estado inativo: timer parado, botão de finalizar desabilitado, navegação desabilitada, alternativas vazias e texto neutro.
- Ao finalizar: salvar tentativa, exibir resultado, limpar enunciado/alternativas/timer e voltar ao gerador.
- Ao voltar à aba de execução sem tentativa ativa, não reutilizar conteúdo da prova anterior.
- Questões ou alternativas longas devem quebrar linha e rolar dentro do cartão; nunca impor largura mínima maior que a tela.
- A janela deve iniciar com o Dashboard selecionado e respeitar o mínimo de 960×640.
- A tela de importação deve permanecer utilizável em 960×640, sem rolagem horizontal no formulário de revisão.
- O botão `table-action-button` deve manter pelo menos 132 px de largura e 40 px reais de altura. A linha de prova usa 60 px e o seletor específico `QTableWidget#exam-table::item` não pode herdar padding vertical que comprima o widget.
- Diálogos e mensagens visíveis ao usuário devem estar em português e explicar uma ação possível.
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
- Fechar durante a leitura é bloqueado; descartar revisão não salva exige
  confirmação. Rascunhos de importação não sobrevivem ao encerramento do processo.
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
