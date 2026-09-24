"""Perfis documentais e funil de associação de cadernos a gabaritos."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import unicodedata


_CODIGO_PROVA = re.compile(r"\b\d{3}(?:_[a-z0-9]+)+_\d{2}\b", re.I)
_CODIGO_EXPLICITO = re.compile(
    r"\b(?:IBFC|FEPESE|FGV|FUNDATEC|OBJETIVA|CEBRASPE|CESPE)[_ -]?\d{1,3}\b|\b[A-Z]\d{3,}\b",
    re.I,
)
_ORGAO = re.compile(
    r"(?i)\b(prefeitura(?: municipal)?|c[aâ]mara municipal|minist[eé]rio p[uú]blico|"
    r"defensoria p[uú]blica|conselho regional|tribunal|universidade|secretaria|"
    r"correios|embrapa|transpetro|sescoop|crea|crf|dpe|mpes)\b"
)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).casefold().strip()


@dataclass(frozen=True)
class PerfilDocumento:
    tipo: str
    padrao: str
    evidencias: tuple[str, ...]
    identificadores: tuple[str, ...] = ()
    candidatos: tuple[str, ...] = ()
    aviso: str = ""
    familia: str = "desconhecida"
    metadados: dict[str, tuple[str, ...]] | None = None
    intervalo_questoes: tuple[int, int] = ()
    quantidade_respostas: int = 0

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BlocoGabarito:
    identificador: str
    titulo: str
    texto: str
    padrao: str


def _metadados(texto: str) -> dict[str, tuple[str, ...]]:
    """Identificadores ficam tipados para evitar comparar cargo com banca."""
    encontrados: dict[str, set[str]] = {"codigo": set(), "ano": set(), "versao": set(), "cargo": set(), "orgao": set()}
    encontrados["codigo"].update(m.group(0).upper() for m in _CODIGO_PROVA.finditer(texto))
    encontrados["codigo"].update(_normalizar(m.group(0)).upper().replace(" ", "_").replace("-", "_") for m in _CODIGO_EXPLICITO.finditer(texto))
    encontrados["ano"].update(re.findall(r"\b(?:19|20)\d{2}\b", texto))
    for linha in texto.splitlines():
        versao = re.search(r"(?i)\b(prova|tipo|t)\s*([1-4ivx]+)\b", linha)
        if versao:
            rotulo = versao.group(2).upper()
            numeral = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "X": "10"}.get(rotulo, rotulo)
            encontrados["versao"].add(numeral)
        cargo = re.search(r"(?i)^\s*cargo\s*:\s*(.+?)\s*$", linha)
        if cargo and len(cargo.group(1).strip()) >= 5:
            encontrados["cargo"].add(_normalizar(cargo.group(1)))
        # Muitos cadernos e gabaritos imprimem o cargo como título, sem o rótulo.
        titulo_cargo = linha.strip()
        if (titulo_cargo == titulo_cargo.upper() and 8 <= len(titulo_cargo) <= 140
                and re.search(r"\b(ANALISTA|AGENTE|AUDITOR|ADMINISTRADOR|ASSISTENTE|T[EÉ]CNICO|PROFESSOR|ENGENHEIRO)\b", titulo_cargo, re.I)
                and not re.search(r"\b(PORTUGU[EÊ]S|MATEM[AÁ]TICA|INFORM[AÁ]TICA|CONHECIMENTOS|DIREITO|RACIOC[IÍ]NIO)\b", titulo_cargo, re.I)):
            encontrados["cargo"].add(_normalizar(titulo_cargo))
        orgao = _ORGAO.search(linha)
        if orgao:
            encontrados["orgao"].add(_normalizar(linha)[:160])
    return {tipo: tuple(sorted(valores)) for tipo, valores in encontrados.items() if valores}


def _familia_caderno(padrao: str, tem_alternativas: bool) -> str:
    if "certo_errado" in padrao or "cespe" in padrao or padrao.startswith("cex"):
        return "certo_errado"
    if tem_alternativas or "multipla_escolha" in padrao:
        return "multipla_escolha"
    return "desconhecida"


_STOP_CARGO = {"de", "da", "do", "das", "dos", "em", "e", "para", "nivel", "superior", "cargo", "prova", "tipo"}
_STOP_ORGAO = _STOP_CARGO | {"prefeitura", "municipal", "ministerio", "publico", "conselho", "regional", "secretaria"}


def _tokens_chave(valor: str, *, organizacao: bool = False) -> set[str]:
    stop = _STOP_ORGAO if organizacao else _STOP_CARGO
    return {token for token in re.findall(r"[a-z0-9]+", _normalizar(valor)) if token not in stop and len(token) > 1}


def _sobreposicao_rotulos(esquerda: set[str], direita: set[str], *, organizacao: bool = False) -> set[tuple[str, str]]:
    """Aceita cargo composto truncado no cabeçalho, mas exige tokens específicos."""
    resultados = set()
    for a in esquerda:
        ta = _tokens_chave(a, organizacao=organizacao)
        for b in direita:
            tb = _tokens_chave(b, organizacao=organizacao)
            comuns = ta & tb
            if a == b or (len(comuns) >= (1 if organizacao else 2)
                          and min(len(comuns) / max(len(ta), 1), len(comuns) / max(len(tb), 1)) >= 0.75):
                resultados.add((a, b))
    return resultados


def classificar_caderno(texto: str) -> PerfilDocumento:
    """Etapa ampla: consulta os segmentadores concorrentes já existentes."""
    from .segmentacao import segmentar

    segmento = segmentar(texto, texto)
    padrao = segmento.perfil
    evidencias = ["segmentador:" + padrao]
    if segmento.tem_alternativas:
        evidencias.append("alternativas_detectadas")
    if segmento.diagnostico:
        evidencias.append("perfis_concorrentes_avaliados")
    if segmento.aviso:
        evidencias.append("segmentacao_ambigua")
    codigos = tuple(sorted({m.group(0).upper() for m in _CODIGO_PROVA.finditer(texto)}))
    if codigos:
        evidencias.append("codigo_impresso")
    blocos = segmento.candidatos
    numeros = [
        int(numero)
        for bloco in blocos
        for numero in re.findall(r"(?im)^\s*(?:quest(?:ão|ao)\s*)?(\d{1,3})\b", bloco)
    ]
    candidatos = tuple(dict.fromkeys(
        str(c.get("perfil", "")) for c in segmento.diagnostico if c.get("perfil")
    ))
    faixa = (min(numeros), max(numeros)) if numeros else ()
    return PerfilDocumento(
        "caderno", padrao, tuple(evidencias), codigos, candidatos, segmento.aviso,
        _familia_caderno(padrao, segmento.tem_alternativas), _metadados(texto), faixa,
    )


def classificar_gabarito(texto: str) -> PerfilDocumento:
    """Reconhece famílias de layout comuns sem amarrá-las a uma banca."""
    evidencias = []
    codigos = tuple(sorted({m.group(0).upper() for m in _CODIGO_PROVA.finditer(texto)}))
    if re.search(r"(?im)^\s*item\s+(?:\d+\s*){2,}", texto):
        padrao = "cex_itens_em_grade"
        evidencias.append("rotulo_item_e_sequencia_de_numeros")
    else:
        versoes = []
        tipos_versao = []
        for linha in texto.splitlines():
            m = re.search(r"(?i)\b(prova|tipo|t)\s*([1-4ivx]+)\b", linha)
            if m:
                tipos_versao.append(m.group(1).casefold())
                versoes.append(m.group(2).upper())
        if len(set(versoes)) >= 2:
            padrao = (
                "multiprova_por_colunas"
                if set(tipos_versao) == {"prova"} and all(v in {"1", "2", "3", "4"} for v in versoes)
                else "matriz_multiversao"
            )
            evidencias.append("cabecalhos_de_versao")
        else:
            pares = len(re.findall(r"(?m)^\s*\d{1,3}\s*[-–:.)]\s*[A-E](?:\s|$)", texto, re.I))
            linhas_numericas = len(re.findall(
                r"(?m)^\s*(?:(?:quest(?:ão|ao)|item)\s+)?\d{1,3}(?:\s+\d{1,3}){2,}\s*$", texto, re.I
            ))
            if pares >= 3:
                padrao = "pares_numero_resposta"
                evidencias.append("pares_na_mesma_linha")
            elif linhas_numericas:
                padrao = "matriz_numeros_e_respostas"
                evidencias.append("numeros_agrupados_em_linha")
            else:
                padrao = "lista_respostas"
                evidencias.append("respostas_em_lista_ou_blocos")
    if codigos:
        evidencias.append("seletor_codigo_de_bloco")
    if re.search(r"(?im)^\s*cargo\s*:", texto):
        evidencias.append("seletor_cargo_explicito")
    if re.search(r"(?i)gabarito\s+(?:definitivo|oficial)", texto):
        evidencias.append("rotulo_oficial")
    # Reutiliza as leituras disponíveis para linhas, pares e grade C/E/X.
    # Assim o funil mede a mesma numeração que os extratores realmente conseguem ler.
    from .gabaritos_texto import _extrair_duas_linhas, _extrair_itens_certo_errado, _extrair_pares_mesma_linha

    linhas = [re.sub(r"\s+", " ", linha).strip() for linha in texto.splitlines()]
    mapas = (
        _extrair_pares_mesma_linha(linhas),
        _extrair_duas_linhas(linhas, "", ""),
        _extrair_itens_certo_errado(linhas),
    )
    numeros = {int(n) for mapa in mapas for n in mapa}
    respostas_em_linhas = [
        len(re.findall(r"\b[A-EX]\b", linha, re.I))
        for linha in texto.splitlines()
    ]
    quantidade_sequencial = sum(qtd for qtd in respostas_em_linhas if qtd >= 8)
    if padrao == "cex_itens_em_grade":
        for linha in texto.splitlines():
            if re.match(r"(?i)^\s*item\b", linha):
                numeros.update(int(n) for n in re.findall(r"\d{1,3}", linha))
    familia = "certo_errado" if padrao == "cex_itens_em_grade" else (
        "multipla_escolha" if len(numeros) >= 5 or quantidade_sequencial >= 8 else "desconhecida"
    )
    if quantidade_sequencial >= 8 and not numeros:
        padrao = "listas_respostas_por_bloco"
        evidencias.append("sequencias_de_respostas_por_linha")
    faixa = (min(numeros), max(numeros)) if numeros else ()
    return PerfilDocumento(
        "gabarito", padrao, tuple(evidencias), codigos,
        familia=familia, metadados=_metadados(texto), intervalo_questoes=faixa,
        quantidade_respostas=max(len(numeros), quantidade_sequencial),
    )


def segmentar_blocos_gabarito(texto: str) -> list[BlocoGabarito]:
    """Separa blocos por código, cargo ou versão explícitos."""
    marcadores = []
    vistos = set()
    for match in _CODIGO_PROVA.finditer(texto):
        codigo = match.group(0).upper()
        if codigo not in vistos:
            marcadores.append((match.start(), codigo, ""))
            vistos.add(codigo)
    padrao_cabecalho = r"(?im)^\s*(cargo\s*:\s*([^\n]+)|prova\s+(?:tipo\s+)?([1-4ivx]+)\s*[-:]?\s*([^\n]*))"
    for match in re.finditer(padrao_cabecalho, texto):
        if match.group(2):
            titulo = match.group(2).strip(" :-")
            identificador = "cargo:" + _normalizar(titulo)
        else:
            versao, titulo = match.group(3).upper(), match.group(4).strip(" :-")
            identificador = "prova:" + versao + (":" + _normalizar(titulo) if titulo else "")
        if identificador not in vistos:
            marcadores.append((match.start(), identificador, titulo))
            vistos.add(identificador)
    marcadores.sort(key=lambda item: item[0])
    if not marcadores:
        perfil = classificar_gabarito(texto)
        return [BlocoGabarito("", "", texto, perfil.padrao)] if texto.strip() else []
    blocos = []
    for indice, (inicio, identificador, titulo) in enumerate(marcadores):
        fim = marcadores[indice + 1][0] if indice + 1 < len(marcadores) else len(texto)
        perfil = classificar_gabarito(texto[inicio:fim])
        blocos.append(BlocoGabarito(identificador, titulo, texto[inicio:fim].strip(), perfil.padrao))
    return blocos


def pontuar_associacao(
    perfil_caderno: PerfilDocumento,
    perfil_gabarito: PerfilDocumento,
    *,
    codigo: str = "",
    cargo: str = "",
    evidencia_catalogo: str = "",
) -> dict:
    """Funil: família → identificadores → modelo/versão → faixa numérica."""
    etapas = []
    evidencias = []
    pontos = 0
    confirmada = bool(evidencia_catalogo.strip())

    familia_compativel = (
        perfil_caderno.familia == "desconhecida"
        or perfil_gabarito.familia == "desconhecida"
        or perfil_caderno.familia == perfil_gabarito.familia
    )
    etapas.append({"etapa": "familia", "sobreviveu": familia_compativel or confirmada,
                   "caderno": perfil_caderno.familia, "gabarito": perfil_gabarito.familia})
    if familia_compativel:
        pontos += 10
        evidencias.append("familia_compativel")
    elif not confirmada:
        return {"pontos": pontos, "decisao": "descartada", "evidencias": evidencias, "etapas": etapas}

    meta_caderno = perfil_caderno.metadados or {}
    meta_gabarito = perfil_gabarito.metadados or {}
    codigos_caderno = set(meta_caderno.get("codigo", ()))
    codigos_gabarito = set(meta_gabarito.get("codigo", ())) | set(perfil_gabarito.identificadores)
    codigo_normalizado = codigo.upper().replace("-", "_").strip()
    if re.match(r"\d{3}_", codigo_normalizado):
        codigos_caderno.add(codigo_normalizado)
    codigos_comuns = codigos_caderno & codigos_gabarito
    conflito_codigo = bool(codigos_caderno and codigos_gabarito and not codigos_comuns)
    etapas.append({"etapa": "identificadores", "sobreviveu": not conflito_codigo or confirmada,
                   "codigos_comuns": sorted(codigos_comuns)})
    if codigos_comuns:
        pontos += 60
        evidencias.append("codigo_exato_compartilhado")
    elif conflito_codigo and not confirmada:
        return {"pontos": pontos, "decisao": "descartada", "evidencias": evidencias, "etapas": etapas}

    orgaos_comuns = _sobreposicao_rotulos(
        set(meta_caderno.get("orgao", ())), set(meta_gabarito.get("orgao", ())), organizacao=True
    )
    orgaos_divergentes = bool(meta_caderno.get("orgao") and meta_gabarito.get("orgao") and not orgaos_comuns)
    if orgaos_comuns:
        pontos += 25
        evidencias.append("orgao_compartilhado")
    if orgaos_divergentes and not confirmada:
        etapas.append({"etapa": "identificadores", "sobreviveu": False, "motivo": "orgao_divergente"})
        return {"pontos": pontos, "decisao": "descartada", "evidencias": evidencias, "etapas": etapas}
    if orgaos_divergentes and confirmada:
        etapas.append({"etapa": "identificadores", "sobreviveu": True, "motivo": "vinculo_confirmado_no_catalogo"})

    anos_caderno, anos_gabarito = set(meta_caderno.get("ano", ())), set(meta_gabarito.get("ano", ()))
    anos_comuns = anos_caderno & anos_gabarito
    if anos_comuns:
        pontos += 12
        evidencias.append("ano_compartilhado:" + ",".join(sorted(anos_comuns)))
    versoes_caderno, versoes_gabarito = set(meta_caderno.get("versao", ())), set(meta_gabarito.get("versao", ()))
    versoes_comuns = versoes_caderno & versoes_gabarito
    if versoes_comuns:
        pontos += 25
        evidencias.append("versao_compartilhada:" + ",".join(sorted(versoes_comuns)))
    elif len(versoes_caderno) == len(versoes_gabarito) == 1:
        if not confirmada:
            etapas.append({"etapa": "modelo_versao", "sobreviveu": False, "motivo": "versao_divergente"})
            return {"pontos": pontos, "decisao": "descartada", "evidencias": evidencias, "etapas": etapas}
    cargos_caderno = set(meta_caderno.get("cargo", ()))
    cargos_gabarito = set(meta_gabarito.get("cargo", ()))
    cargo_normalizado = _normalizar(cargo)
    if cargo_normalizado:
        cargos_caderno.add(cargo_normalizado)
    cargos_comuns = _sobreposicao_rotulos(cargos_caderno, cargos_gabarito)
    if cargos_comuns:
        pontos += 30
        evidencias.append("cargo_exato_compartilhado")
    if cargo.strip():
        evidencias.append("cargo_confirmado_no_catalogo")
    conflito_cargo = bool(cargos_caderno and cargos_gabarito and not cargos_comuns)
    modelo_compativel = not conflito_cargo
    etapas.append({"etapa": "modelo_versao", "sobreviveu": modelo_compativel or confirmada,
                   "cargos_comuns": sorted(cargos_comuns), "versoes_comuns": sorted(versoes_comuns)})
    if conflito_cargo and not confirmada:
        return {"pontos": pontos, "decisao": "descartada", "evidencias": evidencias, "etapas": etapas}

    layout_compativel = familia_compativel
    etapas.append({"etapa": "layout", "sobreviveu": layout_compativel or confirmada,
                   "caderno": perfil_caderno.padrao, "gabarito": perfil_gabarito.padrao})
    if layout_compativel:
        pontos += 10
        evidencias.append("layouts_compativeis")

    faixa_caderno, faixa_gabarito = perfil_caderno.intervalo_questoes, perfil_gabarito.intervalo_questoes
    if faixa_caderno and faixa_gabarito:
        inicio = max(faixa_caderno[0], faixa_gabarito[0])
        fim = min(faixa_caderno[1], faixa_gabarito[1])
        sobreposicao = max(0, fim - inicio + 1)
        total = faixa_caderno[1] - faixa_caderno[0] + 1
        cobertura = sobreposicao / total if total else 0
        etapas.append({"etapa": "faixa_numerica", "sobreviveu": sobreposicao > 0 or confirmada,
                       "sobreposicao": sobreposicao, "cobertura": cobertura})
        if sobreposicao:
            pontos += 20 if cobertura >= 0.8 else 8
            evidencias.append(f"faixa_numerica_compativel:{cobertura:.0%}")
        elif not confirmada:
            return {"pontos": pontos, "decisao": "descartada", "evidencias": evidencias, "etapas": etapas}
    else:
        etapas.append({"etapa": "faixa_numerica", "sobreviveu": True, "resultado": "inconclusivo"})

    if confirmada:
        evidencias.append("catalogo_confirmado: " + evidencia_catalogo.strip())
        decisao = "confirmada"
    elif pontos >= 75 and codigos_comuns and (versoes_comuns or cargos_comuns):
        decisao = "candidato_forte_revisao"
    elif pontos >= 35:
        decisao = "candidato_revisao"
    else:
        decisao = "revisao_manual"
    return {"pontos": pontos, "decisao": decisao, "evidencias": evidencias, "etapas": etapas}
