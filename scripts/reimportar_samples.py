"""Reimporta os PDFs de questões dos samples no banco local de teste.

O script processa todos os PDFs antes de tocar no banco. Só depois de uma
extração bem-sucedida substitui as questões e seus dados dependentes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.database import db, init_db
from src.db.models import (
    ALL_MODELS,
    Alternativa,
    Prova,
    ProvaQuestao,
    Questao,
    Resposta,
    RevisaoEspacada,
    Tentativa,
)
from src.importador.extrator import extrair_gabaritos_pdf, extrair_texto
from src.importador.parser import parsear_questoes, quantidade_declarada
from src.importador.validacao import validar_gabarito


SAMPLES = ROOT / "samples"
DATABASE = ROOT / "data" / "questoes.db"
GABARITO_TRANSPETRO = SAMPLES / "TRANSPETRO GABARITO.pdf"

# Só entram associações confirmadas pelo cabeçalho do PDF. Um gabarito com
# vários cargos não deve ser aplicado por aproximação de nome.
GABARITOS_CONFIRMADOS = {
    "administrador-fgv.pdf": ("GABARITO-FGV.pdf", "ADMINISTRADOR", "PROVA TIPO 1"),
    "analista_administrativo_iii_analista_de_sistemas.pdf": (
        "lote_2026_08_22/gabarito-2.pdf", "ANALISTA LEGISLATIVO III - ANALISTA DE SISTEMAS", "PROVA TIPO 1"
    ),
    "analista_analista_de_sistemas.pdf": (
        "lote_2026_08_22/gabaritos_definitivos.pdf", "IBFC_04_ANALISTA - ANALISTA DE SISTEMAS", None
    ),
    "agente_administrativo_i.pdf": (
        "lote_2026_08_22/gabarito_oficial-1.pdf", "AGENTE ADMINISTRATIVO I", None
    ),
    "agente_administrativo_i-4.pdf": (
        "lote_2026_08_22/gabarito-6.pdf", "AGENTE ADMINISTRATIVO I", None
    ),
    "agente_de_tecnologia_da_informacao_e_comunicacao_analista_de_sistemas.pdf": (
        "gabarito_definitivox.pdf", "S201 Analista de Sistemas", None
    ),
    "analista_producao_redes_suporte_de_banco_de_dados_e_suporte_de_sistemas.pdf": (
        "lote_2026_08_22/gabarito-1.pdf",
        "IBFC_04",
        None,
    ),
    "auditor_fiscal.pdf": (
        "lote_2026_08_22/gabarito-7.pdf", "Auditor Fiscal", None
    ),
    "analista_de_planejamento_e_orcamento_especialidade_governanca_e_gestao_de_projetos_de_ti-cebraspe.pdf": (
        "gabarito_definitivo.pdf-CEBRASPE.pdf", "CARGO 1", None
    ),
}

# Evidências explícitas encontradas na capa/organização do próprio sample.
# Não usar o domínio de download (por exemplo, PCI Concursos) como banca.
BANCAS_CONFIRMADAS = {
    "agente_especializado_analista_de_sistemas.pdf": "FGV",
    "analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf": "FGV",
    "lote_2026_08_22/agente_administrativo_i-4.pdf": "Avança SP",
    "lote_2026_08_22/auditor_fiscal.pdf": "FUNDATEC",
}


def _gabarito_do_sample(caminho: Path) -> dict[int, str]:
    if caminho.name.lower() == "transpetro.pdf":
        return extrair_gabaritos_pdf(str(GABARITO_TRANSPETRO))
    chave = caminho.name.lower()
    configuracao = GABARITOS_CONFIRMADOS.get(chave)
    if not configuracao:
        return {}
    arquivo, cargo, codigo = configuracao
    return extrair_gabaritos_pdf(str(SAMPLES / arquivo), codigo, cargo)


def _aplicar_gabarito_validado(questoes: list[dict], gabaritos: dict[int, str]) -> int:
    """Aplica somente respostas com número explícito correspondente.

    A quantidade pode divergir: uma questão ausente no PDF não deve fazer o
    gabarito das seguintes andar uma posição. Questões sem par permanecem sem
    resposta e são catalogadas para revisão.
    """
    associados = 0
    usados = set()
    for indice, questao in enumerate(questoes, 1):
        numero = questao.get("numero", indice)
        if numero not in gabaritos or numero in usados:
            continue
        resposta = gabaritos[numero]
        questao["gabarito"] = "Anulada" if resposta == "X" else resposta
        usados.add(numero)
        associados += 1
    return associados


def _is_question_pdf(path: Path) -> bool:
    nome = path.name.lower()
    return not (nome.startswith("gab") or "gabarito" in nome)


def _dados_questao(questao: dict) -> dict:
    return {
        "enunciado": questao["enunciado"],
        "tipo": questao["tipo"],
        "alternativas": questao.get("alternativas") or [],
        "disciplina": questao.get("disciplina") or "",
        "topico": questao.get("topico") or "",
        "banca": questao.get("banca") or "",
        "ano": questao.get("ano"),
        "dificuldade": "media",
        "gabarito": questao.get("gabarito"),
    }


def _limpar_banco():
    # A ordem respeita as foreign keys do SQLite.
    for modelo in (Resposta, Tentativa, RevisaoEspacada, ProvaQuestao, Prova, Alternativa, Questao):
        modelo.delete().execute()


def main() -> None:
    pdfs = sorted(path for path in SAMPLES.rglob("*.pdf") if _is_question_pdf(path))
    resultados = []
    dados_importacao = []

    # Primeiro extrai tudo; uma falha aqui não destrói o banco atual.
    for caminho in pdfs:
        texto = extrair_texto(str(caminho))
        questoes = parsear_questoes(texto, str(caminho))
        banca_confirmada = BANCAS_CONFIRMADAS.get(str(caminho.relative_to(SAMPLES)).replace("\\", "/"))
        if banca_confirmada:
            for questao in questoes:
                questao["banca"] = banca_confirmada
        gabaritos = _gabarito_do_sample(caminho)
        quantidade_esperada = quantidade_declarada(texto)
        cargo_confirmado = caminho.name.lower() in GABARITOS_CONFIRMADOS or caminho.name.lower() == "transpetro.pdf"
        validacao = validar_gabarito(
            questoes,
            gabaritos,
            cargo_encontrado=cargo_confirmado or not gabaritos,
            quantidade_esperada=quantidade_esperada,
        )
        gabaritos_aplicados = _aplicar_gabarito_validado(questoes, gabaritos)
        dados = [_dados_questao(questao) for questao in questoes]
        resultados.append(
            {
                "arquivo": str(caminho.relative_to(ROOT)),
                "caracteres": len(texto),
                "questoes": len(questoes),
                "alta": sum(q["confianca"] == "alta" for q in questoes),
                "media": sum(q["confianca"] == "media" for q in questoes),
                "baixa": sum(q["confianca"] == "baixa" for q in questoes),
                "gabaritos": gabaritos_aplicados,
                "validacao": validacao,
                "revisao_manual": validacao["revisao_manual"],
                "banca": next((q.get("banca") for q in questoes if q.get("banca")), ""),
                "pcimarkpci": "pcimarkpci" in texto.lower(),
            }
        )
        dados_importacao.append(dados)

    init_db()
    from src.models.questoes_repo import _criar_questao_sem_transacao

    with db.atomic():
        _limpar_banco()
        total = 0
        for dados_arquivo in dados_importacao:
            for dados in dados_arquivo:
                _criar_questao_sem_transacao(dados)
                total += 1

    resumo = {
        "arquivos": len(pdfs),
        "questoes_importadas": total,
        "por_arquivo": resultados,
    }
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
