# Verificação da importação híbrida — 07/09/2026

## Resultado

- Suíte completa: 145 testes aprovados; conferência visual da revisão e testes direcionados adicionais para a limpeza de cabeçalho Embrapa.

- 23 cadernos: 1.042 → 1.239 questões (+197), sem redução de contagem por arquivo.
- Dois cadernos Embrapa: 2 → 100 itens cada, preservando texto-base e mudança de colunas/largura.
- Um caderno de Analista de Sistemas: 44 → 45 questões, com correção de números capturados dentro de enunciados.
- FEPESE: mantém 50 questões, agora numeradas de 1 a 50 e com o texto-base correspondente. A contagem anterior incluía números duplicados e enunciados misturados.
- PF 2025 fornecida: permanece coberta pelo teste dos 120 itens, incluindo as anulações 96/97.
- Comparação de gabaritos: 19 associações examinadas; 12 preservadas e 7 alteradas após seleção de contexto e remoção de associações indevidas. Nenhum conflito residual nesses resultados finais.

Não se trata de 100% de acertividade: há cadernos ainda incompletos, textos complexos e elementos gráficos que exigem revisão. O conjunto de referência congela o comportamento atual; não certifica a correção humana integral de todas as questões.

## Alterações que a contagem anterior escondia

A comparação revelou respostas de outros cargos sobrescrevendo as do cargo solicitado. A validação antiga de “quantidade de gabaritos encontrados” não detectava esse problema. Agora cabeçalhos, códigos e colunas delimitam a seleção, e respostas conflitantes ficam pendentes.

O arquivo da Transpetro reúne 28 provas. A configuração anterior o tratava como arquivo único. O caderno identifica “PROVA 1 - ADMINISTRAÇÃO”; a associação foi corrigida para esse cabeçalho, incluindo o bloco básico comum.

A prova de Agente Administrativo I de Morungaba agora usa 40 respostas de seu bloco; antes, respostas de outros cargos ampliavam o mapa para 50. Isso é correção da seleção, não perda de dez respostas dessa prova.

## Contagens por caderno

| Caderno | Anterior | Híbrido | Conteúdo anterior idêntico |
|---|---:|---:|---|
| administrador-FGV.pdf | 80 | 80 | Sim |
| agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf | 50 | 50 | Não; alteração registrada |
| agente_especializado_analista_de_sistemas.pdf | 60 | 60 | Sim |
| analista_analise_de_sistema_desenvolvimento_de_sistema.pdf | 57 | 57 | Sim |
| analista_de_planejamento_e_orcamento_especialidade_governanca_e_gestao_de_projetos_de_ti-CEBRASPE.pdf | 100 | 100 | Sim |
| agente_administrativo_auxiliar_i.pdf | 30 | 30 | Não; alteração registrada |
| agente_administrativo_i-1.pdf | 25 | 25 | Sim |
| agente_administrativo_i-2.pdf | 30 | 30 | Sim |
| agente_administrativo_i-3.pdf | 49 | 49 | Sim |
| agente_administrativo_i-4.pdf | 40 | 40 | Sim |
| agente_administrativo_i.pdf | 40 | 40 | Sim |
| agente_nivel_superior_analista_de_sistemas.pdf | 40 | 40 | Sim |
| analista_adm_desenvolvimento_sistemas.pdf | 30 | 30 | Não; alteração registrada |
| analista_administrativo_iii_analista_de_sistemas.pdf | 79 | 79 | Sim |
| analista_analista_de_sistemas.pdf | 44 | 45 | Não; alteração registrada |
| analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf | 2 | 100 | Não; alteração registrada |
| analista_area_ciencias_exatas_e_da_terra_subarea_sistemas_de_informacao.pdf | 2 | 100 | Não; alteração registrada |
| analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf | 30 | 30 | Sim |
| analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf | 40 | 40 | Sim |
| auditor_fiscal.pdf | 30 | 30 | Não; alteração registrada |
| prova1_auditor_fiscal.pdf | 45 | 45 | Não; alteração registrada |
| provas_2e3_auditor_fiscal.pdf | 69 | 69 | Não; alteração registrada |
| TRANSPETRO.pdf | 70 | 70 | Sim |

## Gabaritos alterados

| Caderno | Quantidade final | Números com resposta diferente ou removida/adicionada |
|---|---:|---:|
| administrador-fgv.pdf | 80 | 63 |
| analista_analista_de_sistemas.pdf | 50 | 18 |
| agente_administrativo_i.pdf | 40 | 42 |
| agente_administrativo_i-3.pdf | 55 | 24 |
| analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf | 45 | 13 |
| auditor_fiscal.pdf | 40 | 13 |
| transpetro.pdf | 70 | 44 |

## Evidências e reprodução

- `tests/test_importacao_hibrida.py`: exemplos positivos/negativos, texto-base repetido, colunas, tipos mistos, anulações e fronteiras de cargo.
- `tests/test_cebraspe_2025.py`: regressões da prova fornecida.
- `scripts/verificar_regressoes_perfis.py`: passou em 23/23 PDFs contra a referência híbrida, comparando SHA-256 do conteúdo e quantidade. Não grava no banco nem atualiza referências.
- `tests/fixtures/perfis_manifest.json`: referência anterior preservada.
- `tests/fixtures/perfis_hibridos_manifest.json`: referência nova, separada, após análise das diferenças.
- `scripts/diagnosticar_formato.py`: relatório por arquivo com perfis, candidatos e pendências.

Os PDFs locais podem não acompanhar o Git; testes de integração indicam ausência de fonte e o verificador de referências falha se um PDF estiver ausente. Consulte `IMPORTACAO_HIBRIDA.md` para formatos, organização e limites.

Esta etapa validou a importação sem regravar o acervo existente. Alterar o algoritmo não corrige automaticamente os registros já salvos.
