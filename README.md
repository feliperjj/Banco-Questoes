# Banco de Questões

Aplicação desktop para organizar, importar e praticar questões de concursos. O projeto combina **PySide6**, **SQLite** e um importador em lote para PDFs de diferentes formatos.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![Interface](https://img.shields.io/badge/Interface-PySide6-41CD52?logo=qt&logoColor=white)
![Banco](https://img.shields.io/badge/Banco-SQLite-003B57?logo=sqlite&logoColor=white)

## Funcionalidades

- Importação de questões em PDF e DOCX.
- Extração em lote de enunciados e alternativas.
- Identificação automática de banca, disciplina e seções da prova.
- Importação de gabaritos textuais ou escaneados por OCR em Python.
- Vinculação automática das respostas às questões.
- Revisão dos itens extraídos antes de salvar.
- Banco local SQLite para questões e alternativas.
- Geração de provas por quantidade e disciplina.
- Execução com cronômetro, respostas e resultado.
- Fila de revisão espaçada.
- Estatísticas de desempenho e questões mais erradas.

## Importação em lote

1. Abra **Importar**.
2. Selecione o PDF/DOCX da prova.
3. Selecione o PDF do gabarito, inclusive se for uma imagem escaneada.
4. Aguarde o OCR; a interface permanece responsiva.
5. Confira apenas os itens sinalizados com menor confiança.
6. Clique em **Salvar Todas as Questões**.

Também é possível colar uma sequência inteira de respostas:

```text
A D B C E A B D C E ...
```

## Instalação

Requisito: Python 3.12 ou superior.

### Windows

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

### Linux ou macOS

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

O OCR usa dependências Python do próprio projeto; não é necessário instalar um programa OCR separado no Windows.

## Estrutura

```text
.
├── main.py                    # Entrada da aplicação
├── requirements.txt           # Dependências Python
├── src/
│   ├── db/                    # Modelos e inicialização do SQLite
│   ├── importador/            # Extração, OCR e parser
│   ├── models/                # Persistência e serviços
│   └── ui/                    # Páginas e estilos PySide6
└── data/                      # Banco e logs locais
```

## Banco de dados

O banco é criado automaticamente em:

```text
data/questoes.db
```

O diretório `data/` não é versionado, evitando publicar questões importadas, respostas, logs e backups locais.

## Desenvolvimento

Verificação básica de sintaxe:

```powershell
venv\Scripts\python.exe -m compileall -q src
```

Antes de abrir um pull request, confira se `data/`, `venv/`, `tools/` e caches continuam ignorados pelo Git.

## Observações

- PDFs com layout incomum podem gerar itens com confiança reduzida; o fluxo foi desenhado para revisar apenas exceções.
- Gabaritos escaneados dependem da qualidade da imagem. Como alternativa, a sequência de respostas pode ser colada em lote.
- O banco local não deve ser enviado ao GitHub.
