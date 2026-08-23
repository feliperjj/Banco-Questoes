# Banco de Questões

Aplicação desktop local para transformar provas de concursos em um banco de estudos pesquisável, reutilizável e orientado à prática.

O projeto importa provas em PDF/DOCX, interpreta questões e gabaritos, permite revisão humana, cria simulados e registra desempenho e revisão espaçada em SQLite.

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![Interface](https://img.shields.io/badge/Interface-PySide6-41CD52?logo=qt&logoColor=white)
![Banco](https://img.shields.io/badge/Banco-SQLite-003B57?logo=sqlite&logoColor=white)
![Testes](https://img.shields.io/badge/Testes-29%20aprovados-2ea44f)

## O problema que o projeto resolve

Quem estuda por provas anteriores normalmente precisa copiar questões, separar alternativas, procurar gabaritos, classificar assuntos e acompanhar erros manualmente. O Banco de Questões concentra esse trabalho em um fluxo local:

```text
PDF/DOCX → extração → parser → conferência → banco → prova → desempenho → revisão
```

O objetivo não é fingir que todo PDF possui o mesmo formato. O objetivo é automatizar o máximo possível, indicar incertezas e manter a conferência humana onde o documento exigir.

## Funcionalidades atuais

- Importação de questões em PDF e DOCX.
- Extração de texto com tratamento de cabeçalhos, rodapés, marcas d’água, colunas e texto rotacionado.
- Reconhecimento de questões de múltipla escolha e certo/errado.
- Extração de gabaritos textuais, tabelados e, quando disponível, OCR.
- OCR CPU com RapidOCR, detecção de grades/células por OpenCV e templates específicos para layouts dos samples.
- Validação de vínculo por número, cargo/prova e quantidade, com pendências separadas para revisão manual.
- Aplicação de gabarito e classificação por intervalos.
- Edição e exclusão lógica de questões.
- Busca por enunciado, disciplina, categoria, banca e tipo.
- Geração de provas aleatórias com filtros e limite de tempo.
- Execução com timer, alternativas responsivas e proteção contra finalização duplicada.
- Histórico de provas concluídas, estatísticas e revisão espaçada.
- Banco local, sem necessidade de servidor.

## Documentação do projeto

- [Caderno técnico](docs/CADERNO_TECNICO.md): evolução, conceito, arquitetura, banco de dados e decisões de código.
- [Cérebro operacional](docs/PROJECT_BRAIN.md): contratos, checklist de regressão, riscos e matriz de validação.
- [Relatório de reimportação](docs/RELATORIO_REIMPORTACAO_SAMPLES.md): resultado por sample, bancas, disciplinas, gabaritos e pendências.
- [Screenshots das telas](docs/screenshots/): referência visual da interface.

O caderno explica por que as decisões foram tomadas. O cérebro operacional deve ser consultado antes de modificar uma regra existente.

## Fluxo recomendado

1. Abra **Importar** e selecione o PDF/DOCX das questões.
2. Confira a prévia, especialmente os itens com confiança média ou baixa.
3. Se houver gabarito, selecione o PDF correspondente ou cole a sequência de respostas.
4. Classifique blocos por disciplina e categoria quando o PDF não trouxer esses metadados.
5. Salve as questões.
6. Em **Gerar Prova**, escolha filtros, quantidade e limite de tempo.
7. Resolva a prova e confira resultado, estatísticas e revisão.

Se o gabarito puder ser colado manualmente:

```text
A D B C E A B D C E ...
```

> PDFs de bancas diferentes podem misturar colunas, instruções, textos-base, tabelas e imagens. Sempre confira a prévia antes de salvar. A banca e a disciplina só serão preenchidas automaticamente quando houver evidência reconhecível no documento.

## Telas

### Dashboard

![Dashboard](docs/screenshots/dashboard.png)

### Banco de questões

![Questões](docs/screenshots/questoes.png)

### Importação e classificação em lote

![Importação](docs/screenshots/importar.png)

### Geração de provas

![Gerar prova](docs/screenshots/gerar-prova.png)

### Modo prova

![Modo prova](docs/screenshots/modo-prova.png)

### Estatísticas

![Estatísticas](docs/screenshots/estatisticas.png)

### Revisão espaçada

![Revisão](docs/screenshots/revisao.png)

## Arquitetura resumida

```text
main.py
  └── ui/                 PySide6, páginas, navegação e QSS
        └── models/       regras de prova, persistência e revisão
              └── db/     Peewee, modelos e SQLite

importador/extrator.py    PDF/DOCX/OCR → texto
importador/parser.py      texto → questões estruturadas
importador/templates.py   templates de layout dos gabaritos
importador/validacao.py   número, cargo, quantidade e pendências
importador/lote.py        tokens/blocos → gabarito/classificação
```

As dependências seguem uma direção simples: a UI chama serviços e repositórios; o parser não conhece widgets; o banco não conhece a UI.

## Estrutura do repositório

```text
.
├── main.py                       # Entrada da aplicação
├── requirements.txt              # Dependências Python
├── data/                         # Banco e logs locais, ignorados pelo Git
├── docs/
│   ├── CADERNO_TECNICO.md        # História, arquitetura e decisões
│   ├── PROJECT_BRAIN.md          # Contratos e prevenção de regressões
│   └── screenshots/              # Referências visuais
├── scripts/
│   └── reimportar_samples.py     # Reimportação local explicitamente manual
├── src/
│   ├── db/                       # Peewee, modelos e inicialização SQLite
│   ├── importador/               # Extração, OCR, parser e operações em lote
│   ├── models/                   # Repositórios e serviços de domínio
│   └── ui/                       # Janela, páginas e estilos
└── tests/                        # Testes de parser, banco, lote e UI
```

## Instalação

Requisito: Python 3.12 ou superior.

### Windows

```powershell
git clone https://github.com/feliperjj/Banco-Questoes.git
cd Banco-Questoes
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

### Linux ou macOS

```bash
git clone https://github.com/feliperjj/Banco-Questoes.git
cd Banco-Questoes
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

O OCR utiliza dependências Python do projeto. PDFs escaneados podem exigir mais tempo de processamento e revisão manual.

Na reimportação dos samples de 23/08/2026, a confiança alta passou de 919/979 (93,87%) para 954/979 (97,45%), um ganho de 3,58 pontos percentuais. O vínculo de gabaritos permaneceu em 551/979 (56,28%); os casos sem correspondência inequívoca continuam separados para revisão.

### Meta prioritária

A métrica mais importante para as próximas iterações é a cobertura de gabaritos confirmados. A meta é elevar os atuais 551/979 (56,28%) para pelo menos 80%, chegando a aproximadamente 783 questões com resposta validada. Confiança de extração, quantidade de questões e classificação são métricas auxiliares: uma questão sem gabarito confirmado ainda não está pronta para estudo com correção automática.

## Dados locais

O banco é criado automaticamente em `data/questoes.db`. Questões, alternativas, provas, tentativas, respostas, revisões e logs ficam no computador local. O diretório `data/` não deve ser commitado.

Operações de limpeza ou reimportação são destrutivas para os dados locais e só devem ser executadas quando solicitadas. Para testes, prefira `init_db(caminho_temporario)`.

## Desenvolvimento e validação

Executar a suíte:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Verificar compilação:

```powershell
.venv\Scripts\python.exe -m compileall -q src tests
```

Smoke test da UI em ambiente sem monitor:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; from src.ui.main_window import MainWindow; app=QApplication([]); w=MainWindow(); assert w.minimumWidth() >= 960; print('UI smoke OK')"
```

Antes de alterar comportamento existente, consulte o [cérebro operacional](docs/PROJECT_BRAIN.md). Para entender a lógica e a evolução, consulte o [caderno técnico](docs/CADERNO_TECNICO.md).

## Estado atual e limitações conhecidas

- A extração de banca depende de evidência no texto do arquivo; nomes de arquivos ainda não são uma fonte universal de metadados.
- PDFs com layouts muito diferentes podem exigir uma nova heurística e um caso de teste específico.
- Tentativas interrompidas ficam registradas como abertas, mas ainda não possuem uma tela de retomada completa.
- A revisão humana continua necessária quando o PDF não contém texto confiável ou quando o gabarito é ambíguo.

## Licença

Este projeto ainda não possui uma licença pública definida. Consulte o autor antes de redistribuir o código, os PDFs ou as imagens de provas.
