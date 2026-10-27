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

from src.config import DB_PATH, REPORTS_DIR
from src.importador.extrator import extrair_gabaritos_pdf, extrair_texto
from src.importador.gabaritos import diagnosticar_gabarito_pdf
from src.importador.perfis.documentos import classificar_caderno, PerfilDocumento, pontuar_associacao
from src.importador.parser import parsear_questoes, quantidade_declarada
from src.importador.imagens import anexar_imagens_referenciadas
from src.importador.catalogo import carregar_catalogo, normalizar_chave
from src.importador.validacao import associar_gabaritos, numero_oficial_explicitamente_extraido, validar_gabarito
from src.importador.reimportacao_staging import stage_proposals


SAMPLES = ROOT / "samples"
DATABASE = DB_PATH
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
    numeros = {numero for q in questoes
               for numero, motivo in [numero_oficial_explicitamente_extraido(q)]
               if numero is not None}
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
        # Número lido no marcador do PDF é uma proposta para o campo oficial;
        # a comparação continua pendente de conferência humana.
        "numero_oficial": questao.get("numero"),
        "enunciado": questao["enunciado"],
        "texto_apoio": questao.get("texto_apoio") or None,
        "tipo": questao["tipo"],
        "alternativas": questao.get("alternativas") or [],
        "disciplina": questao.get("disciplina") or "",
        "topico": questao.get("topico") or "",
        "banca": questao.get("banca") or "",
        "ano": questao.get("ano"),
        "dificuldade": "media",
        "gabarito": questao.get("gabarito"),
        "imagem_path": questao.get("imagem_path"),
    }


def _comparar_com_acervo(db_path: Path, resultados: list[dict], dados_importacao: list[list[dict]]) -> dict:
    """Compara por arquivo e ordem, sem tratar a ordem como número oficial."""
    if not db_path.is_file():
        return {"status": "banco_ausente", "por_arquivo": []}
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"provas_cadastradas", "prova_cadastrada_questoes", "questoes", "alternativas"}
        if not required.issubset(tables):
            return {"status": "schema_incompativel", "por_arquivo": []}
        questao_columns = {row[1] for row in connection.execute('PRAGMA table_info("questoes")')}
        names = [field for field in ("numero_oficial", "enunciado", "texto_apoio", "tipo", "disciplina", "banca", "ano", "cargo", "orgao", "dificuldade", "gabarito", "comentario", "imagem_path") if field in questao_columns]
        query = (
            "SELECT pc.id AS prova_id, pc.arquivo_questoes, pq.ordem, q.id AS questao_id, "
            + ", ".join(f'q."{name}" AS "{name}"' for name in names)
            + " FROM provas_cadastradas pc JOIN prova_cadastrada_questoes pq ON pq.prova_cadastrada_id = pc.id "
            + "JOIN questoes q ON q.id = pq.questao_id ORDER BY pc.id, pq.ordem"
        )
        links = connection.execute(query).fetchall()
        grouped = {}
        for row in links:
            key = str(row["arquivo_questoes"] or "").replace("\\", "/").casefold()
            grouped.setdefault(key, {}).setdefault(row["prova_id"], []).append(dict(row))
        alternatives = {}
        for row in connection.execute("SELECT questao_id, letra, texto FROM alternativas ORDER BY questao_id, letra"):
            alternatives.setdefault(row[0], []).append({"letra": row[1], "texto": row[2]})
        attempt_counts = {}
        if "provas" in tables and "prova_questoes" in tables and "tentativas" in tables:
            for row in connection.execute(
                "SELECT pc.arquivo_questoes, COUNT(DISTINCT t.id) "
                "FROM provas_cadastradas pc JOIN prova_cadastrada_questoes pcq ON pcq.prova_cadastrada_id=pc.id "
                "JOIN prova_questoes pq ON pq.questao_id=pcq.questao_id JOIN tentativas t ON t.prova_id=pq.prova_id "
                "GROUP BY pc.arquivo_questoes"
            ):
                attempt_counts[str(row[0] or "").replace("\\", "/").casefold()] = row[1]

    report = []
    for result, incoming in zip(resultados, dados_importacao):
        key = result["arquivo"].replace("\\", "/").casefold()
        matches = grouped.get(key, {})
        file_result = {"arquivo": result["arquivo"], "sha256_fonte": result.get("sha256_caderno"),
                       "fonte_path": str(ROOT / result["arquivo"]),
                       "provas_cadastradas_correspondentes": list(matches),
                       "tentativas_relacionadas": attempt_counts.get(key, 0), "itens": []}
        if len(matches) != 1:
            file_result["status"] = "sem_correspondencia" if not matches else "correspondencia_ambigua"
            file_result["itens"] = [{"ordem_candidata": index, "numero_oficial_extraido": item.get("numero_oficial"), "status": "revisao_manual_necessaria", "proposta": item}
                                    for index, item in enumerate(incoming, 1)]
            report.append(file_result)
            continue
        proof_id, old_links = next(iter(matches.items()))
        by_order = {int(row["ordem"]): row for row in old_links}
        file_result["status"] = "comparacao_por_ordem; numero_oficial_nao_inferido_da_ordem"
        for index, item in enumerate(incoming, 1):
            old = by_order.get(index)
            proposal = dict(item)
            if old is None:
                file_result["itens"].append({"ordem_candidata": index, "numero_oficial_extraido": item.get("numero"), "status": "questao_nova_proposta", "proposta": proposal})
                continue
            current = {name: old.get(name) for name in proposal if name in old.keys()}
            current["alternativas"] = alternatives.get(old["questao_id"], [])
            fields = set(current) | set(proposal)
            normalize = lambda value: None if value == "" else value
            changes = {field: {"atual": current.get(field), "proposto": proposal.get(field)} for field in sorted(fields) if normalize(current.get(field)) != normalize(proposal.get(field))}
            file_result["itens"].append({
                "questao_id": old["questao_id"], "ordem_candidata": index,
                "numero_oficial_atual": old.get("numero_oficial"),
                "numero_oficial_extraido": item.get("numero"),
                "status": "sem_diferenca_estrutural_detectada" if not changes else "proposta_pendente_de_conferencia",
                "conteudo_atual": current,
                "proposta": proposal,
                "diferencas": changes,
            })
        report.append(file_result)
    return {"status": "simulacao_somente_leitura", "por_arquivo": report}


def _salvar_checkpoint(resultados: list[dict], dados_importacao: list[list[dict]], checkpoint: Path) -> None:
    checkpoint.parent.mkdir(exist_ok=True)
    temporario = checkpoint.with_suffix(".tmp")
    temporario.write_text(
        json.dumps({"por_arquivo": resultados, "dados_importacao": dados_importacao}, ensure_ascii=False),
        encoding="utf-8",
    )
    temporario.replace(checkpoint)


def main() -> None:
    parser = argparse.ArgumentParser(description="Propõe diferenças de reimportação sem gravar no banco nem sobrescrever imagens")
    parser.add_argument("--min-cobertura", type=float, default=0, help="Exige cobertura acima deste percentual para produzir a proposta")
    parser.add_argument("--stage", action="store_true", help="Persiste propostas pendentes em staging local, sem aplicar ao acervo")
    args = parser.parse_args()
    pdfs = sorted(path for path in SAMPLES.rglob("*.pdf") if _is_question_pdf(path))
    if not pdfs:
        raise RuntimeError("Nenhum PDF encontrado; o banco foi preservado.")
    resultados = []
    dados_importacao = []
    preview_root = REPORTS_DIR / f"reimportacao-preview-{datetime.now():%Y%m%d-%H%M%S-%f}"
    checkpoint_path = preview_root / "checkpoint.json"
    processados = {resultado["arquivo"] for resultado in resultados}
    diagnosticos_gabarito = {}

    # Primeiro extrai tudo; uma falha aqui não destrói o banco atual.
    for caminho in pdfs:
        if str(caminho.relative_to(ROOT)) in processados:
            continue
        texto = extrair_texto(str(caminho))
        questoes = parsear_questoes(texto, str(caminho))
        # Recortes de teste vão para uma pasta temporária local, nunca para os
        # arquivos que o banco atual já pode referenciar.
        imagens = anexar_imagens_referenciadas(caminho, questoes, preview_root)
        banca_confirmada = BANCAS_CONFIRMADAS.get(str(caminho.relative_to(SAMPLES)).replace("\\", "/"))
        if banca_confirmada:
            for questao in questoes:
                questao["banca"] = banca_confirmada
        registro_gabarito = _registro_do_sample(caminho)
        gabaritos = _gabarito_do_sample(caminho, questoes)
        perfil_caderno = classificar_caderno(texto)
        perfil_gabarito = None
        diagnostico_gabarito = None
        associacao = {"pontos": 0, "decisao": "revisao_manual", "evidencias": []}
        if registro_gabarito:
            arquivo_gabarito = str(SAMPLES / registro_gabarito["gabarito"])
            if arquivo_gabarito not in diagnosticos_gabarito:
                diagnosticos_gabarito[arquivo_gabarito] = diagnosticar_gabarito_pdf(arquivo_gabarito)
            diagnostico_completo = diagnosticos_gabarito[arquivo_gabarito]
            diagnostico_gabarito = {
                "arquivo": diagnostico_completo["arquivo"],
                "perfis": diagnostico_completo["perfis"],
                "codigos": diagnostico_completo["codigos"],
                "paginas": [p for p in diagnostico_completo["paginas"] if p["codigos"] or p["perfil"] != "pares_textuais"],
            }
            perfis = diagnostico_gabarito["perfis"]
            perfil_nome = diagnostico_completo["padrao_predominante"]
            perfil_gabarito = PerfilDocumento(
                "gabarito", perfil_nome,
                tuple(sorted({e for pagina in diagnostico_gabarito["paginas"] for e in pagina["evidencias"]})),
                tuple(diagnostico_gabarito["codigos"]),
                familia=diagnostico_completo["familia"],
                metadados={k: tuple(v) for k, v in diagnostico_completo["metadados"].items()},
                intervalo_questoes=tuple(diagnostico_completo["intervalo_questoes"]),
                quantidade_respostas=diagnostico_completo["quantidade_respostas"],
            )
            associacao = pontuar_associacao(
                perfil_caderno, perfil_gabarito,
                codigo=registro_gabarito.get("codigo") or registro_gabarito.get("prova") or "",
                cargo=registro_gabarito.get("cargo") or "",
                evidencia_catalogo=registro_gabarito.get("evidencia", "") if registro_gabarito.get("confirmado") else "",
            )
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
                "imagens_preservadas": imagens,
                "alta": sum(q["confianca"] == "alta" for q in questoes),
                "media": sum(q["confianca"] == "media" for q in questoes),
                "baixa": sum(q["confianca"] == "baixa" for q in questoes),
                "gabaritos": gabaritos_aplicados,
                "validacao": validacao,
                "revisao_manual": validacao["revisao_manual"],
                "banca": next((q.get("banca") for q in questoes if q.get("banca")), ""),
                "pcimarkpci": "pcimarkpci" in texto.lower(),
                "perfil_caderno": perfil_caderno.como_dict(),
                "perfil_gabarito": perfil_gabarito.como_dict() if perfil_gabarito else None,
                "diagnostico_gabarito": diagnostico_gabarito,
                "associacao_padroes": associacao,
            }
        )
        dados_importacao.append(dados)
        resultados[-1]["sha256_caderno"] = hashlib.sha256(caminho.read_bytes()).hexdigest()
        resultados[-1]["associacao"] = registro_gabarito
        resultados[-1]["itens"] = [{"numero": q["numero"], "gabarito": q.get("gabarito")} for q in questoes]
        _salvar_checkpoint(resultados, dados_importacao, checkpoint_path)
        print(f"Extraído: {caminho.name}: {len(questoes)} questões, {gabaritos_aplicados} vínculos", file=sys.stderr, flush=True)

    if not any(dados_importacao):
        raise RuntimeError("Nenhuma questão extraída; o banco foi preservado.")
    cobertura_prevista = 100 * sum(r["gabaritos"] for r in resultados) / sum(len(d) for d in dados_importacao)
    if cobertura_prevista <= args.min_cobertura:
        raise RuntimeError(f"Cobertura {cobertura_prevista:.2f}% não supera {args.min_cobertura:.2f}%; nenhum dado foi alterado.")
    comparacao = _comparar_com_acervo(DATABASE, resultados, dados_importacao)
    staging = None
    if args.stage:
        propostas = []
        por_arquivo = comparacao.get("por_arquivo", [])
        for arquivo_resultado in por_arquivo:
            origem = next((item for item in resultados if item["arquivo"] == arquivo_resultado["arquivo"]), {})
            for item in arquivo_resultado.get("itens", []):
                propostas.append({
                    "arquivo": arquivo_resultado["arquivo"],
                    "sha256_fonte": origem.get("sha256_caderno"),
                    "fonte_path": str(ROOT / arquivo_resultado["arquivo"]),
                    "prova_id": next(iter(arquivo_resultado.get("provas_cadastradas_correspondentes", [])), None),
                    "questao_id": item.get("questao_id"),
                    "ordem_candidata": item.get("ordem_candidata"),
                    "status": item.get("status"),
                    "conteudo_atual": item.get("conteudo_atual"),
                    "proposta": item.get("proposta"),
                    "diferencas": item.get("diferencas", {}),
                    "identidade_certificada": False,
                    "revisao_humana": "pendente",
                })
        staging_path = REPORTS_DIR / "reimportacao_staging_v2.sqlite3"
        staging = stage_proposals(staging_path, propostas)
    resumo = {
        "modo": "simulacao_somente_leitura",
        "arquivos": len(pdfs),
        "questoes_propostas": sum(len(data) for data in dados_importacao),
        "cobertura_extraida_percentual_nao_equivale_a_precisao": cobertura_prevista,
        "comparacao": comparacao,
        "staging": staging,
        "por_arquivo": resultados,
        "decisao": "Nenhuma alteração aplicada. Diferencas, novas questões, ordem candidata e impacto em tentativas exigem revisão antes de qualquer aplicação.",
    }
    out = REPORTS_DIR / f"proposta_reimportacao_samples_{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    checkpoint_path.unlink(missing_ok=True)
    print(f"Proposta somente leitura gravada em {out.relative_to(ROOT)}")
    print(f"{resumo['arquivos']} arquivos, {resumo['questoes_propostas']} questões; banco não foi alterado.")


if __name__ == "__main__":
    main()
