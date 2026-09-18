# Reimportação e cobertura de gabaritos — setembro de 2026

## Resultado confirmado no banco

- 23 PDFs de questões processados; 984 questões persistidas.
- 909 questões com gabarito (92,38%), sendo 17 anuladas; 75 sem vínculo.
- Baseline reproduzido antes das mudanças: 820/979 (83,76%). Ganho de 89 vínculos e 8,62 pontos percentuais.
- Sem as anuladas no numerador e denominador: 892/967 (92,24%).
- Conferência dos 984 IDs e gabaritos do relatório contra o SQLite: zero divergências.
- `PRAGMA integrity_check`: `ok`; `PRAGMA foreign_key_check`: nenhuma violação.
- 66 testes passaram, incluindo referências transcritas dos PDFs para 170 respostas (CREA-SC, Paraisópolis e MPO).

**Métrica:** cobertura das questões extraídas com vínculo ao gabarito. Não é uma estimativa de precisão baseada em revisão humana de todo o corpus, nem a proporção de todas as questões existentes nas páginas dos PDFs. A extração ainda é incompleta em alguns cadernos.

## Mudanças que produziram o ganho

- CREA-SC: identificação explícita da coluna T1; recuperação das duas colunas do caderno e das 40 questões, sem duplicação.
- Paraisópolis: leitura da linha exata do cargo e dos números escritos nas células, inclusive a anulação da questão 24.
- FGV/IESES: enumerações internas deixam de substituir números oficiais quando o formato alternativo melhora a estrutura. O parser anterior permanece quando a alternativa perde números válidos.
- MPES: provas discursivas deixam de entrar como objetivas. A palavra “justificativas” no enunciado não interrompe mais a questão.
- MPO: substituição do Cargo 1 pelo bloco comum da página 9. Corrigidas 56 respostas; os 100 itens atualmente retidos pelo parser pertencem à P1.
- Reimportação: backup SQLite consistente e validado antes da limpeza, rastreio de número oficial/ID/gabarito por arquivo e opção `--min-cobertura 90`.

## Comparação por arquivo

| Caderno | Questões antes → depois | Vínculos antes → depois | Pendentes |
|---|---:|---:|---:|
| administrador-FGV.pdf | 75 → 75 | 75 → 75 | 0 |
| agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf | 51 → 51 | 49 → 49 | 2 |
| agente_especializado_analista_de_sistemas.pdf | 61 → 60 | 51 → 60 | 0 |
| analista_analise_de_sistema_desenvolvimento_de_sistema.pdf | 6 → 6 | 0 → 0 | 6 |
| analista_de_planejamento_e_orcamento_especialidade_governanca_e_gestao_de_projetos_de_ti-CEBRASPE.pdf | 100 → 100 | 100 → 100 | 0 |
| agente_administrativo_auxiliar_i.pdf | 30 → 30 | 0 → 0 | 30 |
| agente_administrativo_i-1.pdf | 25 → 25 | 25 → 25 | 0 |
| agente_administrativo_i-2.pdf | 30 → 30 | 0 → 30 | 0 |
| agente_administrativo_i-3.pdf | 49 → 49 | 49 → 49 | 0 |
| agente_administrativo_i-4.pdf | 40 → 40 | 40 → 40 | 0 |
| agente_administrativo_i.pdf | 40 → 40 | 40 → 40 | 0 |
| agente_nivel_superior_analista_de_sistemas.pdf | 35 → 40 | 0 → 40 | 0 |
| analista_adm_desenvolvimento_sistemas.pdf | 30 → 30 | 29 → 29 | 1 |
| analista_administrativo_iii_analista_de_sistemas.pdf | 79 → 79 | 70 → 79 | 0 |
| analista_analista_de_sistemas.pdf | 43 → 43 | 41 → 41 | 2 |
| analista_area_ciencias_agrarias_subarea_sistemas_de_producao_animal.pdf | 2 → 2 | 0 → 0 | 2 |
| analista_area_ciencias_exatas_e_da_terra_subarea_sistemas_de_informacao.pdf | 2 → 2 | 0 → 0 | 2 |
| analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf | 29 → 30 | 29 → 30 | 0 |
| analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf | 40 → 40 | 35 → 35 | 5 |
| auditor_fiscal.pdf | 30 → 30 | 28 → 28 | 2 |
| prova1_auditor_fiscal.pdf | 46 → 46 | 40 → 40 | 6 |
| provas_2e3_auditor_fiscal.pdf | 66 → 66 | 54 → 54 | 12 |
| TRANSPETRO.pdf | 70 → 70 | 65 → 65 | 5 |

O total cresceu de 979 para 984: CREA-SC ganhou cinco questões, DPE/RS ganhou uma e MPES perdeu um registro líquido ao corrigir a segmentação de objetivas e discursivas. Nenhum caderno foi removido da avaliação.

## Limitações e próximos passos

- São José do Cerrito responde por 30 das 75 pendências; não foi encontrado um gabarito correspondente entre os arquivos locais. Não foi usado gabarito de outro concurso.
- Persistem duplicidades de numeração e falhas pontuais de extração em outros cadernos, discriminadas no diagnóstico local.
- O MPO tem P1 e P2 com numeração reiniciada. A P2 precisa de importação separada por seção; a cobertura acima usa os 100 itens da P1 atualmente importados.
- Os cadernos IADES e EMBRAPA têm extração muito parcial; os pequenos totais da tabela não representam a extensão integral das provas.
- Há gabaritos preliminares no catálogo. O vínculo confirmado ao documento não os transforma em gabaritos definitivos.

## Backup e reprodução

Backup automático validado: `questoes.pre-reimport-20260904-230436-126641.db`, em `data/`. Ele preserva as 1.049 questões existentes imediatamente antes da reimportação. Esse banco local tinha conteúdo adicional e não é o denominador do benchmark reproduzido de 979 questões.

A reimportação substitui os dados locais de questões e limpa provas, tentativas, respostas, revisões e rascunhos dependentes. O backup preserva o estado anterior.

```powershell
.venv/Scripts/python.exe scripts/diagnosticar_samples.py
.venv/Scripts/python.exe scripts/reimportar_samples.py --min-cobertura 90
.venv/Scripts/python.exe -m pytest -q
```

Relatórios locais: `reports/reimportacao_samples.json` (IDs, números oficiais, respostas e hash dos cadernos), `reports/diagnostico_samples.json`, `reports/auditoria_extracao.json` e `reports/auditoria_match/baseline.json`. PDFs, banco e relatórios locais permanecem ignorados pelo Git.
