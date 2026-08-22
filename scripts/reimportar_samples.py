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
from src.importador.parser import parsear_questoes


SAMPLES = ROOT / "samples"
DATABASE = ROOT / "data" / "questoes.db"
GABARITO_TRANSPETRO = SAMPLES / "TRANSPETRO GABARITO.pdf"


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
        questoes = parsear_questoes(texto)
        if caminho.name.lower() == "transpetro.pdf":
            gabaritos = extrair_gabaritos_pdf(str(GABARITO_TRANSPETRO))
            for numero, questao in enumerate(questoes, 1):
                questao["gabarito"] = gabaritos.get(numero)
        dados = [_dados_questao(questao) for questao in questoes]
        resultados.append(
            {
                "arquivo": str(caminho.relative_to(ROOT)),
                "caracteres": len(texto),
                "questoes": len(questoes),
                "alta": sum(q["confianca"] == "alta" for q in questoes),
                "media": sum(q["confianca"] == "media" for q in questoes),
                "baixa": sum(q["confianca"] == "baixa" for q in questoes),
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
