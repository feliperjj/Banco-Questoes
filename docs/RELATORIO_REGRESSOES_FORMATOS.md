# Importação por formato e regressões — 05/09/2026

## Resultado e limites

A prova PF/Agente Administrativo 2025 fornecida passou de 2 para 120 itens, com contexto compartilhado e numeração 1–120. O gabarito foi selecionado pelos códigos `094_PF_CB2_01;094_PF_015_01`: 118 respostas e 2 anulações (96 e 97). Os 120 registros foram gravados; duplicatas defeituosas foram desativadas. Backup: `data/questoes.pre-pf2025-20260905-162712.db`.

Isso verifica cobertura, alinhamento e estrutura; não representa revisão humana integral dos 120 enunciados nem promessa de 100% de acerto.

## Separação por formato

- `cebraspe_layout.py`: leitura por coordenadas e recuos, preservando texto-base. Tem contrato de sequência e contexto; só aceita o layout reconhecido.
- `perfis/certo_errado.py`: segmentação sequencial e com justificativas.
- `perfis/multipla_escolha.py`: segmentação e avaliação de numeração de múltipla escolha.
- `perfis/segmentacao.py`: roteamento e identificação versionada; marcadores explícitos têm prioridade. Formato genérico gera aviso de revisão.
- `parser.py`: normalização, metadados e construção das questões.

O perfil fica disponível nos dados da revisão, nos logs e na dica do arquivo na tela de importação. Ainda não é persistido como coluna do banco.

Esta é uma migração inicial: permanecem restrições conservadoras de banca nos formatos legados FGV/IESES e no reconhecimento do layout Cebraspe. Não foram liberadas para qualquer banca sem exemplos de validação. O extrator genérico e parte das normalizações continuam compartilhados.

## Regressões encontradas e corrigidas

1. Detectar colunas por “julgue” indiscriminadamente reduzia um caderno IADES de 57 para 2; o reconhecimento foi restringido ao layout comprovado.
2. Reconhecer títulos tardios como início de prova eliminava 15 itens em dois cadernos de 40 questões; a exceção agora exige os marcadores do contexto estruturado.
3. Buscar a palavra “justificativa” em qualquer posição descartava itens comuns; agora apenas o título da seção é reconhecido.
4. Ignorar X no gabarito deslocava respostas após anulações; X preserva sua posição e grades desalinhadas são recusadas.
5. Seleção de cargo podia vazar para páginas de outros cargos; códigos impressos são comparados exatamente por página.

## Verificação reproduzível

`python -m pytest -q`

`python scripts/verificar_regressoes_perfis.py`

O segundo comando é somente leitura e compara quantidade e SHA-256 do conteúdo normalizado das questões com `tests/fixtures/perfis_manifest.json`. Arquivo ausente ou conteúdo diferente falha. Nunca atualiza a referência automaticamente. Perfis e avisos não entram na assinatura; enunciado, alternativas, número, tipo e demais campos existentes entram.

A referência preserva comportamento, inclusive defeitos conhecidos. Os dois cadernos Embrapa que extraem apenas 2 itens continuam pendentes. Para um novo perfil, adicionar exemplos positivos e negativos, validar texto/alternativas/gabarito contra a fonte e revisar qualquer mudança de referência; contagem sozinha não basta.

## Cadernos de referência

As 1.042 questões abaixo são o total extraído dos 23 PDFs de teste, não o total do banco salvo nem uma medida de acertividade.

| Arquivo | Antes | Depois | Números perdidos |
|---|---:|---:|---:|
| samples/administrador-FGV.pdf | 80 | 80 | 0 |
| samples/agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf | 50 | 50 | 0 |
| samples/agente_especializado_analista_de_sistemas.pdf | 60 | 60 | 0 |
| samples/analista_analise_de_sistema_desenvolvimento_de_sistema.pdf | 57 | 57 | 0 |
| samples/analista_de_planejamento_e_orcamento_especialidade_governanca_e_gestao_de_projetos_de_ti-CEBRASPE.pdf | 100 | 100 | 0 |
| samples/lote_2026_08_22/agente_administrativo_auxiliar_i.pdf | 30 | 30 | 0 |
| samples/lote_2026_08_22/agente_administrativo_i-1.pdf | 25 | 25 | 0 |
| samples/lote_2026_08_22/agente_administrativo_i-2.pdf | 30 | 30 | 0 |
| samples/lote_2026_08_22/agente_administrativo_i-3.pdf | 49 | 49 | 0 |
| samples/lote_2026_08_22/agente_administrativo_i-4.pdf | 40 | 40 | 0 |
| samples/lote_2026_08_22/agente_administrativo_i.pdf | 40 | 40 | 0 |
| samples/lote_2026_08_22/agente_nivel_superior_analista_de_sistemas.pdf | 40 | 40 | 0 |
| samples/lote_2026_08_22/analista_adm_desenvolvimento_sistemas.pdf | 30 | 30 | 0 |
| samples/lote_2026_08_22/analista_administrativo_iii_analista_de_sistemas.pdf | 79 | 79 | 0 |
| samples/lote_2026_08_22/analista_analista_de_sistemas.pdf | 44 | 44 | 0 |
| samples/lote_2026_08_22/analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf | 2 | 2 | 0 |
| samples/lote_2026_08_22/analista_area_ciencias_exatas_e_da_terra_subarea_sistemas_de_informacao.pdf | 2 | 2 | 0 |
| samples/lote_2026_08_22/analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf | 30 | 30 | 0 |
| samples/lote_2026_08_22/analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf | 40 | 40 | 0 |
| samples/lote_2026_08_22/auditor_fiscal.pdf | 30 | 30 | 0 |
| samples/lote_2026_08_22/prova1_auditor_fiscal.pdf | 45 | 45 | 0 |
| samples/lote_2026_08_22/provas_2e3_auditor_fiscal.pdf | 69 | 69 | 0 |
| samples/TRANSPETRO.pdf | 70 | 70 | 0 |

Gabaritos: 19 comparações, 0 respostas alteradas e 0 números perdidos nas referências.
