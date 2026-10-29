# Assistência local à conferência

O botão **Conferir com IA local**, em **Corrigir somente este campo**, compara
leituras de um recorte. Ele não aprova questões, não gera gabaritos e não chama
serviços pagos. O processamento ocorre no computador, usando o executor
llama.cpp e o Qwen3-VL-2B. O uso do modelo aberto não significa que já exista
um modelo treinado especificamente para este acervo.

## Usar no aplicativo

### Triagem em lote e revisão por exceção

Na tela **Questões**, ajuste os filtros e clique em **Triar lista automaticamente**.
O programa percorre somente os IDs dessa lista e reutiliza os processos locais
durante o lote. Há progresso e cancelamento; as análises terminadas podem ser
conferidas mesmo quando o restante do lote é cancelado.

O filtro inicial **Exceções e propostas** concentra os campos divergentes,
propostas de correção e bloqueios. Questões já liberadas seguem a avaliação
existente; uma leitura sem diferenças não aprova uma questão que ainda possui
pendências de conteúdo ou gabarito. As contagens e o filtro **Todas** mantêm
essas situações visíveis. A triagem inicial trata alternativas com evidência
geométrica suficiente; outros campos e fontes ambíguas continuam na revisão.
“Sem diferenças” significa que o valor salvo coincide com a leitura sustentada,
não que todos os leitores concordaram. As leituras e seus avisos continuam
disponíveis em **Todas**; essa classificação não substitui a conferência de conteúdo.

Ao escolher **Conferir campo**, o diálogo mostra o recorte, o valor atual, as
leituras e as diferenças. A proposta já vem preparada, mas só é gravada ao
salvar explicitamente, como nova versão pendente. A versão e a integridade da
fonte são reconferidas antes da edição; resultados históricos são descartados.
Não há aprovação coletiva ou troca de resposta baseada na confiança da IA.

### Conferência individual

1. Abra a revisão de uma questão e selecione a página e os limites no original.
2. Em **Corrigir somente este campo**, escolha enunciado, apoio ou alternativas.
   Para alternativas, escolha a letra ao lado do botão de IA.
3. Acione **Conferir com IA local**. Veja as leituras de PDF, OCR e IA e compare
   com o original. Quando duas leituras sustentam o mesmo texto, pode aparecer
   uma proposta; uma terceira leitura divergente continua visível.
4. Edite a proposta se necessário. **Salvar correção** continua criando uma
   versão pendente, sem transportar certificados ou decisões anteriores.

Alternativa sem marcador físico, marcador repetido, continuação interrompida
ou limite ambíguo bloqueiam a sugestão antes de chamar a IA. Listas internas
recuadas não devem ser tratadas como o começo da próxima alternativa.
Enunciado e apoio usam o trecho explicitamente selecionado: o programa não
deduz automaticamente os limites semânticos desses campos.

Número oficial e gabarito mantêm a conferência explícita já existente. Um
modelo não fornece o documento oficial ausente nem transforma preliminar em
definitivo. As explicações do modelo não são usadas como evidência: a tarefa
é transcrever o recorte em dois campos JSON, `encontrado` e `texto`.

## Instalação e recursos

Os arquivos já usados no piloto ficam em `tools/ia-local-piloto`, ignorado
pelo Git. Em outra instalação Windows x64, execute explicitamente:

```powershell
venv/Scripts/python.exe scripts/instalar_ia_local.py
```

O script baixa versões fixas de fontes públicas e verifica SHA-256 antes de
instalar, incluindo o executável e as DLLs extraídos. Os pesos e o componente visual somam aproximadamente 2,28 GB;
executor e artefatos locais ocupam espaço adicional. Para conferir os arquivos
sem rede, use `--verify-only`. A aplicação não baixa nada automaticamente.

Não há assinatura ou cobrança por token/consulta na execução local. O custo
é armazenamento, processamento, energia e trabalho de conferência. As licenças
de referência são [Apache 2.0 do modelo](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct)
e [MIT do executor](https://github.com/ggml-org/llama.cpp/blob/master/LICENSE).

Os processos de PDF, OCR e IA são separados da interface. A inferência atende
somente em `127.0.0.1`, com chave efêmera interna. Cancelamento interrompe os
processos da operação. O modo de lote reutiliza processos e encerra ao sair;
uma consulta individual encerra seu processo ao terminar. Memória e latência
devem ser medidas no hardware do usuário.

## Cache e integridade

O cache guarda a transcrição, não uma aprovação. Sua identidade inclui hash
do PDF, página, limites, imagem, alvo, pesos/projetor/executor, configuração e
versões da política/prompt/schema. Cada reutilização compara novamente com o
valor atual do campo. Fontes alteradas, resposta inválida ou cancelamento não
podem produzir aprovação. Resultados ficam em `data/ia_local/cache` e podem
ser descartados sem apagar questões.

## Avaliação separada

```powershell
venv/Scripts/python.exe scripts/avaliar_ia_local.py --manifest caminho/manifest.json --output reports/ia-avaliacao --force-model
```

O manifesto define fonte/hash, página, limites, alternativa, valor candidato,
referência, grupo e split (`ajuste` ou `avaliacao`). O avaliador rejeita
fontes/grupos compartilhados entre os splits. Registra propostas erradas,
abstenções obrigatórias, casos não resolvidos, tempos, memória e reaproveitamento
do cache. Os PDFs originais são revalidados; o banco da aplicação não é aberto.

O diálogo registra localmente duração da sessão, tempo de espera pela IA e se
houve salvamento ou cancelamento, sem texto da questão ou nome da pessoa. Use
`scripts/resumir_ia_local.py` para resumir sessões manuais e assistidas.
Esses tempos observados não demonstram economia por si só; é necessário
comparar conferências humanas equivalentes. As medições nunca viram labels.

O conjunto inicial ampliado usa sete documentos: quatro de ajuste e três
separados para avaliação, com 21 cenários. Referências conferidas visualmente
pelo Codex são referências do ensaio, **não rótulos humanos para treino**.
Casos com texto excedente são controles provocados; a falha histórica está
documentada no piloto anterior. O relatório local fica em
`reports/ia-local-v2/`. Essa amostra não comprova precisão geral nem suporte
irrestrito a digitalizações reais, fórmulas ou documentos inéditos.

## Exemplos para futura especialização

Depois de analisar um recorte, **Guardar exemplo conferido** mostra a imagem e pede o texto exato, o nome do responsável e a
confirmação de que toda a transcrição foi conferida. Guardar o exemplo não
aprova a questão nem inicia treinamento.

Se o recorte estiver ilegível, a pessoa pode registrar explicitamente um exemplo
de abstenção, com texto vazio. O modelo não decide sozinho quais respostas viram
exemplos de treino. Imagens iguais ficam no mesmo split mesmo quando aparecem
em provas diferentes; a deduplicação pode reduzir o número de grupos independentes.

Somente exemplos explicitamente confirmados entram em `data/ia_local/exemplos`.
Cada registro tem imagem/hash, hash de origem, grupo, página, limites, texto e
responsável. Saídas da IA e certificados automáticos não viram rótulos humanos.

```powershell
venv/Scripts/python.exe scripts/preparar_treino_ia.py --dataset data/ia_local/exemplos --output reports/ia-treino
```

A exportação produz `train.jsonl`, `validation.jsonl`, snapshots das imagens, manifesto e avaliação
de prontidão. As imagens exportadas têm hashes próprios e não dependem da pasta original.
Use `scripts/preparar_treino_ia.py --verify-export reports/ia-treino` para revalidar o conjunto. Componentes conectados por fonte ou grupo ficam no mesmo split;
duplicatas são removidas e rótulos conflitantes são rejeitados. O holdout pode
ser definido com `--holdout-group`. O formato multimodal precisa de um loader
compatível no futuro treinador; não é enviado a nenhum serviço.

O mínimo operacional inicial é 100 exemplos em cinco grupos, além de treino
e validação separados; é uma condição para experimentar, não garantia de
qualidade. Sem rótulos suficientes, não treinar. Hardware não inventariado
permanece pendente, sem afirmar que CPU é impossível ou prometer um tempo.
Uma especialização LoRA só deve substituir a base se melhorar em fontes que
não participaram dos ajustes, especialmente sem aumentar propostas erradas.
Este fluxo prepara e avalia os dados; nenhum treinamento é iniciado sozinho.
