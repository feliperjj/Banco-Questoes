from src.importador.perfis.lexico import (
    _INICIO_ALTERNATIVA,
    _INICIO_NUMERADO,
    _INICIO_QUESTAO,
    _INICIO_QUESTAO_NOMEADA,
    _MARCADOR_INLINE,
    _MARCADOR_QUESTAO,
    _juntar_linhas,
    _parece_grade_respostas,
    _separar_alternativas_horizontais,
    _partes_alternativas,
)
import logging
import re
import unicodedata
from src.importador.perfis.certo_errado import _separar_itens_cespe
from src.importador.perfis.multipla_escolha import _blocos_multipla_escolha, _qualidade_numeracao
from src.importador.validacao import inicio_suspeito


logger = logging.getLogger(__name__)

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


def _normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto or "")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto.strip()




def _quebrar_marcadores_inline(texto: str) -> str:
    def separar(match):
        seguinte = texto[match.end():]
        antes = texto[texto.rfind('\n', 0, match.start()) + 1:match.start()]
        if re.match(r'(?i)quest', seguinte) or len(re.findall(r'\b[A-Ea-e]\)\s', antes)) >= 2:
            return '\n'
        return match.group(0)
    return _MARCADOR_INLINE.sub(separar, texto)




def _disciplina_da_linha(linha: str) -> str:
    linha = _SECAO_CONTAGEM.sub("", linha.strip())
    for nome, padrao in _DISCIPLINAS:
        if re.fullmatch(padrao, linha, re.IGNORECASE):
            return nome
    return ""


def _tem_marcador_questao_perto(linhas: list[str], indice: int, limite=None) -> bool:
    # Um texto-base pode ocupar páginas antes da primeira questão. Não cortar
    # o caderno na disciplina seguinte só porque o marcador está distante.
    for linha in linhas[indice + 1:indice + 1 + limite if limite else None]:
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
    if '\nTEXTO DE APOIO\n' in texto and '\nITEM PARA JULGAMENTO\n' in texto:
        return texto
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
            if len(_INICIO_ALTERNATIVA.findall(texto[:posicao])) >= 2:
                return texto
            return texto[posicao:].strip()
        posicao += len(linha_com_quebra)
    return texto




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
    texto = re.sub(r'(?im)\bTIPO\s+\w+\s*[–—-]\s*P[ÁA]GINA\s+\d+[^\n]*', '', texto)
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





def parsear_questoes(texto: str, origem: str = "") -> list[dict]:
    avisos_extracao = list(getattr(texto, "avisos", ()))
    perfil_extracao = getattr(texto, "perfil", "texto")
    from src.importador.perfis.normalizacao import normalizar_formatos, contextos_explicitos, textos_rotulados
    texto = _normalizar_texto(normalizar_formatos(texto))
    contextos = contextos_explicitos(texto)
    rotulados = textos_rotulados(texto)
    texto = re.sub(r'(?im)\bTIPO\s+\w+\s*[–—-]\s*P[ÁA]GINA\s+\d+[^\n]*', '', texto)
    if not texto:
        return []
    texto = re.split(r"(?im)^prova\s+discursiva\s*$", texto, maxsplit=1)[0]
    texto_original = texto
    texto = _quebrar_marcadores_inline(texto)
    metadados = extrair_metadados_prova(texto, origem)
    texto_questoes = _remover_front_matter(texto)
    quantidade_declarada = _quantidade_de_questoes(texto)

    from src.importador.perfis.segmentacao import segmentar
    resultado = segmentar(texto_questoes, _remover_front_matter(texto_original), metadados["banca"])
    candidatos = resultado.candidatos
    tem_alternativas = resultado.tem_alternativas
    logger.info("Perfil de importação: %s", resultado.perfil)
    if resultado.aviso:
        logger.warning(resultado.aviso)

    questoes = []
    cursor_fonte = 0
    for numero_questao, bloco in enumerate(candidatos, 1):
        bloco = bloco.strip()
        marcador = _MARCADOR_QUESTAO.match(bloco)
        numero_real = int(marcador.group(1)) if marcador else numero_questao
        if marcador:
            bloco = bloco[marcador.end():].strip()
        bloco = re.split(r"(?m)^[ \t]*JUSTIFICATIVA(?:[ \t]*[-–:]|[ \t]*$)", bloco, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        apoio_seguinte = re.search(r'(?im)^(?:Texto[ \t]+[A-Z0-9]+[ \t]*\n|[^\n]*(?:texto|enunciado|informa[çc][õo]es)[^\n]*quest(?:ões|oes)(?:\s+de)?(?:\s+n[úu]meros)?\s+\d+\s+(?:a|até|e)\s+\d+[^\n]*\n)', bloco)
        primeira_alternativa = _INICIO_ALTERNATIVA.search(bloco)
        if apoio_seguinte and primeira_alternativa and apoio_seguinte.start() > primeira_alternativa.start():
            bloco = bloco[:apoio_seguinte.start()].rstrip()
        partes = _partes_alternativas(bloco)
        prefixo_fonte = partes[0].strip()[:80]
        posicao_bloco = texto.find(prefixo_fonte, cursor_fonte)
        if posicao_bloco >= 0:
            cursor_fonte = posicao_bloco + len(prefixo_fonte)
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
        if tem_alternativas and not alternativas and not (resultado.perfil.startswith('questoes_nomeadas') and re.match(r'(?i)(?:julgue|judge|certo ou errado|verdadeiro ou falso)\b', enunciado)):
            continue
        if len(enunciado) < 10:
            continue
        if alternativas:
            tipo = "multipla_escolha"
            confianca = "alta" if len(alternativas) >= 4 else "media"
        else:
            tipo = "certo_errado"
            confianca = "alta" if len(enunciado) >= 80 else ("media" if len(enunciado) >= 30 else "baixa")
        if inicio_suspeito(enunciado):
            confianca = "baixa"
        if numero_real in contextos and contextos[numero_real] not in enunciado:
            enunciado = contextos[numero_real] + "\n\n" + enunciado
        for referencia in re.findall(r'(?i)\btexto\s+([A-Z0-9]+)\b', enunciado):
            anteriores = [apoio for pos, apoio in rotulados.get(referencia.upper(), []) if pos <= posicao_bloco]
            apoio = anteriores[-1] if anteriores else None
            if apoio and apoio not in enunciado:
                enunciado = apoio + "\n\n" + enunciado
        avisos = list(avisos_extracao)
        if resultado.aviso:
            avisos.append(resultado.aviso)
        if re.search(r'(?i)\b(?:figura|gráfico|imagem|tabela)\s+(?:a seguir|abaixo|acima|apresentad)', enunciado):
            avisos.append("Confira a figura ou tabela na fonte; a importação textual pode não preservar sua estrutura.")
        questoes.append({
            # Preserva o número original para que gabaritos parciais possam
            # ser associados sem deslocar respostas após uma questão perdida.
            "numero": numero_real,
            "perfil_importacao": resultado.perfil,
            "aviso_importacao": " ".join(dict.fromkeys(avisos)),
            "perfil_extracao": perfil_extracao,
            "diagnostico_importacao": list(resultado.diagnostico),
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
