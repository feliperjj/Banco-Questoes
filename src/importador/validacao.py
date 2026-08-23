"""Validações determinísticas do vínculo entre caderno e gabarito."""

from __future__ import annotations

from collections import defaultdict


GABARITOS_VALIDOS = frozenset({"A", "B", "C", "D", "E", "CERTO", "ERRADO", "ANULADA", "X"})


def normalizar_gabarito(valor: str | None, tipo: str | None = None) -> str | None:
    """Converte respostas para o vocabulário único usado pelo domínio."""
    if valor is None:
        return None
    token = str(valor).strip().upper()
    if token == "X":
        return "Anulada"
    if token in {"ANULADA", "ANULADO"}:
        return "Anulada"
    if token in {"CERTO", "C"} and tipo == "certo_errado":
        return "Certo"
    if token in {"ERRADO", "E"} and tipo == "certo_errado":
        return "Errado"
    if token in {"A", "B", "C", "D", "E"}:
        return token
    return None


def gabarito_valido(valor: str | None) -> bool:
    token = str(valor or "").strip().upper()
    return token in GABARITOS_VALIDOS


def associar_gabaritos(questoes: list[dict], gabaritos: dict[int, str], *, confianca: str = "alta") -> dict:
    """Associa por número oficial; nunca usa a posição visual como chave."""
    por_numero = defaultdict(list)
    for indice, questao in enumerate(questoes, 1):
        try:
            numero = int(questao.get("numero", indice))
        except (TypeError, ValueError):
            continue
        por_numero[numero].append(questao)
    duplicados = sorted(numero for numero, itens in por_numero.items() if len(itens) > 1)
    extras = sorted(set(int(n) for n in gabaritos) - set(por_numero))
    faltantes = sorted(set(por_numero) - set(int(n) for n in gabaritos))
    vinculados = 0
    conflitos = []
    for numero, resposta in gabaritos.items():
        numero = int(numero)
        itens = por_numero.get(numero, [])
        if len(itens) != 1:
            continue
        questao = itens[0]
        normalizada = normalizar_gabarito(resposta, questao.get("tipo"))
        if normalizada is None:
            continue
        anterior = questao.get("gabarito")
        if anterior and questao.get("gabarito_confianca") == "alta" and confianca != "alta":
            continue
        if anterior and normalizar_gabarito(anterior, questao.get("tipo")) != normalizada:
            conflitos.append(numero)
            continue
        questao["gabarito"] = normalizada
        questao["gabarito_confianca"] = confianca
        vinculados += 1
    return {"extraidos": len(gabaritos), "vinculados": vinculados, "faltantes": faltantes,
            "extras": extras, "duplicados": duplicados, "conflitos": sorted(conflitos),
            "revisao_manual": bool(faltantes or extras or duplicados or conflitos)}


def validar_gabarito(
    questoes: list[dict],
    gabaritos: dict[int, str],
    *,
    cargo_encontrado: bool = True,
    quantidade_esperada: int | None = None,
) -> dict:
    """Retorna evidências e pendências sem aplicar respostas ao banco."""
    numeros = [int(q.get("numero", i)) for i, q in enumerate(questoes, 1)]
    numeros_unicos = set(numeros)
    gabarito_numeros = set(gabaritos)
    faltantes = sorted(numeros_unicos - gabarito_numeros)
    extras = sorted(gabarito_numeros - numeros_unicos)
    duplicados = sorted({n for n in numeros if numeros.count(n) > 1})
    motivos = []
    if not cargo_encontrado:
        motivos.append("cargo_nao_encontrado")
    if quantidade_esperada is not None and len(questoes) != quantidade_esperada:
        motivos.append("numeracao_divergente")
    if duplicados:
        motivos.append("numeros_duplicados")
    if faltantes:
        motivos.append("gabaritos_faltantes")
    if extras:
        motivos.append("gabaritos_extras")
    return {
        "valido": not motivos,
        "questoes": len(questoes),
        "gabaritos": len(gabaritos),
        "faltantes": faltantes,
        "extras": extras,
        "duplicados": duplicados,
        "motivos": motivos,
        "revisao_manual": bool(motivos),
    }
