import re


def parsear_gabarito_em_lote(texto: str) -> list[str]:
    # Aceita apenas tokens inteiros; não transforme letras dentro de palavras
    # (“Caderno”, “Exemplo”...) em respostas acidentais.
    return re.findall(r"(?<![A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])(?:CERTO|ERRADO|[A-E])(?![A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])", (texto or "").upper())


def _normalizar_resposta(token: str, tipo_questao: str) -> str:
    token = token.upper()
    if token == "CERTO" or (token == "C" and tipo_questao == "certo_errado"):
        return "Certo"
    if token == "ERRADO" or (token == "E" and tipo_questao == "certo_errado"):
        return "Errado"
    return token


def aplicar_gabarito_as_questoes(questoes: list[dict], tokens: list[str]) -> list[str]:
    if len(tokens) != len(questoes):
        raise ValueError(f"Foram encontradas {len(tokens)} respostas para {len(questoes)} questões.")
    respostas = []
    for questao, token in zip(questoes, tokens):
        resposta = _normalizar_resposta(token, questao.get("tipo", ""))
        questao["gabarito"] = resposta
        respostas.append(resposta)
    return respostas


def aplicar_classificacao_as_questoes(questoes: list[dict], inicio: int, fim: int, disciplina: str, categoria: str = "") -> int:
    if inicio > fim:
        raise ValueError("A questão inicial não pode ser maior que a final.")
    disciplina = (disciplina or "").strip()
    if not disciplina:
        raise ValueError("Informe a disciplina do bloco.")

    fim_real = min(fim, len(questoes))
    quantidade = 0
    for numero in range(inicio, fim_real + 1):
        questao = questoes[numero - 1]
        questao["disciplina"] = disciplina
        questao["topico"] = categoria
        quantidade += 1
    return quantidade
