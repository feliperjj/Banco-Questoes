# Cérebro do projeto — Banco de Questões

Este arquivo é a referência operacional antes de qualquer alteração. Ele registra os contratos que precisam continuar verdadeiros, os fluxos que já foram quebrados anteriormente e o roteiro mínimo para evitar novas regressões de usabilidade.

## 1. Mapa rápido

| Área | Entrada principal | Fonte de verdade | Saída |
|---|---|---|---|
| Inicialização | `main.py` | `src/db/database.py` | QApplication, estilo, janela |
| Banco | Peewee | `src/db/models.py` | SQLite em `data/questoes.db` |
| Extração | PDF/DOCX | `src/importador/extrator.py` | texto normalizado |
| Parser | texto | `src/importador/parser.py` | dicionários de questões |
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
- Diálogos e mensagens visíveis ao usuário devem estar em português e explicar uma ação possível.
- Botão de uma prova concluída deve ser um estado (`Concluída`), não um botão inativo que parece quebrado.

## 3. Pontos de risco conhecidos

1. **PDFs variam muito.** Aumentar uma heurística de colunas pode recuperar uma banca e deslocar questões de outra. Toda mudança no extrator deve ter um caso positivo e um caso negativo.
2. **Metadados de banca/disciplina são incompletos.** O parser só reconhece marcas explícitas; nome do arquivo não deve ser confundido com texto extraído sem uma regra documentada.
3. **Tentativa interrompida.** A estrutura suporta tentativa sem `finalizada_em`, mas a UI ainda não oferece retomada explícita. Não tratar tentativa aberta como concluída.
4. **QSS é global.** Alterar um seletor genérico pode afetar tabelas, revisão e importação. Prefira `objectName` específico de página.
5. **Dados locais não são descartáveis.** Scripts de reimportação podem recriar questões e IDs. Nunca executar limpeza/reimportação sem pedido explícito.
6. **Layout mínimo.** O tamanho mínimo deve ser validado em monitor 1920×1080 e em janela reduzida; layouts com `minimumSize` implícito podem gerar `QWindowsWindow::setGeometry`.

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

## 5. Matriz de regressão manual

| Fluxo | Resultado esperado |
|---|---|
| Abrir o app | Janela abre sem mensagem de geometria e sem tamanho mínimo impossível |
| Importar PDF com alternativas | Todas as questões e alternativas aparecem na prévia |
| Importar gabarito | Quantidade reconhecida é informada; questões sem gabarito permanecem revisáveis |
| Salvar lote | Banco cresce uma vez; alternativas acompanham suas questões |
| Criar prova | Nova prova aparece na tabela com status Pendente |
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
- Navegação: `src/ui/main_window.py`.
- Aparência: `src/ui/styles.qss`.
- Testes automatizados: `tests/`.
