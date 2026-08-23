import logging
import re
import unicodedata


logger = logging.getLogger(__name__)

_INICIO_QUESTAO = re.compile(
    # Alguns PDFs exportam "QUESTÃO" como "QUEST�O" (caractere de
    # substituição). O marcador precisa continuar reconhecível mesmo assim.
    r"(?im)^((?:quest(?:ão|ao|�o)[ \t]*)?\d{1,3}(?:[ \t]*[.\-):][ \t]*|[ \t]+|[ \t]*\n))"
)
_INICIO_ALTERNATIVA = re.compile(r"(?im)^[ \t]*\(?([A-E])\)?\s*[.\-):]\s+")
_INICIO_NUMERADO = re.compile(r"(?im)^[ \t]*(\d{1,3})(?:[.\-):][ \t]*|[ \t]+).+$")
_INICIO_QUESTAO_NOMEADA = re.compile(
    r"(?im)^((?:quest(?:ão|ao|�o)[ \t]+\d{1,3})(?:[ \t]*[.\-):]|[ \t]*\n))"
)
_DISCIPLINAS = (
    ("Língua Portuguesa", r"l(?:í|i|�)ngua portuguesa"),
    ("Língua Portuguesa", r"portugu(?:ê|e|�)s(?:a)?"),
    ("Matemática", r"matem(?:á|a|�)tica"),
    ("Língua Inglesa", r"l(?:í|i|�)ngua inglesa"),
    ("Conhecimentos Básicos", r"conhecimentos b(?:á|a|�)sicos(?:\s+(?:gerais|espec(?:í|i|�)ficos))?"),
    ("Conhecimentos Gerais", r"conhecimentos gerais"),
    ("Conhecimentos Específicos", r"conhecimentos espec(?:í|i|�)ficos(?:\s+(?:i|ii|iii|iv|v))?"),
    ("Noções de Informática", r"no(?:ç|c|�)(?:ões|oes|�es) de inform(?:á|a|�)tica"),
    ("Informática", r"inform(?:á|a|�)tica"),
    ("Direito Constitucional", r"direito constitucional"),
    ("Direito Administrativo", r"direito administrativo"),
    ("Raciocínio Lógico", r"racioc(?:í|i|�)nio l(?:ó|o|�)gico"),
    ("Raciocínio Lógico e Matemática", r"racioc(?:í|i|�)nio l(?:ó|o|�)gico e matem(?:á|a|�)tica"),
    ("Contabilidade", r"contabilidade"),
    ("Administração", r"administra(?:ç|c|�)(?:ão|ao|�o)"),
    ("Auditoria", r"auditoria"),
    ("Legislação", r"legisla(?:ç|c|�)(?:ão|ao|�o)"),
    ("Atualidades", r"atualidades"),
)
_SECAO_CONTAGEM = re.compile(r"\s*\|\s*\d+\s*quest(?:ão|ões|ao|oes|�o|�es).*$", re.IGNORECASE)
_MARCADOR_QUESTAO = re.compile(r"(?i)^(?:quest(?:ão|ao|�o)[ \t]*)?(\d{1,3})(?:[ \t]*[.\-):][ \t]*|[ \t]+|[ \t]*\n)")
_MARCADOR_INLINE = re.compile(
    r"(?<!^)(?<!\n)[ \t]+(?=(?:(?i:quest(?:ão|ao|�o))[ \t]*)?\d{1,3}[)\-.:][ \t]+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ�])",
)


def _normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto or "")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto.strip()


def _juntar_linhas(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def _quebrar_marcadores_inline(texto: str) -> str:
    return _MARCADOR_INLINE.sub("\n", texto)


def _disciplina_da_linha(linha: str) -> str:
    linha = _SECAO_CONTAGEM.sub("", linha.strip())
    for nome, padrao in _DISCIPLINAS:
        if re.fullmatch(padrao, linha, re.IGNORECASE):
            return nome
    return ""


def _tem_marcador_questao_perto(linhas: list[str], indice: int, limite=12) -> bool:
    for linha in linhas[indice + 1:indice + 1 + limite]:
        linha = linha.strip()
        if _parece_grade_respostas(linha):
            continue
        # A distribuição "1 a 10" e as instruções numeradas "02 - ..."
        # aparecem no front matter de cadernos FGV e não são questões.
        if re.match(r"(?i)^\d{1,3}\s+a\s+\d{1,3}\b", linha) or re.match(r"^\d{1,2}\s*[-–:]\s+", linha):
            continue
        if _MARCADOR_QUESTAO.match(linha):
            return True
    return False


def _remover_front_matter(texto: str) -> str:
    linhas = texto.splitlines(True)
    posicao = 0
    for indice, linha_com_quebra in enumerate(linhas):
        linha = linha_com_quebra.strip()
        disciplina = _disciplina_da_linha(linha)
        # Em alguns cadernos FGV o cargo aparece isolado na primeira linha
        # (por exemplo, "ADMINISTRAÇÃO") e não é uma seção de questões.
        # Não use esse título para cortar o front matter antes das instruções.
        titulo_inicial = indice < 3 and disciplina == "Administração"
        if disciplina and not titulo_inicial and (_SECAO_CONTAGEM.search(linha) or _tem_marcador_questao_perto(linhas, indice)):
            return texto[posicao:].strip()
        posicao += len(linha_com_quebra)
    return texto


def _parece_grade_respostas(linha: str) -> bool:
    numeros = re.findall(r"\b\d{1,3}\b", linha)
    palavras = re.findall(r"[A-Za-zÀ-ÿ�]{3,}", linha)
    return len(numeros) >= 5 and not palavras


def _quantidade_de_questoes(texto: str) -> int | None:
    """Lê a quantidade declarada no cabeçalho, sem inventar itens ausentes."""
    padroes = (
        r"\b(?:cont[eé]m|contendo|total de|s[aã]o)\s+(\d{1,3})\s+(?:quest(?:[õo]es|oes)|itens)\b",
        r"\b(?:cont[eé]m|contendo|total de|s[aã]o)\s+(\d{1,3})\s*\([^)]{2,30}\)\s+(?:quest(?:[õo]es|oes)|itens)\b",
        r"\b(\d{1,3})\s+quest(?:[õo]es|oes)\s+objetivas?\b",
    )
    valores = [int(valor) for padrao in padroes for valor in re.findall(padrao, texto, re.IGNORECASE)]
    return max(valores) if valores else None


def quantidade_declarada(texto: str) -> int | None:
    """Retorna a quantidade informada no cabeçalho, quando existir."""
    return _quantidade_de_questoes(_normalizar_texto(texto))


def _inferir_banca(texto: str, origem: str = "") -> str:
    """Identifica a banca usando texto do documento e, como fallback, sua origem."""
    contexto = f"{texto}\n{origem}".upper()
    bancas = (
        ("FGV", ("FGV", "FUNDAÇÃO GETULIO VARGAS", "FUNDACAO GETULIO VARGAS")),
        ("CESPE/CEBRASPE", ("CESPE", "CEBRASPE")),
        ("IBFC", ("IBFC",)),
        ("FCC", ("FUNDAÇÃO CARLOS CHAGAS", "FUNDACAO CARLOS CHAGAS")),
        ("VUNESP", ("VUNESP",)),
        ("FUNDATEC", ("FUNDATEC",)),
        ("Objetiva", ("OBJETIVAS.COM.BR", "OBJETIVA CONCURSOS")),
        ("Instituto AOCP", ("INSTITUTO AOCP", "AOCP")),
        ("CONSULPLAN", ("CONSULPLAN",)),
        ("QUADRIX", ("QUADRIX",)),
        ("IBADE", ("IBADE",)),
        ("FURB", ("FURB",)),
        ("FEPESE", ("FEPESE",)),
        ("Legalle", ("LEGALLE",)),
        ("Avança SP", ("AVANÇA SP", "AVANCA SP")),
        ("Nosso Rumo", ("NOSSO RUMO",)),
    )
    return next((nome for nome, marcas in bancas if any(marca in contexto for marca in marcas)), "")


def extrair_metadados_prova(texto: str, origem: str = "") -> dict:
    """Obtém metadados globais e a disciplina de cada questão sem depender da banca."""
    texto = _normalizar_texto(texto)
    upper = texto.upper()
    banca = _inferir_banca(texto, origem)
    linhas_contexto = [linha for linha in texto.splitlines() if re.search(r"(?i)aplica|edital|concurso|publica|realiza|prova de", linha)]
    anos = [int(ano) for linha in linhas_contexto for ano in re.findall(r"\b(20\d{2})\b", linha)]
    ano = next((valor for valor in anos if 2000 <= valor <= 2035), None)

    disciplinas = {}
    disciplina_atual = ""
    numero_pendente = None
    for linha in texto.splitlines():
        linha = linha.strip()
        disciplina = _disciplina_da_linha(linha)
        if disciplina:
            disciplina_atual = disciplina
            numero_pendente = None
            continue
        marcador = re.fullmatch(r"(\d{1,3})[.\-):]?", linha)
        if marcador:
            numero_pendente = int(marcador.group(1))
            continue
        marcador_inicio = _MARCADOR_QUESTAO.match(linha)
        if marcador_inicio and disciplina_atual and not _parece_grade_respostas(linha):
            disciplinas[int(marcador_inicio.group(1))] = disciplina_atual
            continue
        if numero_pendente is not None and disciplina_atual:
            disciplinas[numero_pendente] = disciplina_atual
            numero_pendente = None

    # Alguns cadernos não repetem o nome da disciplina antes de cada bloco;
    # deixam apenas "Conhecimentos Básicos" e a indicação "questões de 1 a
    # 15". Nesse padrão de prova superior, a divisão oficial é fixa.
    if re.search(r"texto\s+para\s+as\s+quest.*?1\s+a\s+15", texto, re.IGNORECASE):
        for numero in range(1, 16):
            disciplinas.setdefault(numero, "Língua Portuguesa")
        for numero in range(16, 26):
            disciplinas.setdefault(numero, "Raciocínio Lógico e Matemática")
        for numero in range(26, 51):
            disciplinas.setdefault(numero, "Conhecimentos Específicos")
    return {"banca": banca, "ano": ano, "disciplinas": disciplinas}


def _separar_itens_cespe(texto: str) -> list[str]:
    """Separa itens CESPE, ignorando números de linha dos textos-base."""
    candidatos = [
        candidato for candidato in _INICIO_NUMERADO.finditer(texto)
        if not _parece_grade_respostas(candidato.group(0))
    ]
    if not candidatos:
        return []

    blocos_reais = []
    for indice, candidato in enumerate(candidatos):
        fim = candidatos[indice + 1].start() if indice + 1 < len(candidatos) else len(texto)
        bloco = texto[candidato.start():fim].strip()
        # Itens da prova têm uma justificativa; números de linha dos textos-base não.
        if "JUSTIFICATIVA" in bloco.upper():
            blocos_reais.append(bloco)

    # Algumas fontes não trazem justificativa. Nesse caso, aproveita a
    # sequência numerada principal como fallback. Em PDFs de duas colunas a
    # ordem de leitura pode intercalar números de texto-base (por exemplo,
    # 1, 2, 3, 4, 10, 5, 25, 11...). Consolidar a primeira ocorrência de cada
    # número a partir do primeiro item 1 recupera a sequência sem duplicar
    # blocos discursivos posteriores.
    if len(blocos_reais) < 2:
        inicio = next((indice for indice, candidato in enumerate(candidatos) if int(candidato.group(1)) == 1), None)
        sequencia_por_numero = {}
        if inicio is not None:
            for candidato in candidatos[inicio:]:
                numero = int(candidato.group(1))
                if numero >= 1:
                    sequencia_por_numero.setdefault(numero, candidato)

        maior_prefixo = 0
        while maior_prefixo + 1 in sequencia_por_numero:
            maior_prefixo += 1
        selecionados = {
            numero: sequencia_por_numero[numero]
            for numero in range(1, maior_prefixo + 1)
        }
        # O fim do bloco é determinado pela ordem física do PDF, enquanto a
        # saída volta à ordem numérica oficial.
        por_posicao = sorted(selecionados.items(), key=lambda item: item[1].start())
        blocos_por_numero = {}
        for indice, (numero, candidato) in enumerate(por_posicao):
            fim = por_posicao[indice + 1][1].start() if indice + 1 < len(por_posicao) else len(texto)
            blocos_por_numero[numero] = texto[candidato.start():fim].strip()
        blocos_reais = [blocos_por_numero[numero] for numero in range(1, maior_prefixo + 1)]
    return blocos_reais


def parsear_questoes(texto: str, origem: str = "") -> list[dict]:
    texto = _normalizar_texto(texto)
    if not texto:
        return []
    texto = _quebrar_marcadores_inline(texto)
    metadados = extrair_metadados_prova(texto, origem)
    texto_questoes = _remover_front_matter(texto)
    quantidade_declarada = _quantidade_de_questoes(texto)

    # Quando o PDF traz marcadores explícitos ("QUESTÃO 1"), eles têm
    # prioridade. Números soltos também aparecem em textos-base e não podem
    # ativar o modo CESPE por engano.
    tem_marcadores_nomeados = bool(_INICIO_QUESTAO_NOMEADA.search(texto_questoes))
    tem_alternativas = len(_INICIO_ALTERNATIVA.findall(texto_questoes)) >= 2
    blocos_sem_pontuacao = [] if tem_marcadores_nomeados or tem_alternativas else _separar_itens_cespe(texto_questoes)
    if blocos_sem_pontuacao:
        blocos = blocos_sem_pontuacao
    elif tem_marcadores_nomeados:
        blocos = _INICIO_QUESTAO_NOMEADA.split(texto_questoes)
    else:
        blocos = _INICIO_QUESTAO.split(texto_questoes)
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
        marcador = _MARCADOR_QUESTAO.match(bloco)
        numero_real = int(marcador.group(1)) if marcador else numero_questao
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

        # Em cadernos de múltipla escolha, números de parágrafos/textos-base
        # também parecem marcadores de questão. Esses blocos não possuem
        # alternativas e devem ser descartados; manteríamos texto-base como
        # falsas questões, especialmente no layout de duas colunas da FGV.
        if tem_alternativas and not alternativas:
            continue
        if len(enunciado) < 10:
            continue
        if alternativas:
            tipo = "multipla_escolha"
            confianca = "alta" if len(alternativas) >= 4 else "media"
        else:
            tipo = "certo_errado"
            confianca = "alta" if len(enunciado) >= 80 else ("media" if len(enunciado) >= 30 else "baixa")
        questoes.append({
            # Preserva o número original para que gabaritos parciais possam
            # ser associados sem deslocar respostas após uma questão perdida.
            "numero": numero_real,
            "enunciado": enunciado,
            "tipo": tipo,
            "alternativas": alternativas or None,
            "gabarito": None,
            "confianca": confianca,
            "disciplina": metadados["disciplinas"].get(numero_real, ""),
            "topico": "",
            "banca": metadados["banca"],
            "ano": metadados["ano"],
        })

    # Ruído de rodapé, textos-base e assinatura costuma formar uma falsa
    # questão no final do documento. Se o cabeçalho informa a quantidade e a
    # extração excedeu esse limite, removemos somente candidatos de baixa
    # qualidade, preservando a ordem dos itens reais.
    if quantidade_declarada and len(questoes) > quantidade_declarada:
        questoes = questoes[:quantidade_declarada]

    logger.info("Parser identificou %s questões", len(questoes))
    return questoes
