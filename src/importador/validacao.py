"""Validações determinísticas do vínculo entre caderno e gabarito."""

from __future__ import annotations

from collections import defaultdict
import re


GABARITOS_VALIDOS = frozenset({"A", "B", "C", "D", "E", "CERTO", "ERRADO", "ANULADA", "X"})


def inicio_suspeito(enunciado: str) -> bool:
    """Minúscula após aspas/pontuação é alerta, nunca motivo para cortar texto."""
    texto = (enunciado or "").lstrip(" \n\r\t\"'“”‘’([{—–-…")
    return bool(texto and texto[0].islower())


def problemas_estrutura(questao: dict) -> list[str]:
    problemas = []
    texto = questao.get('enunciado') or ''
    if not texto.strip():
        problemas.append('Enunciado vazio')
    if questao.get('gabarito') and normalizar_gabarito(questao['gabarito'], questao.get('tipo')) is None:
        problemas.append('Gabarito incompatível com o tipo da questão')
    if re.search(r'\b(?:alternativa que|afirmação que)\s*$', texto, re.I):
        problemas.append('Comando aparentemente incompleto')
    alternativas = questao.get('alternativas') or []
    if questao.get('tipo') == 'multipla_escolha':
        letras = sorted(a['letra'] for a in alternativas if a.get('texto', '').strip())
        if len(letras) < 2 or letras != list('ABCDE'[:len(letras)]):
            problemas.append('Alternativas ausentes ou com letras repetidas')
        if questao.get('gabarito') in set('ABCDE') and questao.get('gabarito') not in letras:
            problemas.append('Alternativa do gabarito ausente')
        def marcador_fundido(t):
            for m in re.finditer(r'\s[b-eB-E]\)\s+\S', t):
                prefixo = t[:m.start()]
                if prefixo.count('(') <= prefixo.count(')'):
                    return True
            return False
        if any(marcador_fundido(a.get('texto', '')) for a in alternativas):
            problemas.append('Possíveis alternativas fundidas')
    if any(re.search(r'TIPO\s+\w+\s*[–—-]\s*P[ÁA]GINA\s+\d+', t, re.I)
           for t in [texto] + [a.get('texto', '') for a in alternativas]):
        problemas.append('Rodapé misturado ao conteúdo')
    return problemas


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
    if token in {"A", "B", "C", "D", "E"} and tipo != "certo_errado":
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
    conflitos = list(getattr(gabaritos, 'conflitos', ()))
    incompativeis = []
    for numero, resposta in gabaritos.items():
        numero = int(numero)
        itens = por_numero.get(numero, [])
        if len(itens) != 1:
            continue
        questao = itens[0]
        normalizada = normalizar_gabarito(resposta, questao.get("tipo"))
        alternativas = questao.get('alternativas')
        ausente = (questao.get('tipo') == 'multipla_escolha' and alternativas is not None
                   and normalizada != 'Anulada'
                   and normalizada not in {a.get('letra') for a in alternativas if a.get('texto', '').strip()})
        if normalizada is None or ausente:
            incompativeis.append(numero)
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
    faltantes = sorted(set(faltantes) | set(incompativeis))
    return {"extraidos": len(gabaritos), "vinculados": vinculados, "faltantes": faltantes,
            "extras": extras, "duplicados": duplicados, "conflitos": sorted(conflitos),
            "incompativeis": sorted(incompativeis),
            "revisao_manual": bool(faltantes or extras or duplicados or conflitos)}


def validar_gabarito(
    questoes: list[dict],
    gabaritos: dict[int, str],
    *,
    cargo_encontrado: bool = True,
    quantidade_esperada: int | None = None,
) -> dict:
    """Retorna evidências e pendências sem aplicar respostas ao banco."""
    associacao = associar_gabaritos([dict(q) for q in questoes], gabaritos)
    faltantes = associacao['faltantes']
    extras = associacao['extras']
    duplicados = associacao['duplicados']
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
    if associacao['incompativeis']:
        motivos.append('gabaritos_incompativeis')
    if associacao['conflitos']:
        motivos.append('gabaritos_conflitantes')
    return {
        "valido": not motivos,
        "questoes": len(questoes),
        "gabaritos": len(gabaritos),
        "faltantes": faltantes,
        "extras": extras,
        "duplicados": duplicados,
        "incompativeis": associacao['incompativeis'],
        "conflitos": associacao['conflitos'],
        "motivos": motivos,
        "revisao_manual": bool(motivos),
    }
