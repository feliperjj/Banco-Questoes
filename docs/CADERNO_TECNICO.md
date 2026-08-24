# Caderno técnico — Banco de Questões

Este documento registra a história, o conceito, a montagem e as decisões técnicas do Banco de Questões. Ele serve como memória de engenharia: explica não apenas o que existe, mas por que cada parte foi construída dessa forma.

O documento deve evoluir junto com o código. Quando uma decisão importante mudar, atualize a seção correspondente e acrescente uma nota no histórico.

## 1. Conceito do projeto

### 1.1 Visão

O Banco de Questões é um ambiente local de estudo construído a partir de provas reais. O usuário fornece documentos que já possui; o sistema transforma esse material em unidades de estudo que podem ser pesquisadas, filtradas, resolvidas e revisadas.

O conceito central é:

```text
documento bruto → conhecimento estruturado → prática repetível → feedback
```

### 1.2 Problema de produto

O trabalho de preparação costuma ser fragmentado em PDF, editor de texto, planilha, site de questões e anotações. Isso gera três custos:

- preparação manual do material;
- dificuldade de reutilizar a mesma prova em filtros diferentes;
- ausência de histórico consistente de erros e evolução.

O sistema reduz esses custos mantendo os dados localmente e oferecendo um fluxo integrado de importação, conferência, prova e revisão.

### 1.3 Princípios

1. **Automatizar sem esconder incerteza.** A extração é heurística; a interface mostra confiança e permite correção.
2. **Preservar o material original.** O texto é normalizado para processamento, mas o usuário decide o que será salvo.
3. **Separar camadas.** Parser não conhece UI; banco não conhece widgets; telas orquestram serviços.
4. **Falhar de forma recuperável.** Uma falha de extração não deve apagar a prévia nem corromper o banco.
5. **Manter o estudo local.** O banco não depende de servidor, conta ou conexão de rede.
6. **Preferir histórico explícito.** Uma prova concluída permanece visível como concluída, em vez de desaparecer ou parecer iniciável.

### 1.4 Fora do escopo atual

- sincronização entre computadores;
- login, usuários e colaboração;
- edição avançada de PDF;
- garantia de interpretação perfeita para qualquer banca;
- retomada visual de tentativas interrompidas;
- distribuição de conteúdo protegido por direitos autorais.

## 2. Evolução do projeto

O histórico abaixo resume as fases visíveis no Git. Os hashes são referências do repositório e não substituem a leitura do diff.

| Fase | Evidência no histórico | Resultado |
|---|---|---|
| Base do produto | `feat: melhora telas de prova revisao e estatisticas` | Primeira organização das telas de estudo, prova, estatísticas e revisão |
| Dashboard | `feat: melhora dashboard de estudos` | Indicadores e ações de entrada para o estudo |
| Banco de questões | `feat: adiciona categorias as questoes` | Disciplina, categoria/tópico e filtros reutilizáveis |
| Geração | `feat: filtra tipo de questao ao gerar prova` | Provas por tipo, disciplina e categoria |
| Gabaritos | `fix: importa gabaritos por cargo` e `fix: corrige sinal do importador de gabarito` | Suporte a gabaritos com cargos e formatos diferentes |
| Parser resiliente | `fix: reconhece marcadores de questao corrompidos` | Tolerância a caracteres substitutos e marcadores inconsistentes |
| Classificação em lote | `feat: classifica questoes em blocos` | Edição de faixas sem repetir a mesma ação questão a questão |
| Documentação | `docs: melhora readme e adiciona telas` e `docs: adiciona aviso sobre formatos de pdf` | Onboarding e explicitação dos limites do parser |
| Extração avançada | `Fortalece importacao de PDFs e gabaritos` | Colunas, marcas d’água, OCR, tabelas e amostras reais |
| Estabilidade da prova | `Fortalece importacao de PDFs e estabilidade das provas` | Alternativas responsivas, estado da prova, histórico e regressões de UI cobertas |

### 2.1 O que motivou a fase de estabilização

O projeto passou por uma sequência de regressões de usabilidade: alternativas que não apareciam, questões longas que estouravam o monitor, prova finalizada que reaparecia, histórico que desaparecia e parser que funcionava para um layout e falhava em outro.

A resposta arquitetural foi explicitar contratos e estados:

- `ExecucaoProvaPage.em_andamento` passou a controlar o estado visual da execução;
- provas concluídas ganharam um status explícito;
- textos longos passaram a usar quebra de linha e área rolável;
- o parser ganhou testes de layouts mistos;
- a camada de domínio passou a proteger finalização duplicada e respostas fora da prova.

## 3. Como o projeto é montado

### 3.1 Entrada da aplicação

`main.py` executa quatro tarefas:

1. configura logs;
2. inicializa o banco;
3. cria o `QApplication` e carrega o QSS;
4. monta e exibe `MainWindow`.

A janela principal cria a barra lateral e um `QStackedWidget`. A ordem das páginas é um contrato utilizado por ações rápidas e navegação:

| Índice | Página |
|---:|---|
| 0 | Dashboard |
| 1 | Questões |
| 2 | Importar |
| 3 | Gerar Prova |
| 4 | Provas / Modo Prova |
| 5 | Estatísticas |
| 6 | Revisão |

### 3.2 Camadas

```text
UI (PySide6 + QSS)
  ↓ chama
Serviços/repositórios (regras do domínio e consultas)
  ↓ usa
Modelos Peewee
  ↓ persiste em
SQLite
```

O importador é uma cadeia paralela que termina no repositório:

```text
extrator → parser → operações em lote → criar_questoes_em_lote
```

### 3.3 Responsabilidade dos módulos

| Módulo | Responsabilidade | Não deve fazer |
|---|---|---|
| `src/db/database.py` | abrir/configurar SQLite e criar tabelas | decidir regra de prova ou formatar widget |
| `src/db/models.py` | representar tabelas e relações | interpretar PDF |
| `src/importador/extrator.py` | PDF/DOCX, texto, colunas, OCR | salvar diretamente no banco |
| `src/importador/parser.py` | texto em dicionários de questões | acessar Qt ou SQLite |
| `src/importador/lote.py` | validar tokens e aplicar blocos | conhecer arquivos PDF |
| `src/models/questoes_repo.py` | persistência, filtros, provas e métricas | criar layouts de tela |
| `src/models/revisao_service.py` | agenda de revisão e atualização de dificuldade | controlar navegação |
| `src/ui/pages/*.py` | entrada, feedback e renderização | duplicar regras SQL |
| `src/ui/styles.qss` | aparência global e seletores específicos | conter regra de domínio |

## 4. Pipeline de importação

### 4.0 Integridade da prova

Uma prova avaliativa só é composta por questões ativas com gabarito válido. O
vocabulário é centralizado em `src/importador/validacao.py`. A resposta
`Anulada` é preservada para auditoria, mas não reduz a nota, não gera erro e
não entra na revisão espaçada. O catálogo versionado em
`config/gabaritos.json` exige evidência explícita e não usa aproximação de
cargo ou prova.

### 4.1 Extração

`extrair_texto()` escolhe o adaptador pela extensão:

- PDF: `pdfplumber`;
- DOCX: `python-docx`;
- outros formatos: erro explícito.

No PDF, o extrator:

1. remove caracteres rotacionados que não pertencem ao fluxo principal;
2. coleta palavras e coordenadas;
3. identifica indícios de duas colunas;
4. extrai cabeçalho e corpo em ordem adequada;
5. normaliza hífens, espaços e linhas;
6. remove marcas d’água e linhas repetidas;
7. entrega texto para o parser.

A decisão de coluna precisa ser conservadora. Uma página de instruções pode ocupar a largura inteira e parecer duas colunas apenas pela distribuição de palavras. Por isso a heurística considera linhas confinadas, quantidade e separação central.

### 4.2 Parser

`parsear_questoes()` trabalha com três problemas simultâneos:

- localizar o início de cada questão;
- separar enunciado e alternativas;
- ignorar front matter, textos-base, grades e números de referência.

O parser reconhece marcadores nomeados (`QUESTÃO 1`), marcadores numéricos e itens certo/errado sem alternativa. Quando existem alternativas, blocos sem opções são descartados para evitar que textos-base virem questões falsas.

Cada questão devolvida possui o contrato:

```python
{
    "enunciado": str,
    "tipo": "multipla_escolha" | "certo_errado",
    "alternativas": list[dict] | None,
    "gabarito": str | None,
    "confianca": "alta" | "media" | "baixa",
    "disciplina": str,
    "topico": str,
    "banca": str,
    "ano": int | None,
}
```

A confiança não é uma probabilidade estatística. É uma indicação operacional para priorizar conferência humana:

- alta: estrutura reconhecida com bons sinais;
- média: estrutura utilizável, mas com algum sinal incompleto;
- baixa: resultado que exige revisão antes de salvar.

### 4.3 Gabarito

O gabarito pode chegar como:

- mapa textual de item para alternativa;
- tabela com números e respostas em linhas seguintes;
- várias provas/cargos no mesmo PDF;
- grade escaneada, tratada pelo caminho OCR quando texto não existe;
- sequência colada manualmente na tela.

Para os samples escaneados, o caminho OCR usa RapidOCR em CPU. O OpenCV detecta a geometria da grade e recorta as células antes de classificar cada resposta. As geometrias ficam em templates nomeados (`src/importador/templates.py`). Texto e tabelas estruturadas são processados primeiro; quando o conjunto esperado de números é conhecido, o OCR complementa somente os itens faltantes e respostas já confirmadas não são sobrescritas.

As associações confirmadas ficam em `config/gabaritos.json`, indexadas pelo
caminho relativo do caderno para evitar colisões de nomes. O comando
`scripts/diagnosticar_samples.py` gera JSON e Markdown sem abrir o banco, com
taxa de extração, associação, cobertura final, ganho potencial e motivos de
revisão. A opção `--ocr` executa a rodada mais lenta apenas para completar
itens ausentes.

O vínculo nunca é feito por deslocamento posicional quando há números disponíveis. `src/importador/validacao.py` compara números do caderno e do gabarito, registra extras, faltantes e duplicidades e marca o arquivo para revisão manual quando o cargo/prova ou a quantidade não são confirmados.

`parsear_gabarito_em_lote()` aceita apenas tokens completos para não transformar letras de palavras em respostas. `aplicar_gabarito_as_questoes()` normaliza `C`/`E` para `Certo`/`Errado` somente em questões certo/errado.

### 4.4 Persistência do lote

`criar_questoes_em_lote()` usa uma transação única. Se uma questão ou alternativa falhar, o lote não deve deixar metade da importação gravada.

O script `scripts/reimportar_samples.py` é uma operação explicitamente manual. Ele extrai todos os arquivos antes de limpar o banco, para evitar substituir os dados por uma importação que falhou no meio.

Na primeira execução de 23/08/2026 foram processados 23 PDFs e 979 questões. A confiança alta foi 954 (97,45%), contra 919 (93,87%) na execução anterior: ganho de 3,58 pontos percentuais. Naquele momento foram vinculados 551 gabaritos (56,28%). Após a estabilização do catálogo, uma nova reimportação persistiu 820 gabaritos (83,76%). A validação estrutural aprovou integralmente 2 arquivos; os outros 21 foram preservados e marcados para revisão manual por divergência de quantidade, número, cargo ou gabarito.

### Meta de cobertura de gabaritos

A meta original era elevar a cobertura de 56,28% para 80% ou mais — pelo
menos 783 das 979 questões. A medição posterior abaixo registra que essa meta
foi alcançada. A confiança da extração continua relevante, mas não substitui a
existência de uma correspondência de gabarito rastreável.

### Diagnóstico posterior à estabilização

O diagnóstico não destrutivo executado em 23/08/2026 sobre os mesmos 23
cadernos encontrou 820 vínculos estruturais em 979 questões (83,76%). Isso
representa 269 vínculos adicionais e ganho de 27,48 pontos percentuais sobre a
medição histórica. A meta de 80% foi superada sem executar OCR e sem abrir ou
alterar o banco. O relatório detalhado está em
`docs/RELATORIO_DIAGNOSTICO_GABARITOS.md`.

Uma reimportação destrutiva autorizada foi executada em seguida, com backup
prévio em `data/questoes.pre-reimport-2026-08-23.db`. A auditoria direta da
tabela `questoes` confirmou 820 registros com gabarito e 159 sem gabarito,
reproduzindo os **83,76%** previstos pelo diagnóstico.

Nesse contexto, “vínculo confirmado” descreve a correspondência explícita
entre caderno, concurso, cargo/prova e arquivo de gabarito. Não significa que
todo arquivo seja definitivo: fontes preliminares permanecem identificadas
como tais e podem exigir atualização após recursos.

## 5. Banco de dados

### 5.1 Fonte de verdade

O schema executado é definido pelos modelos Peewee em `src/db/models.py`. `init_db()` cria as tabelas com `safe=True` e ativa chaves estrangeiras no SQLite.

`src/db/migrations.py` mantém a versão do schema e repara incrementalmente
colunas legadas conhecidas. Antes de uma alteração estrutural em um arquivo
existente, cria uma cópia datada ao lado do banco. Testes usam bancos
temporários e não migram o arquivo do usuário.

O banco padrão é:

```text
data/questoes.db
```

Testes devem apontar o mesmo objeto Peewee para um caminho temporário por meio de `init_db(caminho)`, sem tocar no banco do usuário.

### 5.2 Entidades

| Tabela/modelo | Papel |
|---|---|
| `questoes` / `Questao` | enunciado, tipo, metadados, gabarito e exclusão lógica |
| `alternativas` / `Alternativa` | opções A–E ligadas a uma questão |
| `provas` / `Prova` | nome, filtros e configuração de limite de tempo |
| `prova_questoes` / `ProvaQuestao` | composição ordenada de cada prova |
| `tentativas` / `Tentativa` | início, fim, nota, acertos e tempo |
| `respostas` / `Resposta` | resposta dada, questão e correção |
| `revisao_espacada` / `RevisaoEspacada` | próxima revisão, intervalo e fator de facilidade |

### 5.3 Relações

```text
Questao 1 ─── N Alternativa
Questao N ─── N Prova       (por ProvaQuestao)
Prova   1 ─── N Tentativa
Tentativa 1 ─── N Resposta
Questao 1 ─── 1 RevisaoEspacada
```

### 5.4 Invariantes importantes

- questão inativa não aparece em busca nem em novas provas;
- alternativa só existe para questão de múltipla escolha;
- prova concluída não é iniciável novamente pela UI;
- respostas precisam pertencer à composição da prova;
- tentativa finalizada não pode ser finalizada novamente;
- nota usa o total da composição, então questão sem resposta conta como não acertada;
- dados relacionados são removidos em ordem segura somente no script de limpeza autorizado;
- excluir uma questão é exclusão lógica para preservar histórico.

### 5.5 Configuração de prova

O modelo de prova mantém filtros em JSON. O limite de tempo é armazenado junto à configuração como `_tempo_limite_min` para manter compatibilidade sem exigir migração imediata de tabela.

```json
{
  "disciplina": "Informática",
  "tipo": "multipla_escolha",
  "_tempo_limite_min": 30
}
```

Zero ou ausência significa sem limite. `obter_prova()` centraliza a leitura segura dessa configuração.

## 6. Ciclo da prova

```text
Pendente
   │ iniciar
   ▼
Em andamento ── responder/navegar ──┐
   │                                │
   ├── finalizar manualmente        │
   └── atingir limite de tempo      │
                    ▼               │
                 Concluída ◄────────┘
```

Na UI, `em_andamento` é a autoridade do estado. Ao finalizar, a página:

1. para o timer;
2. persiste respostas e resultado;
3. registra erros para revisão;
4. apresenta o resultado;
5. limpa questão, alternativas, timer e navegação;
6. retorna ao gerador, onde a prova aparece como `Concluída`.

## 7. Caderno de decisões de código

### Decisão 1 — SQLite local com Peewee

**Problema:** o projeto precisa funcionar sem servidor e com instalação simples.

**Decisão:** usar SQLite e Peewee.

**Motivo:** SQLite é local, portátil e suficiente para o volume esperado; Peewee reduz SQL repetitivo e mantém relações explícitas em Python.

**Custo:** mudanças de schema exigem atenção a compatibilidade e os testes precisam controlar o caminho global da conexão.

### Decisão 2 — Parser heurístico em vez de um formato único

**Problema:** bancas e PDFs usam marcadores, colunas e cabeçalhos diferentes.

**Decisão:** combinar expressões regulares, coordenadas do PDF, regras de front matter e confiança operacional.

**Motivo:** um formato rígido funcionaria para um sample e falharia para os demais.

**Custo:** cada nova heurística pode gerar regressão em outro layout; por isso mudanças devem adicionar caso positivo e negativo.

### Decisão 3 — Revisão humana após extração

**Problema:** OCR e PDFs complexos não oferecem garantia de precisão.

**Decisão:** mostrar prévia editável, confiança e opção de gabarito manual.

**Motivo:** uma extração imperfeita visível é recuperável; uma extração incorreta salva silenciosamente contamina todo o estudo.

### Decisão 4 — Operações de lote transacionais

**Problema:** salvar centenas de questões uma a uma é lento e pode deixar o banco incompleto após erro.

**Decisão:** `criar_questoes_em_lote()` salva a lista dentro de uma transação.

**Motivo:** atomicidade e melhor desempenho.

**Custo:** o lote inteiro falha se uma entrada inválida não for tratada; a UI precisa informar o erro e preservar a prévia.

### Decisão 5 — `QStackedWidget` para navegação

**Problema:** as páginas compartilham a mesma janela e precisam manter estado visual controlado.

**Decisão:** uma janela, menu lateral e páginas empilhadas.

**Motivo:** navegação simples e compatível com os botões de ação do Dashboard.

**Custo:** os índices das páginas são um contrato; alterar a ordem exige revisar todos os atalhos.

### Decisão 6 — Recarregar no `showEvent`

**Problema:** Dashboard, estatísticas, questões e gerador ficavam com dados antigos ao retornar à aba.

**Decisão:** recarregar dados no `showEvent` e após operações de escrita.

**Motivo:** garante que mudanças feitas em outra página apareçam sem reiniciar o app.

**Custo:** consultas são repetidas; `showEvent` não pode iniciar ações destrutivas nem processos longos sem feedback.

### Decisão 7 — Texto longo dentro de áreas limitadas

**Problema:** enunciados e alternativas extensos estouravam a largura do monitor.

**Decisão:** quebra de linha, `QTextEdit` somente leitura e `QScrollArea` para alternativas.

**Motivo:** o conteúdo cresce verticalmente sem impor largura mínima impossível.

**Custo:** o usuário pode precisar rolar dentro do cartão; a área precisa permanecer claramente rolável.

### Decisão 8 — Histórico explícito de provas

**Problema:** esconder provas concluídas fazia parecer que foram apagadas; mantê-las iniciáveis fazia a prova voltar infinitamente.

**Decisão:** listar concluídas com status e substituir o botão por texto.

**Motivo:** preserva a percepção de salvamento e impede nova execução acidental.

### Decisão 9 — Limite de tempo dentro da configuração JSON

**Problema:** a tela oferecia limite, mas a versão inicial não persistia nem aplicava esse valor.

**Decisão:** guardar `_tempo_limite_min` no JSON existente e aplicar no timer.

**Motivo:** corrige a funcionalidade sem exigir migração imediata da tabela `provas`.

**Custo:** o campo é uma convenção; `obter_prova()` deve ser usado para leitura segura.

### Decisão 10 — Proteções no domínio, não apenas na UI

**Problema:** a UI bloqueava alguns fluxos, mas chamadas repetidas ou inconsistentes ainda poderiam corromper histórico.

**Decisão:** o repositório rejeita finalização repetida e respostas fora da composição da prova.

**Motivo:** invariantes importantes não podem depender de um único botão.

### Decisão 11 — Estratégias de gabarito extraídas por layout

**Problema:** o roteamento de cargo/código e as heurísticas de gabarito estavam concentrados em um único loop, dificultando validar cada layout sem alterar a precedência existente.

**Decisão:** separar estratégias puras para pares na mesma linha, Item/Certo-Errado, sequências em duas linhas e multiprova; selecionar a estratégia por evidência textual e manter o estado de cargo/código em `FiltroContexto`.

**Motivo:** reduz a complexidade acidental e torna explícita a precedência texto/tabela/OCR, preservando o vínculo por número oficial.

**Evidência:** a rodada pós-refactor reproduziu os 23 cadernos, 979 questões, 996 respostas extraídas e 820 vínculos, com e sem OCR.

## 8. Testes e evidências

A suíte cobre atualmente:

- marcadores nomeados, corrompidos e numéricos;
- certo/errado, múltipla escolha e duas colunas;
- gabarito em lote e classificação por intervalo;
- criação em lote com alternativas;
- nota de prova parcial;
- limpeza de alternativas ao trocar o tipo;
- limite de tempo e quantidade inválida;
- finalização duplicada e respostas fora da prova;
- limpeza da tela após finalizar;
- seleção inicial do Dashboard;
- tamanho e inicialização básica da UI.

Comandos de validação:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

Para alterações no parser, valide também samples reais por contagem de questões, tipos, alternativas e gabaritos. Para alterações na prova, execute o ciclo manual criar → iniciar → responder parcialmente → finalizar → retornar ao gerador.

## 9. Limitações e próximos passos

### Limitações conhecidas

- A banca só é identificada quando há evidência reconhecível no texto extraído; nomes de arquivo ainda não formam uma fonte universal de metadados.
- Layouts novos podem exigir heurísticas específicas.
- Tentativas interrompidas são preservadas como abertas, mas não há uma tela completa de retomada.
- OCR pode exigir revisão humana, especialmente em grades de baixa qualidade.
- A confiança operacional melhorou nos samples, mas não equivale a acurácia estatística: 97,45% de confiança alta não significa 97,45% de respostas corretas.
- A validação encontrou divergências de numeração/quantidade em 21 dos 23 arquivos; somente os 2 arquivos sem divergência foram considerados automaticamente confirmados.

### Próximos passos naturais

1. criar uma camada explícita de metadados da fonte para inferir banca por arquivo com rastreabilidade;
2. adicionar retomada de tentativa aberta;
3. separar configuração de prova em colunas próprias se o JSON crescer;
4. adicionar testes parametrizados por banca e layout;
5. permitir exportação/importação controlada do banco;
6. melhorar observabilidade da importação com relatório por arquivo.

## 10. Como usar este caderno

Antes de uma mudança, responda:

1. Qual camada é dona dessa regra?
2. Qual contrato pode ser afetado?
3. O que acontece com dados já existentes?
4. Qual fluxo de UI pode ficar com estado antigo?
5. Qual sample ou teste prova que a mudança não regrediu?

Se a resposta não estiver clara, consulte o [PROJECT_BRAIN.md](PROJECT_BRAIN.md) e registre a nova decisão aqui antes de expandir a implementação.
