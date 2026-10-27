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


def numero_oficial_explicitamente_extraido(questao: dict) -> tuple[int | None, str | None]:
    """Retorna apenas número explícito; ordem visual e ID nunca são substitutos."""
    if questao.get("numero_ambiguo") or questao.get("numeracao_ambigua"):
        return None, "numeracao_ambigua"
    value = questao.get("numero")
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, "numeracao_ausente"
    if isinstance(value, bool):
        return None, "numeracao_invalida"
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None, "numeracao_invalida"
    if number <= 0 or (isinstance(value, float) and value != number):
        return None, "numeracao_invalida"
    if isinstance(value, str) and str(number) != value.strip():
        return None, "numeracao_invalida"
    return number, None


def _canonical_scope(value) -> tuple:
    if isinstance(value, dict):
        return tuple(sorted((str(key), str(item)) for key, item in value.items() if item not in (None, "")))
    if isinstance(value, tuple):
        return value
    if value in (None, ""):
        return ()
    return (("escopo", str(value)),)


def _escopo_questao(questao: dict) -> tuple:
    declared = questao.get("escopo")
    if declared not in (None, ""):
        return _canonical_scope(declared)
    return tuple((key, str(questao[key])) for key in ("prova", "cargo", "codigo", "versao", "ano")
                 if questao.get(key) not in (None, ""))


def associar_gabaritos(questoes: list[dict], gabaritos: dict[int, str], *, confianca: str = "alta") -> dict:
    """Associa por número oficial e escopo explícitos, sem deslocamento posicional."""
    por_numero = defaultdict(list)
    problemas_numeracao = []
    for visual_order, questao in enumerate(questoes, 1):
        numero, motivo = numero_oficial_explicitamente_extraido(questao)
        if motivo:
            problemas_numeracao.append({"motivo": motivo, "ordem_visual": visual_order,
                                        "id": questao.get("id")})
            continue
        por_numero[(_escopo_questao(questao), numero)].append(questao)
    duplicados_por_escopo = sorted(key for key, itens in por_numero.items() if len(itens) > 1)
    answers = {}
    errors = []
    for raw_key, resposta in gabaritos.items():
        if isinstance(raw_key, tuple) and len(raw_key) == 2:
            scope = _canonical_scope(raw_key[0])
            raw_number = raw_key[1]
        else:
            scope = None
            raw_number = raw_key
        try:
            number = int(raw_number)
            if number <= 0 or (isinstance(raw_number, str) and str(number) != raw_number.strip()):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            errors.append({"motivo": "numeracao_invalida", "valor": repr(raw_number)})
            continue
        answers[(scope, number)] = resposta
    ambiguous = {number for scope, number in answers if scope is None
                 and len([key for key in por_numero if key[1] == number]) > 1}
    extras = sorted(number for (scope, number) in answers
                    if number not in {key[1] for key in por_numero} and number not in ambiguous)
    faltantes = sorted(number for (scope, number), items in por_numero.items()
                       if (scope, number) not in answers and (None, number) not in answers)
    vinculados = 0
    conflitos = list(getattr(gabaritos, 'conflitos', ()))
    incompativeis = []
    escopos_divergentes = []
    for (answer_scope, numero), resposta in answers.items():
        if answer_scope is None and numero in ambiguous:
            escopos_divergentes.append(numero)
            continue
        matching_keys = [key for key in por_numero if key[1] == numero
                         and (answer_scope is None or key[0] == answer_scope)]
        itens = por_numero.get(matching_keys[0], []) if len(matching_keys) == 1 else []
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
            "extras": extras, "duplicados": sorted(number for scope, number in duplicados_por_escopo),
            "duplicados_por_escopo": duplicados_por_escopo, "conflitos": sorted(conflitos),
            "incompativeis": sorted(incompativeis),
            "numeracao": problemas_numeracao, "erros_gabarito": errors,
            "escopo_divergente": sorted(set(escopos_divergentes)),
            "revisao_manual": bool(faltantes or extras or duplicados_por_escopo or conflitos
                                    or problemas_numeracao or errors or escopos_divergentes)}


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
    if associacao['numeracao']:
        motivos.extend(sorted({item["motivo"] for item in associacao['numeracao']}))
    if associacao['escopo_divergente']:
        motivos.append('escopo_divergente')
    if associacao['erros_gabarito']:
        motivos.append('numeracao_invalida')
    return {
        "valido": not motivos,
        "questoes": len(questoes),
        "gabaritos": len(gabaritos),
        "faltantes": faltantes,
        "extras": extras,
        "duplicados": duplicados,
        "incompativeis": associacao['incompativeis'],
        "conflitos": associacao['conflitos'],
        "numeracao": associacao['numeracao'],
        "escopo_divergente": associacao['escopo_divergente'],
        "erros_gabarito": associacao['erros_gabarito'],
        "associados": associacao["vinculados"],
        "motivos": motivos,
        "revisao_manual": bool(motivos),
    }
