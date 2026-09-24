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


class QuestoesExtraidas(list):
    """Lista compatível com consumidores antigos, com partes compartilhadas da prova."""

    def __init__(self, questoes=(), *, instrucoes_prova=""):
        super().__init__(questoes)
        self.instrucoes_prova = instrucoes_prova


def _associar_textos_linguas(texto: str, questoes: list[dict]) -> None:
    """Liga passagens de inglês/espanhol aos itens que as citam no caderno.

    Alguns cadernos CEBRASPE não declaram um intervalo numérico: colocam a
    passagem sob o título da disciplina e, em seguida, dizem para julgar os
    itens seguintes. O próximo título de disciplina encerra esse grupo.
    """
    numeros = {int(q.get("numero", 0)) for q in questoes}
    secoes = (
        ("língua inglesa", r"(?im)^\s*L[ÍI]NGUA\s+INGLESA\s*$", r"(?im)^\s*L[ÍI]NGUA\s+ESPANHOLA\s*$"),
        ("língua espanhola", r"(?im)^\s*L[ÍI]NGUA\s+ESPANHOLA\s*$", r"(?im)^\s*DIREITO\s+P[ÚU]BLICO\s*$"),
    )
    for _, inicio_re, fim_re in secoes:
        inicio = re.search(inicio_re, texto)
        if not inicio:
            continue
        fim = re.search(fim_re, texto[inicio.end():])
        final = inicio.end() + fim.start() if fim else len(texto)
        secao = texto[inicio.start():final]
        comando = re.search(
            r"(?is)(?:judge\s+the\s+following\s+items|"
            r"juzgue\s+los\s+siguientes\s+[íi]tems)\s*[.:]?",
            secao,
        )
        if not comando:
            continue
        itens = secao[comando.end():]
        marcadores = [
            m for m in re.finditer(r"(?im)^\s*0*(\d{1,3})[.)]?\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", itens)
            if int(m.group(1)) in numeros
        ]
        if not marcadores:
            continue
        suporte = secao[:comando.end()].strip()
        if len(suporte) < 120:
            continue
        faixa = {int(m.group(1)) for m in marcadores}
        for questao in questoes:
            if int(questao.get("numero", 0)) in faixa:
                questao["texto_apoio"] = suporte


def _separar_contexto_inicial(texto: str) -> tuple[str, str, str]:
    """Separa instruções reconhecíveis do texto que pode servir de apoio.

    O prefixo só é classificado como instrução quando contém vários itens
    numerados e vocabulário típico de orientação ao candidato. O restante fica
    como texto de apoio para ser associado às questões que o referenciam.
    """
    if not texto:
        return "", "", ""
    linhas = texto.splitlines()
    itens_numerados = [
        i for i, linha in enumerate(linhas)
        if re.match(r"^\s*\d{1,2}\s*[-–—]\s+\S", linha)
    ]
    sinais_instrucao = re.search(
        r"(?i)cart[aã]o[- ]resposta|candidato|fiscal|tempo dispon[ií]vel|"
        r"ser[aá] eliminado|assinalar uma resposta|lista de presen[çc]a",
        texto,
    )
    instrucoes = ""
    apoio = texto.strip()
    disciplina_apoio = ""
    if len(itens_numerados) >= 3 and sinais_instrucao:
        posicoes_secao = [
            i for i, linha in enumerate(linhas)
            if _disciplina_da_linha(linha.strip())
        ]
        # A última linha de disciplina costuma ser o cabeçalho do texto-base
        # após as instruções gerais (ex.: Conhecimentos Básicos → Língua Portuguesa).
        secao = posicoes_secao[-1] if posicoes_secao else None
        if secao is not None and secao > itens_numerados[0]:
            instrucoes = "\n".join(linhas[:secao]).strip()
            apoio = "\n".join(linhas[secao + 1:]).strip()
            disciplina_apoio = _disciplina_da_linha(linhas[secao].strip())
        elif secao is None:
            inicio = itens_numerados[0]
            instrucoes = "\n".join(linhas[inicio:]).strip()
            apoio = "\n".join(linhas[:inicio]).strip()
    return instrucoes, apoio, disciplina_apoio


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
        return QuestoesExtraidas()
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
    contexto_inicial = ""
    if candidatos:
        primeiro_bloco = candidatos[0].strip()
        marcador_inicial = _MARCADOR_QUESTAO.match(primeiro_bloco)
        corpo_inicial = primeiro_bloco[marcador_inicial.end():] if marcador_inicial else primeiro_bloco
        prefixo_enunciado = _juntar_linhas(_partes_alternativas(corpo_inicial)[0]).strip()
        ancora = re.sub(r"\s+", " ", prefixo_enunciado[:90]).strip()
        if len(ancora) >= 30:
            padrao_ancora = r"\s*".join(re.escape(palavra) for palavra in ancora.split())
            ocorrencia = re.search(padrao_ancora, texto_questoes, re.IGNORECASE)
            if ocorrencia:
                contexto_inicial = texto_questoes[:ocorrencia.start()].strip()
                if len(contexto_inicial) < 180 or len(re.findall(r"[.!?](?:\s|$)", contexto_inicial)) < 2:
                    contexto_inicial = ""
    instrucoes_prova, texto_apoio_inicial, disciplina_apoio = _separar_contexto_inicial(contexto_inicial)
    if contextos:
        # A regra de intervalos explícitos também encontra tabelas de
        # distribuição de pontos. Se o suposto contexto contiver instruções
        # ao candidato, separe-as antes de associar qualquer texto às questões.
        contexto_candidato = max(contextos.values(), key=len)
        instrucoes_contexto, apoio_contexto, disciplina_contexto = _separar_contexto_inicial(contexto_candidato)
        if instrucoes_contexto:
            instrucoes_prova = instrucoes_prova or instrucoes_contexto
            texto_apoio_inicial = apoio_contexto
            disciplina_apoio = disciplina_contexto or disciplina_apoio
            contextos = {numero: apoio_contexto for numero in contextos}
    intervalos_apoio = [
        tuple(map(int, valores))
        for valores in re.findall(r"(?<!\d)(\d{1,3})\s+a\s+(\d{1,3})(?!\d)", instrucoes_prova, re.IGNORECASE)
        if 0 < int(valores[0]) <= int(valores[1]) <= 200
    ]
    intervalo_apoio = intervalos_apoio[0] if intervalos_apoio else None
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
        # Os extratores geométricos do CEBRASPE já entregam cada item com
        # delimitadores explícitos. Use-os antes das heurísticas de contexto:
        # em alguns PDFs o texto-base aparece dentro do bloco da questão e,
        # sem esta divisão, acaba duplicado no enunciado e no apoio.
        bloco_conteudo = partes[0]
        apoio_marcado = re.search(
            r"(?is)\bTEXTO\s+DE\s+APOIO\b\s*(.*?)\s*\bITEM\s+PARA\s+JULGAMENTO\b\s*(.*)$",
            bloco_conteudo,
        )
        if apoio_marcado:
            texto_apoio_marcado = _juntar_linhas(apoio_marcado.group(1))
            enunciado = _juntar_linhas(apoio_marcado.group(2))
        else:
            texto_apoio_marcado = ""
            enunciado = _juntar_linhas(bloco_conteudo)
        texto_apoio = texto_apoio_marcado or contextos.get(numero_real, "")
        apoio_inicial_inferido = False
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
        for referencia in re.findall(r'(?i)\btexto\s+([A-Z0-9]+)\b', enunciado):
            anteriores = [apoio for pos, apoio in rotulados.get(referencia.upper(), []) if pos <= posicao_bloco]
            apoio = anteriores[-1] if anteriores else None
            if apoio and apoio not in texto_apoio:
                texto_apoio = apoio
        if not texto_apoio and texto_apoio_inicial:
            dentro_intervalo = bool(
                intervalo_apoio and intervalo_apoio[0] <= numero_real <= intervalo_apoio[1]
            )
            mesma_disciplina = bool(
                disciplina_apoio
                and metadados["disciplinas"].get(numero_real) == disciplina_apoio
            )
            # A mera menção a gráfico/tabela/figura não liga o prefixo do PDF
            # à questão: em cadernos de duas colunas, esse prefixo pode ser um
            # texto de outra disciplina. Sem intervalo explícito, só associe
            # quando a disciplina também coincide.
            associar_apoio = dentro_intervalo if intervalo_apoio else mesma_disciplina
            if associar_apoio:
                texto_apoio = texto_apoio_inicial
        avisos = list(avisos_extracao)
        if apoio_inicial_inferido:
            confianca = "media" if confianca == "alta" else confianca
            avisos.append("Texto de apoio associado por referência do enunciado; confira se pertence a esta questão.")
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
            "texto_apoio": texto_apoio,
            "instrucoes_prova": instrucoes_prova,
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

    _associar_textos_linguas(texto_original, questoes)

    logger.info("Parser identificou %s questões", len(questoes))
    return QuestoesExtraidas(questoes, instrucoes_prova=instrucoes_prova)
