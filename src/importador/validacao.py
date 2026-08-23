"""Validações determinísticas do vínculo entre caderno e gabarito."""

from __future__ import annotations


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
        motivos.append("cargo_nao_confirmado")
    if quantidade_esperada is not None and len(questoes) != quantidade_esperada:
        motivos.append("quantidade_questoes_divergente")
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
