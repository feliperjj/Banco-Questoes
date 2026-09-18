"""Reimporta os PDFs de questões dos samples no banco local de teste.

O script processa todos os PDFs antes de tocar no banco. Só depois de uma
extração bem-sucedida substitui as questões e seus dados dependentes.
"""

from __future__ import annotations

import json
import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.database import db, init_db
from src.db.models import (
    ALL_MODELS,
    ProgressoTentativa,
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
from src.importador.catalogo import carregar_catalogo, normalizar_chave
from src.importador.validacao import associar_gabaritos, validar_gabarito


SAMPLES = ROOT / "samples"
DATABASE = ROOT / "data" / "questoes.db"
CATALOGO = carregar_catalogo(ROOT / "config" / "gabaritos.json")

# Evidências explícitas encontradas na capa/organização do próprio sample.
# Não usar o domínio de download (por exemplo, PCI Concursos) como banca.
BANCAS_CONFIRMADAS = {
    "agente_especializado_analista_de_sistemas.pdf": "FGV",
    "analista_area_de_apoio_especializado_tecnologia_da_informacao_desenvolvimento_de_sistemas.pdf": "FGV",
    "lote_2026_08_22/agente_administrativo_i-4.pdf": "Avança SP",
    "lote_2026_08_22/auditor_fiscal.pdf": "FUNDATEC",
}


def _registro_do_sample(caminho: Path) -> dict | None:
    chave = normalizar_chave(caminho.relative_to(SAMPLES))
    return CATALOGO.get(chave)


def _gabarito_do_sample(caminho: Path, questoes: list[dict]) -> dict[int, str]:
    registro = _registro_do_sample(caminho)
    if not registro:
        return {}
    codigo = registro.get("codigo") or registro.get("prova")
    numeros = {int(q.get("numero", indice)) for indice, q in enumerate(questoes, 1)}
    gabaritos = extrair_gabaritos_pdf(
        str(SAMPLES / registro["gabarito"]), codigo, registro.get("cargo") or None,
        numeros_esperados=numeros,
    )
    for numero in registro.get("anuladas", []):
        gabaritos[int(numero)] = "X"
    return gabaritos


def _aplicar_gabarito_validado(questoes: list[dict], gabaritos: dict[int, str]) -> int:
    """Aplica somente respostas com número explícito correspondente.

    A quantidade pode divergir: uma questão ausente no PDF não deve fazer o
    gabarito das seguintes andar uma posição. Questões sem par permanecem sem
    resposta e são catalogadas para revisão.
    """
    return associar_gabaritos(questoes, gabaritos)["vinculados"]


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
    for modelo in (ProgressoTentativa, Resposta, Tentativa, RevisaoEspacada, ProvaQuestao, Prova, Alternativa, Questao):
        modelo.delete().execute()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reimportação com backup e conferência de cobertura")
    parser.add_argument("--min-cobertura", type=float, default=0, help="Exige cobertura acima deste percentual antes de alterar o banco")
    args = parser.parse_args()
    pdfs = sorted(path for path in SAMPLES.rglob("*.pdf") if _is_question_pdf(path))
    if not pdfs:
        raise RuntimeError("Nenhum PDF encontrado; o banco foi preservado.")
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
        registro_gabarito = _registro_do_sample(caminho)
        gabaritos = _gabarito_do_sample(caminho, questoes)
        quantidade_esperada = quantidade_declarada(texto)
        cargo_confirmado = bool(registro_gabarito)
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
        resultados[-1]["sha256_caderno"] = hashlib.sha256(caminho.read_bytes()).hexdigest()
        resultados[-1]["associacao"] = registro_gabarito
        resultados[-1]["itens"] = [{"numero": q["numero"], "gabarito": q.get("gabarito")} for q in questoes]
        print(f"Extraído: {caminho.name}: {len(questoes)} questões, {gabaritos_aplicados} vínculos", file=sys.stderr, flush=True)

    if not any(dados_importacao):
        raise RuntimeError("Nenhuma questão extraída; o banco foi preservado.")
    cobertura_prevista = 100 * sum(r["gabaritos"] for r in resultados) / sum(len(d) for d in dados_importacao)
    if cobertura_prevista <= args.min_cobertura:
        raise RuntimeError(f"Cobertura {cobertura_prevista:.2f}% não supera {args.min_cobertura:.2f}%; banco preservado.")
    backup = None
    if DATABASE.exists():
        backup = DATABASE.with_name(f"questoes.pre-reimport-{datetime.now():%Y%m%d-%H%M%S-%f}.db")
        with sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True) as origem, sqlite3.connect(backup) as destino:
            origem.backup(destino)
            if destino.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup não passou na verificação; banco preservado.")
    init_db()
    from src.models.questoes_repo import _criar_questao_sem_transacao

    with db.atomic():
        _limpar_banco()
        total = 0
        for dados_arquivo, resultado in zip(dados_importacao, resultados):
            for dados, item in zip(dados_arquivo, resultado["itens"]):
                item["id"] = _criar_questao_sem_transacao(dados)
                total += 1

    resumo = {
        "arquivos": len(pdfs),
        "questoes_importadas": total,
        "gabaritos_persistidos": Questao.select().where(Questao.gabarito.is_null(False), Questao.gabarito != "").count(),
        "backup": str(backup) if backup else None,
        "por_arquivo": resultados,
    }
    resumo["cobertura_percentual"] = 100 * resumo["gabaritos_persistidos"] / total
    out = ROOT / "reports" / "reimportacao_samples.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
