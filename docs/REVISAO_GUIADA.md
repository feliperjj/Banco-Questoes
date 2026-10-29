# Revisão guiada e correção parcial

## Como usar

1. Abra **Questões** e ajuste a busca ou o filtro do funil.
2. Clique em **Revisar pendências da lista**. A avaliação usa a versão atual de
   cada questão da lista e inclui somente registros ativos ainda não liberados.
3. Escolha o motivo da pendência. A orientação informa a ação necessária.
4. Use **Conferir esta pendência** para abrir a fonte relacionada. O recorte
   original e o conteúdo salvo aparecem lado a lado. A aba **Página completa**
   mantém acesso ao restante do documento; **Ajustar recorte** expõe os limites.
5. Em **Conteúdo e decisões**, informe responsável, justificativa e evidências e
   registre as decisões de conteúdo e gabarito separadamente.
6. Avance pela fila. Decisões, justificativa e escopo da questão anterior não
   ficam preenchidos na próxima. Fechar e reabrir a fila reavalia as pendências.

## Corrigir um campo

**Corrigir somente este campo** permite escolher enunciado, apoio, alternativas,
gabarito ou número oficial. O formulário mostra o valor atual e a proposta.

**Reler somente o recorte selecionado no PDF** extrai apenas a região/página
selecionada, em worker, sem importar novamente o caderno ou salvar a proposta.
Enunciado e apoio recebem o texto como proposta editável. Número, alternativas
e gabarito exigem preenchimento explícito a partir do trecho exibido. As
alternativas usam `A) texto`, `B) texto` etc., uma alternativa por linha.

Salvar altera apenas o campo escolhido, registra uma execução própria e cria
uma versão pendente, sem transportar aprovações nem a apresentação automática
da extração anterior. A versão base é conferida novamente dentro da transação;
edições concorrentes ou versões históricas não podem ser sobrescritas. Uma
proposta idêntica ao campo atual não cria versão extra. Tentativas existentes
mantêm seus snapshots e notas.

## Limites e validação

- A visualização do recorte funciona também em páginas sem texto extraível.
  A releitura textual avisa quando exige correção manual; não executa OCR nessa
  ação nem libera uma questão por reconhecimento aproximado.
- Fontes ausentes ou alteradas bloqueiam sua releitura, visualização assistida e
  aplicação de propostas relidas. As decisões continuam sujeitas à autoridade
  de elegibilidade do domínio.
- Fila e contagem filtrada usam snapshots de leitura com até 100 e 250 questões,
  respectivamente, incluindo somente alternativas, versões, evidências e fontes relacionadas.
  Leituras fora do escopo consultam o banco; snapshots terminam após a leitura.
- Esta entrega não altera pesos de associação ou critérios de certificação e
  não demonstra generalização para PDFs inéditos.

Validação em 28/10/2026: suíte completa com **336 aprovados e 1 ignorado**
(teste condicionado a PDFs externos ausentes). Os testes novos exercitam fila,
releitura, fonte alterada, correção isolada, histórico, mudança concorrente,
escopo de consultas e navegação sem transportar decisões. A renderização Qt foi
conferida em 960×640 e 1240×800 com PDF sintético e banco isolado; capturas locais
em `reports/review-qa-2026-10-28/`. O acervo operacional não foi reimportado.
