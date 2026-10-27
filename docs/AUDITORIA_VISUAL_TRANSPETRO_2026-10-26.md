# Auditoria de fidelidade da prova Transpetro

Data: 26/10/2026. Escopo: as 70 questões da **Prova 1 — Administração — Terra — Nível Superior — edital 2/2023.2** presentes no banco local. O catálogo a apresenta como “Transpetro · FGV”, mas a capa identifica a **Fundação CESGRANRIO**.

## Resultado medido

**A prova ainda exige correção antes de ser considerada fiel ao original.** A inspeção encontrou 13 questões com falha material, duas com destaque importante perdido e 27 com ruídos de apresentação. Em 28 não foi observada divergência material no conteúdo confrontado.

| Critério | Resultado | O que significa |
|---|---:|---|
| Questões com falha material confirmada | 13/70 · 18,6% | Q10, Q11–20, Q41 e Q68. |
| Questões com destaque importante perdido | 2/70 · 2,9% | Q6 e Q9. O texto simples omite a identificação visual do trecho perguntado. |
| Conteúdo preservado com ruído | 27/70 · 38,6% | Números de página, rodapés, linearização de tabelas ou imagem com conteúdo duplicado. |
| Sem divergência material observada | 28/70 · 40,0% | Textos confrontados com a fonte; não equivale a aprovação formal ou revisão acadêmica. |
| Gabaritos salvos iguais ao documento local fornecido | 70/70 · 100,0% | Conferência no escopo Prova 1/Administração; publicação definitiva não verificada externamente. |
| Recortes de imagem correspondentes à questão | 3/4 · 75,0% | Q55, Q57 e Q70 corretos; Q68 mostra Q70. |

**Não existe uma porcentagem única de “confiabilidade” demonstrada.** As dimensões têm resultados diferentes e não devem ser somadas ou promediadas. A ausência de falha material observada em 55/70 itens (78,6%, incluindo os 27 com ruído) não demonstra que 78,6% da prova esteja integralmente correta: destaques, metadados, revisão formal e estado de publicação do gabarito também importam. O conjunto de 15 itens com falha material ou destaque perdido corresponde a 21,4% da prova.

Esses resultados pertencem à prova Transpetro examinada. Não estimam a taxa de acerto da extração das outras 22 provas do banco.

## Problemas que afetam a leitura

- **Q10, página 3:** a alternativa E deveria conter apenas “incompreensão”. Ela recebeu o texto-base de inglês da página 4 inteiro.
- **Q11–20, páginas 4–5:** o texto-base de inglês não está vinculado a nenhuma dessas questões. Fragmentos citados em alguns enunciados não substituem o texto completo do original.
- **Q41, página 10:** μ/σ foram convertidos em m/s e os expoentes se tornaram caracteres na linha normal. A mesma limitação aparece na extração de texto do PDF, demonstrando que igualdade textual automática não valida a fórmula. A página foi conferida também com PDFium, após o aviso de fonte Symbol do Poppler. Não foi presumido um sinal de raiz ausente: foi comparada a notação efetivamente visível no original.
- **Q68, página 14:** o texto contém a tabela de desconto/VPL, mas o recorte vinculado é o da questão 70 (empréstimo). Os dois arquivos de imagem são idênticos por SHA-256.
- **Q6 e Q9, página 3:** foram perdidos os negritos que identificam a palavra “que” e o “segmento em destaque”.
- **Metadados:** o rótulo FGV contradiz a capa CESGRANRIO. O campo de número oficial permanece vazio nas 70 questões; para esta auditoria, cada correspondência foi confrontada com o marcador impresso e o texto do original, sem preencher o campo nem converter automaticamente a ordem em número oficial.

Há contraprovas positivas: os enunciados e alternativas extensos da Q24 estão presentes; seu comprimento não é um defeito. As tabelas das Q55, Q57 e Q70 estão completas nos recortes correspondentes, embora existam duplicação de conteúdo e linearização do texto.

## Método e limites

1. Banco SQLite aberto em modo somente leitura; nenhum gabarito, imagem, aprovação ou questão foi alterado pela auditoria.
2. Leitura independente das duas colunas do PDF, identificando os 70 números impressos por posição, fonte e tamanho. Foram excluídos os números menores de parágrafos. O verificador não importa nem usa o parser de produção.
3. Enunciados e alternativas confrontados após normalização de Unicode, quebras de linha, espaços e hifenização de fim de linha. As diferenças de conteúdo e sobras ficaram registradas; o manifesto de regressão não foi alterado.
4. Inspeção visual das páginas 2–15 do caderno, da capa e dos quatro recortes de imagem existentes. O texto de apoio português foi comparado com os parágrafos 1–9 da página 2; há números soltos de página/marcador e formatação simplificada. O inglês está na página 4 e deveria servir às Q11–20.
5. Gabarito de conhecimentos básicos na página 1 do arquivo de respostas; Q21–70 no primeiro quadro da página 2, explicitamente PROVA 1/Administração. Os outros cargos e quadros foram excluídos da comparação.
6. Não foi verificada publicação definitiva na internet, nem foi julgada a correção acadêmica de cada resposta. Nenhuma decisão de revisão foi registrada em nome do usuário.

A janela atualizada foi acompanhada pela árvore de acessibilidade enquanto o usuário abriu a consulta e a conferência com a fonte. A captura da janela pela automação do Windows apresentou timeout; por isso, a comparação visual foi feita com as páginas renderizadas do documento e os recursos reais do banco, sem alegar inspeção por screenshot da janela.

## Registro por questão

| Número impresso verificado | ID no banco | Página do PDF | Resultado | Observação | Gabarito salvo / documento |
|---:|---:|---:|---|---|---|
| 1 | 1316 | 2 | Conteúdo preservado com ruído | Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. | E / E |
| 2 | 1317 | 2 | Conteúdo preservado com ruído | Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. | B / B |
| 3 | 1318 | 2 | Conteúdo preservado com ruído | Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. | B / B |
| 4 | 1319 | 2 | Conteúdo preservado com ruído | Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | A / A |
| 5 | 1320 | 3 | Conteúdo preservado com ruído | Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. | C / C |
| 6 | 1321 | 3 | Destaque importante perdido | Negrito que identifica a palavra 'que' no enunciado e nas alternativas foi perdido. Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. | C / C |
| 7 | 1322 | 3 | Conteúdo preservado com ruído | Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. | D / D |
| 8 | 1323 | 3 | Conteúdo preservado com ruído | Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | E / E |
| 9 | 1324 | 3 | Destaque importante perdido | Enunciado pede o 'segmento em destaque', mas o destaque que delimita a segunda oração não foi preservado. Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. | B / B |
| 10 | 1325 | 3 | Falha material | Alternativa E recebeu o texto de inglês completo (p.4), fora da alternativa original. Texto português completo vinculado, mas contém números soltos de página/marcador; a formatação original foi simplificada. | A / A |
| 11 | 1326 | 4 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. | E / E |
| 12 | 1327 | 4 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. | D / D |
| 13 | 1328 | 4 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | E / E |
| 14 | 1329 | 5 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. | A / A |
| 15 | 1330 | 5 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. | D / D |
| 16 | 1331 | 5 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. | E / E |
| 17 | 1332 | 5 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. | C / C |
| 18 | 1333 | 5 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | C / C |
| 19 | 1334 | 5 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. | B / B |
| 20 | 1335 | 5 | Falha material | Texto-base de inglês da página 4 não está vinculado à questão. | C / C |
| 21 | 1336 | 6 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | C / C |
| 22 | 1337 | 6 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | B / B |
| 23 | 1338 | 6 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | C / C |
| 24 | 1339 | 6 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | A / A |
| 25 | 1340 | 7 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | D / D |
| 26 | 1341 | 7 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | D / D |
| 27 | 1342 | 7 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | E / E |
| 28 | 1343 | 7 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | E / E |
| 29 | 1344 | 7 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | A / A |
| 30 | 1345 | 8 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | D / D |
| 31 | 1346 | 8 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | C / C |
| 32 | 1347 | 8 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | E / E |
| 33 | 1348 | 8 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | B / B |
| 34 | 1349 | 8 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | B / B |
| 35 | 1350 | 9 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | C / C |
| 36 | 1351 | 9 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | E / E |
| 37 | 1352 | 9 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | C / C |
| 38 | 1353 | 9 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | B / B |
| 39 | 1354 | 10 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | D / D |
| 40 | 1355 | 10 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | A / A |
| 41 | 1356 | 10 | Falha material | A fórmula perdeu μ/σ e os expoentes; o campo textual não preserva a notação visual, e não há imagem vinculada. | C / C |
| 42 | 1357 | 10 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | B / B |
| 43 | 1358 | 10 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | A / A |
| 44 | 1359 | 11 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | A / A |
| 45 | 1360 | 11 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | C / C |
| 46 | 1361 | 11 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | B / B |
| 47 | 1362 | 11 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | A / A |
| 48 | 1363 | 11 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | E / E |
| 49 | 1364 | 11 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | E / E |
| 50 | 1365 | 11 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | D / D |
| 51 | 1366 | 12 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | A / A |
| 52 | 1367 | 12 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | E / E |
| 53 | 1368 | 12 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | C / C |
| 54 | 1369 | 12 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | E / E |
| 55 | 1370 | 12 | Conteúdo preservado com ruído | Tabela completa confirmada no recorte correto; imagem inclui enunciado/alternativas em duplicidade, e o texto da tabela está linearizado. | B / B |
| 56 | 1371 | 12 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | C / C |
| 57 | 1372 | 13 | Conteúdo preservado com ruído | Tabela completa confirmada no recorte correto; imagem inclui enunciado/alternativas em duplicidade, e o texto da tabela está linearizado. | A / A |
| 58 | 1373 | 13 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | A / A |
| 59 | 1374 | 13 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | D / D |
| 60 | 1375 | 13 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | B / B |
| 61 | 1376 | 13 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | E / E |
| 62 | 1377 | 13 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | E / E |
| 63 | 1378 | 14 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | A / A |
| 64 | 1379 | 14 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | B / B |
| 65 | 1380 | 14 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | B / B |
| 66 | 1381 | 14 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | D / D |
| 67 | 1382 | 14 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | B / B |
| 68 | 1383 | 14 | Falha material | Imagem vinculada é da Q70. Tabela esperada: desconto/VPL; imagem mostra empréstimo. Hash do crop idêntico ao Q70. Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. | B / B |
| 69 | 1384 | 15 | Sem divergência material observada | Sem diferença material observada no confronto textual e visual do item. | E / E |
| 70 | 1385 | 15 | Conteúdo preservado com ruído | Há resíduo de página/rodapé no texto salvo, identificado na comparação campo a campo. Tabela completa confirmada no recorte correto; imagem inclui enunciado/alternativas em duplicidade, e o texto da tabela está linearizado. | D / D |

## Fontes e evidências locais

- `C:\Users\Felipe\Desktop\Banco-Questões\samples\TRANSPETRO.pdf` — SHA-256 `b3ce9b933a725a60f438bd9ae4420c900fc37f6e20f72cf23b7a6d90f450a7a5`.
- `C:\Users\Felipe\Desktop\Banco-Questões\samples\TRANSPETRO GABARITO.pdf` — SHA-256 `eb71012fd21909a4c999a8b17496fa2f80247bd1479a6fd48faa773493e681ec`.
- Recortes Q68 e Q70 — mesmo SHA-256 `4a6bf7ed0dc27994dcab885b1ad5d9fb85b46e1bef8ac00c6219d91efe9e8e55`.
- `reports/auditoria_visual_20261026/transpetro_resultado_70.json`: resultados estruturados com observações e gabaritos por questão.
- `reports/auditoria_visual_20261026/transpetro_comparacao_70.json`: diferenças integrais de campos contra a leitura independente.
- `reports/auditoria_visual_20261026/transpetro-p02.png` até `transpetro-p15.png`: páginas do caderno; `transpetro-p10-pdfium.png`: contraprova visual da fórmula.

## Correção da interface realizada nesta conferência

A tela confundia o total não liberado pela revisão com o total sem gabarito. Agora conta separadamente `qtd_com_gabarito`, `qtd_sem_gabarito` e questões liberadas. O botão **Ver questões** abre uma consulta com navegação, conteúdo integral, texto de apoio, imagens e gabarito salvo, sem criar tentativa nem registrar respostas. A opção **Fazer prova** continua condicionada à revisão válida e é novamente verificada pelo domínio.

Foram executados os testes de consulta, repositório e regressões de UI: **20 aprovados**. O teste de consulta usa `PRAGMA query_only=ON`, navega entre questões e comprova que o dump lógico do banco de teste não mudou. Nenhum commit, push ou PR foi realizado.

A melhoria implementada no funil é rastreabilidade, conferência e proteção de uso. A comparação somente leitura com `data/questoes.pre-migration-20261026-134426-612751-823df8.db` confirmou que o conteúdo dos 70 enunciados/contextos/gabaritos/imagens referenciadas e das 350 alternativas é idêntico ao backup anterior à migração. As propostas de reimportação permanecem em staging. Portanto, não foi demonstrada melhora da fidelidade do acervo: os controles mudaram, mas as questões ainda são as mesmas.

Banco real na auditoria final: mesmo SHA-256 de arquivo `261ece62de2aec6389bbc5f582728e189cabeaedd60c7987fac75de93bb6caeb`, `integrity_check=ok`, zero erros FK, 1.385 questões, seis tentativas e nenhuma decisão de conteúdo/gabarito registrada. A auditoria e a consulta não modificaram o banco.
