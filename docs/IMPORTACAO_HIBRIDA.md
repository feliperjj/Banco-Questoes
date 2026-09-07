# Importação híbrida por formato

A importação combina leitores especializados com uma segmentação geral conservadora. O formato é identificado pela estrutura do documento; o gabarito não participa da decisão sobre os limites das questões.

## Etapas

1. **Leitura:** PDF textual, leitura por colunas, texto-base com recuos, OCR local para páginas sem texto ou DOCX com tabelas na ordem original.
2. **Segmentação:** candidatos por marcadores nomeados, número isolado, número pontuado, número com espaço, itens sequenciais e formato predominante. Marcadores explícitos e contratos de contexto têm prioridade.
3. **Validação:** compara numeração extraível, duplicatas, alternativas e divergência entre candidatos. Mantém o candidato geral quando uma troca não traz evidência suficiente. Empates diferentes geram aviso.
4. **Revisão:** preserva números oficiais, textos de apoio, avisos e diagnóstico dos candidatos. Figuras e tabelas podem exigir conferência no PDF.
5. **Gabarito:** seleciona cargo/código/tipo antes de ler as respostas; trata pares, linhas alinhadas, listas verticais, C/E, V/F, anulações, tabelas, seções e grades com várias provas.

## Formatos cobertos e limites

| Família | Variações | Verificação |
|---|---|---|
| Marcadores de questão | QUESTÃO/QUESTAO, Nº, Q., número isolado, ponto, parêntese, dois-pontos, traço e espaço | Casos sintéticos com conteúdo esperado e PDFs de referência |
| Alternativas | A–E, maiúsculas/minúsculas, parênteses, mesma linha, letra isolada, letras circuladas e caixas de seleção | Conteúdo e letras conferidos nos testes |
| Certo/errado | Numeração sequencial, justificativas separadas, texto-base, comandos julgue/judge, mistura com múltipla escolha | PF 2025 e dois cadernos Embrapa, além de casos sintéticos |
| Texto-base | Intervalo explícito de questões, rótulo Texto 1 e referência local, continuidade entre colunas | Testes de reutilização e de não vazamento para outro texto |
| PDF | Coluna única, duas colunas, três colunas com separadores confirmados, mudança de largura em itens com recuo | PDFs reais para uma/duas colunas; três colunas com teste geométrico sintético |
| Digitalização | OCR local por página quando não há texto extraível | Aviso obrigatório; reconhecimento de caracteres/ordem não equivale a validação humana |
| DOCX | Parágrafos e tabelas intercaladas, células mescladas sem duplicação | Documento temporário com ordem e respostas conferidas |
| Gabarito | Pares, linhas alinhadas, listas verticais, palavras Certo/Errado, V/F, X e notas de anulação | Casos esperados, fontes locais e controle de conflitos |
| Multiprova | Cargo/código, tipos, seções e colunas identificadas por PROVA n | Seleção explícita, incluindo IDs maiores que quatro; sem escolha automática da primeira coluna |

A arquitetura permite acrescentar novos perfis, mas não representa cobertura de todos os PDFs possíveis. Fórmulas, imagens, tabelas complexas, OCR ruim e textos sem marcadores inequívocos continuam exigindo revisão. O número extraído não comprova a qualidade do enunciado.

## Organização do código

- `extrator.py`: API de compatibilidade, sem algoritmo aglomerado.
- `pdf_texto.py`, `docx_texto.py`: leitura documental.
- `perfis/pdf_recuado.py`, `cebraspe_layout.py`, `perfis/pdf_paginas.py`: leitores de layout.
- `perfis/segmentacao.py`: catálogo de marcadores, geração/seleção e diagnóstico dos candidatos.
- `perfis/certo_errado.py`, `perfis/multipla_escolha.py`: estratégias de segmentação.
- `perfis/normalizacao.py`, `perfis/lexico.py`: regras locais compartilhadas.
- `gabaritos.py`: coordenação da associação à fonte.
- `perfis/gabaritos_contexto.py`, `gabaritos_texto.py`, `gabaritos_grades.py`, `gabaritos_ocr.py`, `gabaritos_resultado.py`: seleção, leitura e conflitos.
- `servico.py`: fluxo usado pela tela, sem acesso ao banco durante a extração.

## Diagnóstico sem gravar no banco

```powershell
.\.venv\Scripts\python.exe scripts/diagnosticar_formato.py "caderno.pdf" --saida "diagnostico.json"
```

Para incluir o gabarito, acrescente `--gabarito "gabarito.pdf" --cargo "Cargo exato" --codigo "PROVA 1"`, conforme a seleção impressa na fonte.

O JSON mostra perfis, candidatos, avisos, números ausentes/duplicados e o conteúdo extraído. A revisão da tela exibe avisos e mantém o perfil na dica do arquivo. Esses diagnósticos não são novas colunas do banco de questões.

## Prevenção de regressões

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/verificar_regressoes_perfis.py
```

A referência atual, após a correção de lacunas, é `tests/fixtures/perfis_corrigidos_manifest.json`. As anteriores permanecem em `perfis_manifest.json` e `perfis_hibridos_manifest.json`. Referências de conteúdo são registros de comportamento e podem conter defeitos conhecidos; não substituem testes com expectativas conferidas na fonte. Não atualizar automaticamente uma referência para esconder uma diferença. Resultados e regras acrescentadas: `RELATORIO_CORRECAO_LACUNAS.md`.

Para acrescentar um perfil: definir evidências de reconhecimento e rejeição, incluir exemplos positivos e negativos de outro layout, verificar texto/alternativas/números e executar a comparação de referências. Uma nova estratégia não deve completar números ou respostas ausentes por suposição.
