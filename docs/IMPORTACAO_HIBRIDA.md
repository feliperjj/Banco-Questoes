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

## Associação e integridade dos gabaritos

Os perfis `ExtratorExtenso` e `ExtratorHorizontal` tratam palavras de resposta e
blocos alinhados separadamente. `ExtratorPadrao` combina esses resultados com
pares na mesma linha, processando todos os blocos da página. Listas verticais
são blocos unitários; sequências V/F não encerram a leitura após a primeira linha.

- Blocos horizontais exigem a mesma quantidade de números e tokens. `?`, `*` e
  `0` preservam uma lacuna sem deslocar as respostas seguintes; não são anulações.
- `MapaGabarito` preserva conflitos em listas, grades, tabelas e complementos OCR.
  Texto tem prioridade sobre complementos; um conflito textual não pode ser
  preenchido novamente por outra leitura.
- Seleção por tipo também recorta os blocos de um mesmo cargo na mesma página.
  Tabelas extraídas da página inteira não complementam um recorte de outro contexto.
- O OCR recebe cargo e código, reconstrói linhas e usa os perfis textuais. Números
  não são inventados a partir da posição da célula ou do último item de outra página.
  Grades escaneadas sem numeração legível ou sem seleção geométrica segura ficam
  pendentes. Isso pode reduzir a cobertura automática dessas digitalizações.
- A associação rejeita respostas incompatíveis com o tipo da questão ou com as
  alternativas extraídas. Diagnóstico e revisão exibem essas pendências; elas não
  contam como cobertura confirmada.

Na geração de provas, registros antigos com respostas incompatíveis também são
excluídos pela validação de estrutura. A tela informa quando a quantidade apta é
menor que a solicitada e confirma a quantidade efetivamente gerada.

As regressões específicas estão em `tests/test_gabaritos_seguranca.py`. Os testes
de OCR desse arquivo usam detecções controladas; não medem a precisão do motor em
novas digitalizações. As amostras reais continuam cobertas pelos demais testes de
importação, incluindo os 120 vínculos da PF/CEBRASPE 2025.

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

## Dois funis especializados — implementação parcial

O reconhecimento do caderno e do gabarito agora produz perfis documentais e
diagnósticos por página. `perfis/registro.py` descreve os perfis conhecidos;
`associacao_documental.py` compara família, identificadores, escopo e cobertura
numérica; a tela permite reprocessar um caderno por um perfil candidato. Para
gabaritos com vários layouts, a tela mantém o roteamento por página e não força
um perfil global.

As listas editáveis de cargo, código e versão exibem as opções reconhecidas no
PDF. Havendo várias opções, a tela exige seleção e nova leitura antes de
vincular respostas; uma seleção incompatível com o caderno permanece bloqueada.
**Conferir leitura por página** permite ajustar separadamente caderno e
gabarito. Blocos consecutivos mantêm a leitura e o contexto entre páginas; uma
escolha estruturalmente incompatível gera pendência. Páginas sem texto ficam
identificadas e não são consideradas íntegras por uma seleção manual de perfil.

Ao salvar, `lote_verificado.py` registra a extração e as fontes dentro de uma
transação. A certificação automática exige evidência de conteúdo e gabarito,
escopo compatível e regiões físicas verificáveis. Itens sem essas evidências
ficam pendentes; salvar ou selecionar um perfil não libera questões. Lotes
revisados sem arquivo de fonte acessível também podem ser salvos, mas não são
certificados automaticamente.

Os totais devolvidos ao lote vêm de `assess_version`, distinguindo certificado
automático válido de elegibilidade efetiva. A tela mostra extraídas, com
resposta, salvas, verificadas, elegíveis e pendentes; quantidade esperada só
aparece como número quando declarada pela fonte. Os atalhos após o salvamento
abrem a prévia da prova e suas pendências ou o gerador aleatório.

Figuras, fac-símiles e páginas para OCR são renderizados por PDFium em processo
isolado. O lote reutiliza esse processo e mantém o confronto dos pixels com o
PDF. Falhas de extração, preparação ou transação removem apenas recursos novos;
arquivos já existentes permanecem preservados. Um recorte contextual completo
não é substituído por uma região geométrica ainda não aprovada.

O botão de cancelamento sinaliza a tarefa em segundo plano: leituras em curso
terminam a etapa atual antes de descartar o resultado; cancelamento durante a
gravação reverte o lote inteiro. Se os mesmos dois PDFs já tiverem sido
importados e o conteúdo permanecer igual, a prova cadastrada é reutilizada. Se
o conteúdo revisado divergir, o salvamento exige marcar a opção de criar nova
versão, preservando a composição histórica e as versões vinculadas a tentativas.

Uma reimportação completa também pode retomar itens já salvos de um lote
parcial. A identidade inclui os dois PDFs e o escopo; IDs, evidências e
rejeições humanas são preservados. Escopos distintos geram composições
distintas. Se o legado não comprovar o escopo/par de fontes, a tela orienta
conferir os registros existentes ou retomar o rascunho, evitando fusão ou
duplicação automática.

Essa integração ainda não comprova suporte integral ao corpus. O relatório
[`RELATORIO_DOIS_FUNIS_ESPECIALIZADOS_LUNA.md`](RELATORIO_DOIS_FUNIS_ESPECIALIZADOS_LUNA.md)
registra pares testados, hashes, limitações observadas e critérios que faltam.
Em particular, perfil reconhecido não equivale a extração de gabarito correta;
confira os resultados do corpus antes de declarar qualquer documento suportado.

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

O verificador aceita `--diagnostico-json caminho.json` para registrar a comparação
estrita e a projeção dos campos do contrato antigo. Essa classificação não
altera o resultado estrito nem aprova os campos novos de contexto/instruções.

Para acrescentar um perfil: definir evidências de reconhecimento e rejeição, incluir exemplos positivos e negativos de outro layout, verificar texto/alternativas/números e executar a comparação de referências. Uma nova estratégia não deve completar números ou respostas ausentes por suposição.
# Validação do par real S201

O caderno EPAGRI/S201 enviado em 28/10 foi testado pela interface com seu
gabarito: 50 questões e respostas preservadas, 46 elegíveis e quatro anulações
(16, 18, 19 e 36) bloqueadas. A consulta mantém os 50 itens; a resolução é
identificada como treino parcial de 46/50. Treino parcial com retomada e simulado
aleatório terminaram com 46/46 acertos no banco isolado.

O leitor de páginas com caixas de seleção remove cabeçalhos repetidos antes
de dividir as colunas e encerra a leitura objetiva antes da redação. Os recortes
preservam expoentes, tabelas e fórmulas. T11/T12 permanecem códigos de cargo;
não indicam versões. Cargos homônimos exigem o código correto no gabarito.

Cópias de fontes catalogadas fora de `samples` podem reutilizar a associação
somente após comparação integral de texto e pixels de ambos os PDFs. A
autoridade de liberação recompõe essa prova e rejeita alterações. Isso não
substitui a identificação documental de pares novos nem comprova generalização
para PDFs ainda não conferidos. Veja o relatório de execução para as limitações
que ainda impedem o aceite integral do plano.

## Fechamento real dos dois funis — 28/10

Três famílias passaram pela interface em bancos isolados: EPAGRI/S201 (50 itens/46 elegíveis), Morungaba com rótulos QUESTÃO (40/38) e EMBRAPA/Sistemas C/E com texto compartilhado (100/94). Os itens restantes são anulados. Composições completas preservadas; treinos parciais com retomada e simulados aleatórios concluídos com 46/46, 38/38 e 94/94.

Dataprev tipo 4: 70 respostas conferidas no quadro da página 14; tipo 3 recusado. O gabarito é preliminar e a identidade impressa é insuficiente para certificação independente. São 70 questões para conferência e zero elegíveis, sem simulado. O código no nome do arquivo não substitui comprovação documental. Permanecem necessários gabarito definitivo e identidade verificável/revisão humana efetiva.

Apoios relativos e recursos compartilhados foram preservados. Cabeçalhos/rodapés saem do corpo mantendo banca/ano documentais; números internos não sobrescrevem a disciplina de questões anteriores. O relatório de execução reúne evidências, limites e validações finais. Os três pares conhecidos e a Dataprev ajustada não comprovam generalização cega. OCR de digitalização real também não foi comprovado.
