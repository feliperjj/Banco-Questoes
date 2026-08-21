import logging
import re
import unicodedata


logger = logging.getLogger(__name__)

_INICIO_QUESTAO = re.compile(
    # Alguns PDFs exportam "QUESTÃO" como "QUEST�O" (caractere de
    # substituição). O marcador precisa continuar reconhecível mesmo assim.
    r"(?im)^((?:quest(?:ão|ao|�o)\s*)?\d{1,3}(?:\s*[.\-):]\s+|\s*\n))"
)
_INICIO_ALTERNATIVA = re.compile(r"(?im)^[ \t]*\(?([A-E])\)?\s*[.\-):]\s+")
_INICIO_NUMERADO = re.compile(r"(?im)^[ \t]*(\d{1,3})\s+.+$")
_INICIO_QUESTAO_NOMEADA = re.compile(
    r"(?im)^((?:quest(?:ão|ao|�o)\s+\d{1,3})(?:\s*[.\-):]|\s*\n))"
)
_SECOES_DISCIPLINA = re.compile(
    r"(?i)^(língua portuguesa|matemática|língua inglesa|conhecimentos gerais|"
    r"conhecimentos específicos|informática|direito(?: constitucional| administrativo)?|"
    r"raciocínio lógico|contabilidade|administração|auditoria|legislação|atualidades)$"
)


def _normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto or "")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto.strip()


def _juntar_linhas(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def extrair_metadados_prova(texto: str) -> dict:
    """Obtém metadados globais e a disciplina de cada questão sem depender da banca."""
    texto = _normalizar_texto(texto)
    upper = texto.upper()
    bancas = (
        ("FGV", ("FGV", "FUNDAÇÃO GETULIO VARGAS")),
        ("CESPE/CEBRASPE", ("CESPE", "CEBRASPE")),
        ("FCC", ("FUNDAÇÃO CARLOS CHAGAS", "FCC")),
        ("VUNESP", ("VUNESP",)),
        ("IBFC", ("IBFC",)),
        ("CONSULPLAN", ("CONSULPLAN",)),
    )
    banca = next((nome for nome, marcas in bancas if any(marca in upper for marca in marcas)), "")
    linhas_contexto = [linha for linha in texto.splitlines() if re.search(r"(?i)aplica|edital|concurso|publica|realiza|prova de", linha)]
    anos = [int(ano) for linha in linhas_contexto for ano in re.findall(r"\b(20\d{2})\b", linha)]
    ano = next((valor for valor in anos if 2000 <= valor <= 2035), None)

    disciplinas = {}
    disciplina_atual = ""
    numero_pendente = None
    for linha in texto.splitlines():
        linha = linha.strip()
        marcador = re.fullmatch(r"(\d{1,3})", linha)
        if marcador:
            numero_pendente = int(marcador.group(1))
            continue
        secao = _SECOES_DISCIPLINA.match(linha)
        if secao:
            disciplina_atual = secao.group(1)
            continue
        if numero_pendente is not None and disciplina_atual:
            disciplinas[numero_pendente] = disciplina_atual
            numero_pendente = None
    return {"banca": banca, "ano": ano, "disciplinas": disciplinas}


def _separar_itens_cespe(texto: str) -> list[str]:
    """Separa itens CESPE, ignorando números de linha dos textos-base."""
    candidatos = list(_INICIO_NUMERADO.finditer(texto))
    if not candidatos:
        return []

    blocos_reais = []
    for indice, candidato in enumerate(candidatos):
        fim = candidatos[indice + 1].start() if indice + 1 < len(candidatos) else len(texto)
        bloco = texto[candidato.start():fim].strip()
        # Itens da prova têm uma justificativa; números de linha dos textos-base não.
        if "JUSTIFICATIVA" in bloco.upper():
            blocos_reais.append(bloco)

    # Algumas fontes não trazem justificativa. Nesse caso, aproveita uma sequência
    # crescente de números de item como fallback, descartando números de linha.
    if len(blocos_reais) < 2:
        sequencia = []
        esperado = 1
        for candidato in candidatos:
            numero = int(candidato.group(1))
            if numero == esperado:
                sequencia.append(candidato)
                esperado += 1
        blocos_reais = []
        for indice, candidato in enumerate(sequencia):
            fim = sequencia[indice + 1].start() if indice + 1 < len(sequencia) else len(texto)
            blocos_reais.append(texto[candidato.start():fim].strip())
    return blocos_reais


def parsear_questoes(texto: str) -> list[dict]:
    texto = _normalizar_texto(texto)
    if not texto:
        return []
    metadados = extrair_metadados_prova(texto)

    # Quando o PDF traz marcadores explícitos ("QUESTÃO 1"), eles têm
    # prioridade. Números soltos também aparecem em textos-base e não podem
    # ativar o modo CESPE por engano.
    tem_marcadores_nomeados = bool(_INICIO_QUESTAO_NOMEADA.search(texto))
    blocos_sem_pontuacao = [] if tem_marcadores_nomeados else _separar_itens_cespe(texto)
    if blocos_sem_pontuacao:
        blocos = blocos_sem_pontuacao
    elif tem_marcadores_nomeados:
        blocos = _INICIO_QUESTAO_NOMEADA.split(texto)
    else:
        blocos = _INICIO_QUESTAO.split(texto)
    # split() devolve o texto antes do primeiro marcador e, depois, pares marcador/conteúdo.
    candidatos = []
    if blocos_sem_pontuacao:
        candidatos = blocos_sem_pontuacao
    else:
        for indice in range(1, len(blocos), 2):
            if indice + 1 < len(blocos):
                candidatos.append(blocos[indice] + blocos[indice + 1])

    questoes = []
    for numero_questao, bloco in enumerate(candidatos, 1):
        bloco = bloco.strip()
        marcador = re.match(r"(?i)^(?:quest(?:ão|ao|�o)\s*)?\d{1,3}(?:\s*[.\-):]\s+|\s*\n)", bloco)
        if not marcador:
            marcador = re.match(r"^\s*\d{1,3}\s+", bloco)
        if marcador:
            bloco = bloco[marcador.end():].strip()
        bloco = re.split(r"\s+JUSTIFICATIVA\s*[-–:]?", bloco, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        partes = _INICIO_ALTERNATIVA.split(bloco)
        enunciado = _juntar_linhas(partes[0])
        alternativas = []
        for indice in range(1, len(partes), 2):
            if indice + 1 < len(partes):
                texto_alternativa = _juntar_linhas(partes[indice + 1])
                if texto_alternativa:
                    alternativas.append({"letra": partes[indice].upper(), "texto": texto_alternativa})

        if len(enunciado) < 10:
            continue
        if alternativas:
            tipo = "multipla_escolha"
            confianca = "alta" if len(alternativas) >= 4 else "media"
        else:
            tipo = "certo_errado"
            confianca = "media" if len(enunciado) >= 30 else "baixa"
        questoes.append({
            "enunciado": enunciado,
            "tipo": tipo,
            "alternativas": alternativas or None,
            "gabarito": None,
            "confianca": confianca,
            "disciplina": metadados["disciplinas"].get(numero_questao, ""),
            "banca": metadados["banca"],
            "ano": metadados["ano"],
        })

    logger.info("Parser identificou %s questões", len(questoes))
    return questoes
