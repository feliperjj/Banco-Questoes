import json
import random
from functools import wraps

import datetime
from pathlib import Path

from peewee import Case, JOIN, fn, prefetch

from src.db.database import db, init_db, initialized_database_batch
from src.db.models import (
    Alternativa,
    Prova,
    ProvaCadastrada,
    ProvaCadastradaQuestao,
    ProvaQuestao,
    Questao,
    Resposta,
    RevisaoEspacada,
    Tentativa,
    ProgressoTentativa,
    QuestaoVersao,
    DocumentoFonte,
)
from src.importador.validacao import gabarito_valido, normalizar_gabarito, problemas_estrutura
from src.models.provenance_service import assess_version, create_question_version, create_source, register_extraction, version_is_eligible


CAMPOS_QUESTAO = ("numero_oficial", "enunciado", "texto_apoio", "tipo", "disciplina", "topico", "banca", "ano", "cargo", "orgao", "dificuldade", "gabarito", "comentario", "imagem_path")
GABARITOS_AVALIAVEIS = ("A", "B", "C", "D", "E", "Certo", "Errado")
# Uma questão oficialmente anulada tem gabarito confirmado, embora não entre
# no sorteio de provas aleatórias nem no cálculo de nota.
GABARITOS_CONFIRMADOS = GABARITOS_AVALIAVEIS + ("Anulada",)


def _verificar_fontes_em_lote(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        from src.models.provenance_service import begin_source_verification_batch, end_source_verification_batch
        token = begin_source_verification_batch()
        try:
            return function(*args, **kwargs)
        finally:
            end_source_verification_batch(token)
    return wrapped


def _as_dict(model, fields=None):
    names = fields or [field.name for field in model._meta.sorted_fields]
    return {name: _legacy_value(getattr(model, name)) for name in names}


def _legacy_value(value):
    """Mantém os textos de data que a antiga camada sqlite3 devolvia."""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return str(value)
    return value


def _tempo_limite_da_configuracao(configuracao: dict) -> int:
    try:
        return max(0, int(configuracao.get("_tempo_limite_min") or 0))
    except (TypeError, ValueError):
        return 0


def _questao_dict(questao):
    dados = _as_dict(questao)
    if questao.tipo == "multipla_escolha":
        dados["alternativas"] = [_as_dict(alt, ["letra", "texto"]) for alt in questao.alternativas]
    return dados


def _apresentacao_fonte(version):
    """Carrega só os recursos da versão exata; nunca de gabaritos."""
    from src.models.provenance_service import get_automatic_validation, verify_source, _hash_file, _resource_path
    automatic = get_automatic_validation(version.id)
    if automatic["valida"]:
        return dict(automatic["manifesto"]["apresentacao"], verificacao="automatica")
    if not version.execucao_extracao_id or not version.documento_fonte_id:
        return None
    extraction = version.execucao_extracao
    if extraction.extrator not in {"reparacao_documental", "reconstrucao_canonica_preparada"}:
        return None
    integrity = verify_source(version.documento_fonte_id)
    if not integrity["integro"]:
        return None
    try:
        media = json.loads(extraction.parametros_json or "{}").get("facsimile")
        if not media or not media.get("questao"):
            return None
        for asset in media["questao"] + media.get("contexto", []):
            path = _resource_path(asset.get("path"))
            if not path or not path.is_file() or _hash_file(path) != asset.get("sha256"):
                return None
        return dict(media, modo="facsimile", verificacao="conteudo_reparado")
    except (ValueError, TypeError, KeyError):
        return None


def _criar_questao_sem_transacao(dados: dict, source_id: int | None = None, extraction_id: int | None = None) -> int:
    dados = dict(dados)
    if "numero_oficial" not in dados:
        dados["numero_oficial"] = dados.get("numero")
    questao = Questao.create(**{campo: dados.get(campo) for campo in CAMPOS_QUESTAO})
    if questao.tipo == "multipla_escolha":
        for alt in dados.get("alternativas") or []:
            Alternativa.create(questao=questao.id, letra=alt["letra"], texto=alt["texto"])
    create_question_version(questao.id, source_id=source_id, extraction_id=extraction_id)
    return questao.id


def _ultima_versao_questao(questao_id: int):
    return (QuestaoVersao.select()
            .where(QuestaoVersao.questao == questao_id)
            .order_by(QuestaoVersao.numero_versao.desc()).first())


def _versao_liberada(questao_id: int):
    version = _ultima_versao_questao(questao_id)
    return version if version and version_is_eligible(version) else None


def _source_from_local_path(value: str | None, tipo: str) -> int | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        root = Path(__file__).resolve().parents[2]
        direct = root / path
        samples = root / "samples" / path
        path = direct if direct.is_file() else samples if samples.is_file() else direct
    if not path.is_file():
        return None
    return create_source(path, tipo=tipo)


def criar_questao(dados: dict) -> int:
    init_db()
    with db.atomic():
        return _criar_questao_sem_transacao(dados)


def criar_questoes_em_lote(
    lista_dados: list[dict],
    *,
    source_path: str | None = None,
    extraction_metadata: dict | None = None,
) -> list[int]:
    init_db()
    ids = []
    with db.atomic():
        source_id = _source_from_local_path(source_path, "caderno_questoes")
        extraction_id = None
        if extraction_metadata:
            metadata = dict(extraction_metadata)
            extraction_id = register_extraction(
                source_id,
                extractor=metadata.pop("extractor", "src.importador.extrator.extrair_texto"),
                extractor_version=metadata.pop("extractor_version", None),
                profile=metadata.pop("profile", None),
                profile_version=metadata.pop("profile_version", None),
                parameters=metadata.pop("parameters", {}),
                diagnostics=metadata.pop("diagnostics", []),
            )
        for dados in lista_dados:
            ids.append(_criar_questao_sem_transacao(dados, source_id, extraction_id))
    return ids


def atualizar_questao(q_id: int, dados: dict, *, source_id=None, extraction_id=None):
    init_db()
    with db.atomic():
        questao = Questao.get_by_id(q_id)
        for campo in CAMPOS_QUESTAO:
            if campo in dados:
                setattr(questao, campo, dados[campo])
        if "numero_oficial" not in dados and "numero" in dados:
            questao.numero_oficial = dados["numero"]
        questao.save()
        if questao.tipo == "multipla_escolha" and "alternativas" in dados:
            Alternativa.delete().where(Alternativa.questao == q_id).execute()
            for alt in dados["alternativas"]:
                Alternativa.create(questao=q_id, letra=alt["letra"], texto=alt["texto"])
        elif questao.tipo != "multipla_escolha":
            # Alternativas não fazem parte de questões certo/errado. Remova
            # resíduos ao trocar o tipo para evitar que reapareçam depois.
            Alternativa.delete().where(Alternativa.questao == q_id).execute()
        create_question_version(q_id, source_id=source_id, extraction_id=extraction_id)


def excluir_questao(q_id: int):
    init_db()
    Questao.update(ativa=False).where(Questao.id == q_id).execute()


def buscar_questoes(filtros: dict = None, texto: str = None) -> list[dict]:
    init_db()
    query = Questao.select().where(Questao.ativa == True)
    if texto:
        query = query.where(Questao.enunciado.contains(texto))
    if filtros and filtros.get("disciplina"):
        query = query.where(Questao.disciplina == filtros["disciplina"])
    if filtros and filtros.get("tipo"):
        query = query.where(Questao.tipo == filtros["tipo"])
    if filtros and filtros.get("banca"):
        query = query.where(Questao.banca == filtros["banca"])
    if filtros and filtros.get("topico"):
        query = query.where(Questao.topico == filtros["topico"])
    return [_questao_dict(questao) for questao in prefetch(query, Alternativa)]


def obter_questao(q_id: int) -> dict | None:
    init_db()
    questao = Questao.get_or_none(Questao.id == q_id)
    return _questao_dict(questao) if questao else None


def ultima_versao(q_id: int):
    init_db()
    return _ultima_versao_questao(q_id)


def diagnosticar_questao(q_id: int) -> dict:
    """Avalia a versão atual sem alterar aprovação ou histórico."""
    version = _ultima_versao_questao(q_id)
    if version is None:
        return assess_version(-1)
    return assess_version(version.id)


def listar_disciplinas() -> list[str]:
    init_db()
    query = Questao.select(Questao.disciplina).distinct().where(Questao.disciplina.is_null(False), Questao.disciplina != "")
    return [row.disciplina for row in query]


def listar_topicos(disciplina=None) -> list[str]:
    init_db()
    query = Questao.select(Questao.topico).distinct().where(Questao.topico.is_null(False), Questao.topico != "")
    if disciplina:
        query = query.where(Questao.disciplina == disciplina)
    return [row.topico for row in query]


def listar_bancas() -> list[str]:
    init_db()
    query = Questao.select(Questao.banca).distinct().where(Questao.banca.is_null(False), Questao.banca != "")
    return [row.banca for row in query]


def _questoes_avaliaveis_query():
    return Questao.select(Questao.id).where(
        (Questao.ativa == True) & Questao.gabarito.in_(GABARITOS_AVALIAVEIS)
    )


def _filtros_para_query(query, filtros):
    if filtros and filtros.get("disciplina"):
        query = query.where(Questao.disciplina == filtros["disciplina"])
    if filtros and filtros.get("tipo"):
        query = query.where(Questao.tipo == filtros["tipo"])
    if filtros and filtros.get("banca"):
        query = query.where(Questao.banca == filtros["banca"])
    if filtros and filtros.get("topico"):
        query = query.where(Questao.topico == filtros["topico"])
    return query


def _questoes_elegiveis(filtros=None):
    query = _filtros_para_query(_questoes_avaliaveis_query(), filtros)
    # Gabarito não basta para uma questão entrar em um simulado: registros
    # antigos também precisam ter estrutura utilizável.
    candidatos = list(Questao.select().where(Questao.id.in_(query)))
    alternativas = {}
    for alternativa in Alternativa.select().where(Alternativa.questao.in_(query)):
        alternativas.setdefault(alternativa.questao_id, []).append(
            {"letra": alternativa.letra, "texto": alternativa.texto}
        )
    validos = []
    for questao in candidatos:
        dados = {
            "enunciado": questao.enunciado,
            "tipo": questao.tipo,
            "gabarito": questao.gabarito,
            "alternativas": alternativas.get(questao.id, []),
        }
        if not problemas_estrutura(dados) and _versao_liberada(questao.id):
            validos.append(questao.id)
    return query.where(Questao.id.in_(validos))


@_verificar_fontes_em_lote
def contar_questoes_elegiveis(filtros=None):
    init_db()
    return _questoes_elegiveis(filtros).count()


def criar_prova(
    nome: str,
    filtros: dict,
    quantidade: int,
    tempo_limite_min: int,
    prova_cadastrada_id: int | None = None,
    prova_existente_id: int | None = None,
) -> int:
    """Cria uma tentativa futura aleatória ou baseada em prova cadastrada."""
    init_db()
    if prova_cadastrada_id is not None and prova_existente_id is not None:
        raise ValueError("Informe apenas uma origem para a prova.")
    if prova_cadastrada_id is not None:
        return criar_prova_a_partir_de_cadastrada(
            nome, prova_cadastrada_id, tempo_limite_min
        )
    if prova_existente_id is not None:
        return criar_prova_a_partir_de_existente(
            nome, prova_existente_id, tempo_limite_min
        )
    if quantidade <= 0:
        return 0
    # Questões anuladas continuam no histórico, mas não compõem novas provas:
    # elas não são avaliáveis e poderiam gerar uma prova com denominador zero.
    query = _questoes_elegiveis(filtros)
    todas_questoes = [questao.id for questao in query]
    if not todas_questoes:
        return 0
    selecionadas = random.sample(todas_questoes, min(quantidade, len(todas_questoes)))
    configuracao = dict(filtros or {})
    configuracao["_tempo_limite_min"] = max(0, int(tempo_limite_min or 0))
    with db.atomic():
        prova = Prova.create(nome=nome, filtros=json.dumps(configuracao))
        for ordem, q_id in enumerate(selecionadas, 1):
            version = _versao_liberada(q_id)
            if version is None:
                raise ValueError("A questão perdeu a revisão válida durante a criação da prova.")
            ProvaQuestao.create(prova=prova.id, questao=q_id, questao_versao=version.id, ordem=ordem)
    return prova.id


def criar_prova_cadastrada(
    nome: str,
    lista_dados: list[dict],
    arquivo_questoes: str | None = None,
    arquivo_gabarito: str | None = None,
    instrucoes_prova: str | None = None,
) -> int:
    """Salva um lote importado como uma prova de origem reutilizável."""
    init_db()
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome da prova cadastrada.")
    if not lista_dados:
        raise ValueError("A prova precisa possuir ao menos uma questão.")
    with db.atomic():
        source_questions = _source_from_local_path(arquivo_questoes, "caderno_questoes")
        source_answers = _source_from_local_path(arquivo_gabarito, "documento_gabarito")
        prova = ProvaCadastrada.create(
            nome=nome,
            arquivo_questoes=arquivo_questoes or None,
            arquivo_gabarito=arquivo_gabarito or None,
            documento_fonte_questoes=source_questions,
            documento_fonte_gabarito=source_answers,
            instrucoes_prova=(instrucoes_prova or "").strip() or None,
        )
        for ordem, dados in enumerate(lista_dados, 1):
            questao_id = dados.get("_questao_id") or _criar_questao_sem_transacao(dados, source_questions)
            if not Questao.get_or_none(Questao.id == questao_id):
                raise ValueError("A questão revisada não existe mais no banco.")
            version = _ultima_versao_questao(questao_id)
            ProvaCadastradaQuestao.create(
                prova_cadastrada=prova.id,
                questao=questao_id,
                questao_versao=version.id if version else None,
                ordem=ordem,
            )
    return prova.id


@_verificar_fontes_em_lote
def listar_provas_cadastradas() -> list[dict]:
    """Lista provas de origem e indica se já podem gerar uma nova prova."""
    init_db()
    total = fn.COUNT(ProvaCadastradaQuestao.questao).alias("qtd_questoes")
    com_gabarito = fn.SUM(
        Case(
            None,
            (
                (
                    Questao.gabarito.in_(GABARITOS_CONFIRMADOS),
                    1,
                ),
            ),
            0,
        )
    ).alias("qtd_com_gabarito")
    query = (
        ProvaCadastrada.select(
            ProvaCadastrada.id,
            ProvaCadastrada.nome,
            ProvaCadastrada.arquivo_questoes,
            ProvaCadastrada.arquivo_gabarito,
            ProvaCadastrada.criada_em,
            total,
            com_gabarito,
        )
        .join(ProvaCadastradaQuestao, JOIN.LEFT_OUTER)
        .join(Questao, JOIN.LEFT_OUTER)
        .where(ProvaCadastrada.ativa == True)
        .group_by(ProvaCadastrada.id)
        .order_by(ProvaCadastrada.criada_em.desc())
    )
    provas = []
    for prova in query:
        qtd = int(prova.qtd_questoes or 0)
        vinculadas = list(
            ProvaCadastradaQuestao.select(ProvaCadastradaQuestao, QuestaoVersao)
            .join(QuestaoVersao, JOIN.LEFT_OUTER)
            .where(ProvaCadastradaQuestao.prova_cadastrada == prova.id)
        )
        qtd_avaliaveis = sum(bool(_versao_liberada(item.questao_id)) for item in vinculadas)
        provas.append(
            {
                "id": prova.id,
                "nome": prova.nome,
                "arquivo_questoes": prova.arquivo_questoes,
                "arquivo_gabarito": prova.arquivo_gabarito,
                "criada_em": _legacy_value(prova.criada_em),
                "qtd_questoes": qtd,
                "qtd_avaliaveis": qtd_avaliaveis,
                "qtd_com_gabarito": int(prova.qtd_com_gabarito or 0),
                "qtd_sem_gabarito": qtd - int(prova.qtd_com_gabarito or 0),
                "pronta": qtd > 0 and qtd == qtd_avaliaveis,
            }
        )
    return provas


@_verificar_fontes_em_lote
def listar_lotes_importados_sem_prova() -> list[dict]:
    """Recupera lotes antigos de importação que ainda não tinham vínculo de prova.

    Antes do cadastro de ProvaCadastrada, o banco guardava as questões em sequência,
    com timestamps gerados durante o salvamento do lote. Uma pausa de mais de um
    minuto separa lotes antigos sem misturar os metadados das questões.
    """
    init_db()
    vinculadas = (
        ProvaCadastradaQuestao.select(ProvaCadastradaQuestao.questao)
        .join(ProvaCadastrada)
        .where(ProvaCadastrada.ativa == True)
    )
    questoes = list(
        Questao.select().where(
            (Questao.ativa == True) & ~Questao.id.in_(vinculadas)
        ).order_by(Questao.id)
    )
    lotes_brutos = []
    lote_atual = []
    anterior = None

    for questao in questoes:
        criada_em = questao.criada_em
        if isinstance(criada_em, str):
            try:
                criada_em = datetime.datetime.fromisoformat(criada_em)
            except ValueError:
                criada_em = None
        if (
            lote_atual
            and anterior is not None
            and criada_em is not None
            and (criada_em - anterior).total_seconds() > 60
        ):
            if len(lote_atual) > 1:
                lotes_brutos.append(lote_atual)
            lote_atual = []
        lote_atual.append(questao)
        anterior = criada_em
    if len(lote_atual) > 1:
        lotes_brutos.append(lote_atual)

    lotes = []
    for questoes_lote in lotes_brutos:
        bancas = {q.banca.strip() for q in questoes_lote if q.banca and q.banca.strip()}
        anos = {q.ano for q in questoes_lote if q.ano}
        partes_nome = []
        if len(bancas) == 1:
            partes_nome.append(next(iter(bancas)))
        if len(anos) == 1:
            partes_nome.append(str(next(iter(anos))))
        if not partes_nome:
            criada_em = questoes_lote[0].criada_em
            if isinstance(criada_em, str):
                try:
                    criada_em = datetime.datetime.fromisoformat(criada_em)
                except ValueError:
                    criada_em = None
            data = criada_em.strftime("%d/%m/%Y") if criada_em else "lote antigo"
            partes_nome.append(f"Prova importada · {data}")

        avaliaveis = sum(bool(_versao_liberada(q.id)) for q in questoes_lote)
        com_gabarito = sum(q.gabarito in GABARITOS_CONFIRMADOS for q in questoes_lote)
        questao_ids = [q.id for q in questoes_lote]
        lotes.append(
            {
                "id": questao_ids[0],
                "origem_tipo": "lote_importado",
                "nome": " · ".join(partes_nome),
                "qtd_questoes": len(questoes_lote),
                "qtd_avaliaveis": avaliaveis,
                "qtd_com_gabarito": com_gabarito,
                "qtd_sem_gabarito": len(questoes_lote) - com_gabarito,
                "pronta": len(questoes_lote) == avaliaveis,
                "questao_ids": questao_ids,
                "criada_em": _legacy_value(questoes_lote[0].criada_em),
            }
        )
    return list(reversed(lotes))


@_verificar_fontes_em_lote
def consultar_questoes_importadas(prova_cadastrada_id=None, *, questao_ids=None) -> list[dict]:
    """Lê o conteúdo atual na ordem importada, sem criar prova ou tentativa."""
    if (prova_cadastrada_id is None) == (questao_ids is None):
        raise ValueError("Informe apenas uma origem para consultar as questões.")
    if prova_cadastrada_id is not None:
        fonte = ProvaCadastrada.get_or_none(
            (ProvaCadastrada.id == prova_cadastrada_id) & (ProvaCadastrada.ativa == True)
        )
        if fonte is None:
            raise ValueError("A prova importada não existe mais no acervo ativo.")
        ordem_ids = [
            (item.ordem, item.questao_id)
            for item in ProvaCadastradaQuestao.select()
            .where(ProvaCadastradaQuestao.prova_cadastrada == fonte.id)
            .order_by(ProvaCadastradaQuestao.ordem, ProvaCadastradaQuestao.questao)
        ]
    else:
        ordem_ids = list(enumerate(dict.fromkeys(questao_ids), 1))
    ids = [qid for _, qid in ordem_ids]
    questoes = {
        questao.id: _questao_dict(questao)
        for questao in prefetch(Questao.select().where(Questao.id.in_(ids)), Alternativa)
    }
    if len(questoes) != len(set(ids)):
        raise ValueError("Uma ou mais questões da prova não existem mais.")
    result = []
    for ordem, qid in ordem_ids:
        data = dict(questoes[qid], ordem_na_prova=ordem)
        version = _ultima_versao_questao(qid)
        if version:
            data["apresentacao_fonte"] = _apresentacao_fonte(version)
        result.append(data)
    return result


def criar_prova_a_partir_de_questoes(
    nome: str, questao_ids: list[int], tempo_limite_min: int = 0,
    configuracao_extra: dict | None = None,
) -> int:
    """Cria uma prova executável a partir da composição de um lote importado legado."""
    init_db()
    ids = list(dict.fromkeys(questao_ids or []))
    if not ids:
        raise ValueError("A prova importada não possui questões.")
    encontradas = list(
        Questao.select(Questao.id, Questao.ativa, Questao.gabarito).where(
            Questao.id.in_(ids)
        )
    )
    por_id = {questao.id: questao for questao in encontradas}
    if len(por_id) != len(ids):
        raise ValueError("Uma ou mais questões da prova importada não existem mais.")
    indisponiveis = [
        qid
        for qid in ids
        if not por_id[qid].ativa or por_id[qid].gabarito not in GABARITOS_CONFIRMADOS
    ]
    if indisponiveis:
        raise ValueError(
            f"A prova importada possui {len(indisponiveis)} questão(ões) "
            "sem gabarito avaliável ou inativas."
        )
    versions = {qid: _versao_liberada(qid) for qid in ids}
    if any(version is None for version in versions.values()):
        raise ValueError("A prova importada contém conteúdo ou gabarito ainda não conferido com a fonte.")
    configuracao = {
        "modo": "prova_importada_lote",
        "lote_importacao_id": ids[0],
        "_tempo_limite_min": max(0, int(tempo_limite_min or 0)),
    }
    if configuracao_extra:
        configuracao.update(configuracao_extra)
    with db.atomic():
        prova = Prova.create(nome=nome, filtros=json.dumps(configuracao))
        for ordem, qid in enumerate(ids, 1):
            ProvaQuestao.create(prova=prova.id, questao=qid, questao_versao=versions[qid].id, ordem=ordem)
    return prova.id


@_verificar_fontes_em_lote
def criar_prova_parcial_importada(
    nome: str,
    *,
    prova_cadastrada_id: int | None = None,
    questao_ids: list[int] | None = None,
    tempo_limite_min: int = 0,
) -> int:
    """Cria uma prova somente com os itens liberados de uma origem importada.

    A origem é lida novamente no momento do clique para evitar confiar na
    contagem exibida pela tela.  A ordem original é preservada e a composição
    criada continua sendo um snapshot imutável das versões elegíveis.
    """
    if (prova_cadastrada_id is None) == (questao_ids is None):
        raise ValueError("Informe apenas a prova cadastrada ou o lote importado.")
    init_db()
    if prova_cadastrada_id is not None:
        fonte = ProvaCadastrada.get_or_none(
            (ProvaCadastrada.id == prova_cadastrada_id)
            & (ProvaCadastrada.ativa == True)
        )
        if fonte is None:
            raise ValueError("A prova importada não existe mais no acervo ativo.")
        ordem_ids = [
            item.questao_id
            for item in ProvaCadastradaQuestao.select()
            .where(ProvaCadastradaQuestao.prova_cadastrada == fonte.id)
            .order_by(ProvaCadastradaQuestao.ordem, ProvaCadastradaQuestao.questao)
        ]
        origem_config = {"prova_cadastrada_id": fonte.id, "lote_importacao_id": None}
    else:
        ordem_ids = list(dict.fromkeys(questao_ids or []))
        origem_config = {"lote_importacao_id": ordem_ids[0] if ordem_ids else None}
    if not ordem_ids:
        raise ValueError("A prova importada não possui questões.")

    # A avaliação é feita uma única vez por item dentro do lote de verificação;
    # isso também reutiliza a leitura/hash da fonte entre versões da mesma prova.
    selecionados = []
    with initialized_database_batch():
        for qid in ordem_ids:
            questao = Questao.get_or_none(Questao.id == qid)
            version = _ultima_versao_questao(qid) if questao else None
            if (
                questao is not None
                and questao.ativa
                and questao.gabarito in GABARITOS_AVALIAVEIS
                and version is not None
                and version_is_eligible(version)
            ):
                selecionados.append(qid)
    if not selecionados:
        raise ValueError("Nenhuma questão da prova importada está liberada para resolver.")
    excluded = [qid for qid in ordem_ids if qid not in set(selecionados)]
    configuracao = {
        "modo": "prova_importada_parcial",
        "questao_ids_originais": ordem_ids,
        "questao_ids_excluidas": excluded,
        "prova_id": prova_cadastrada_id,
        "_tempo_limite_min": max(0, int(tempo_limite_min or 0)),
        **origem_config,
    }
    with initialized_database_batch():
        return criar_prova_a_partir_de_questoes(
            f"{len(selecionados)} de {len(ordem_ids)} verificadas — {nome}",
            selecionados,
            tempo_limite_min,
            configuracao_extra=configuracao,
        )


def listar_fontes_de_prova() -> list[dict]:
    """Lista provas importadas e provas já geradas que podem ser reutilizadas."""
    fontes = [dict(prova, origem_tipo="cadastrada", origem_id=prova["id"])
              for prova in listar_provas_cadastradas()]
    qtd = fn.COUNT(ProvaQuestao.questao).alias("qtd_questoes")
    query = (
        Prova.select(Prova.id, Prova.nome, Prova.criada_em, qtd)
        .join(ProvaQuestao, JOIN.LEFT_OUTER)
        .group_by(Prova.id)
        .order_by(Prova.criada_em.desc())
    )
    for prova in query:
        qtd_questoes = int(prova.qtd_questoes or 0)
        vinculadas = list(
            ProvaQuestao.select(ProvaQuestao, Questao)
            .join(Questao)
            .where(ProvaQuestao.prova == prova.id)
        )
        qtd_avaliaveis = sum(
            bool(item.questao.ativa and item.questao_versao_id and version_is_eligible(item.questao_versao))
            for item in vinculadas
        )
        fontes.append(
            {
                "id": prova.id,
                "origem_id": prova.id,
                "origem_tipo": "existente",
                "nome": prova.nome,
                "criada_em": _legacy_value(prova.criada_em),
                "qtd_questoes": qtd_questoes,
                "qtd_avaliaveis": qtd_avaliaveis,
                "pronta": qtd_questoes > 0 and qtd_questoes == qtd_avaliaveis,
            }
        )
    return fontes


def criar_prova_a_partir_de_cadastrada(
    nome: str, prova_cadastrada_id: int, tempo_limite_min: int
) -> int:
    """Copia a composição e a ordem de uma prova cadastrada para uma prova executável."""
    init_db()
    fonte = ProvaCadastrada.get_or_none(
        (ProvaCadastrada.id == prova_cadastrada_id)
        & (ProvaCadastrada.ativa == True)
    )
    if fonte is None:
        raise ValueError("A prova cadastrada informada não existe.")
    vinculadas = list(
        ProvaCadastradaQuestao.select(ProvaCadastradaQuestao, Questao)
        .join(Questao)
        .where(ProvaCadastradaQuestao.prova_cadastrada == fonte.id)
        .order_by(ProvaCadastradaQuestao.ordem)
    )
    if not vinculadas:
        raise ValueError("A prova cadastrada não possui questões.")
    indisponiveis = [
        item.questao_id
        for item in vinculadas
        if not item.questao.ativa
        or _versao_liberada(item.questao_id) is None
    ]
    if indisponiveis:
        raise ValueError(
            "A prova cadastrada possui "
            f"{len(indisponiveis)} questão(ões) sem versão conferida e evidência íntegra "
            "para conteúdo e gabarito. "
            "Corrija a importação antes de utilizá-la."
        )
    configuracao = {
        "modo": "prova_cadastrada",
        "prova_cadastrada_id": fonte.id,
        "_tempo_limite_min": max(0, int(tempo_limite_min or 0)),
    }
    versions = {item.questao_id: _versao_liberada(item.questao_id) for item in vinculadas}
    with db.atomic():
        prova = Prova.create(nome=nome, filtros=json.dumps(configuracao))
        for item in vinculadas:
            ProvaQuestao.create(
                prova=prova.id,
                questao=item.questao_id,
                questao_versao=versions[item.questao_id].id,
                ordem=item.ordem,
            )
    return prova.id


def criar_prova_a_partir_de_existente(
    nome: str, prova_existente_id: int, tempo_limite_min: int
) -> int:
    """Copia a composição de uma prova já gerada e preserva sua ordem."""
    init_db()
    fonte = Prova.get_or_none(Prova.id == prova_existente_id)
    if fonte is None:
        raise ValueError("A prova existente informada não existe.")
    vinculadas = list(
        ProvaQuestao.select(ProvaQuestao, Questao)
        .join(Questao)
        .where(ProvaQuestao.prova == fonte.id)
        .order_by(ProvaQuestao.ordem)
    )
    if not vinculadas:
        raise ValueError("A prova existente não possui questões.")
    indisponiveis = [
        item.questao_id
        for item in vinculadas
        if not item.questao.ativa
        or _versao_liberada(item.questao_id) is None
    ]
    if indisponiveis:
        raise ValueError(
            "A prova existente possui "
            f"{len(indisponiveis)} questão(ões) sem versão conferida e evidência íntegra."
        )
    configuracao = {
        "modo": "prova_existente",
        "prova_existente_id": fonte.id,
        "_tempo_limite_min": max(0, int(tempo_limite_min or 0)),
    }
    versions = {item.questao_id: _versao_liberada(item.questao_id) for item in vinculadas}
    with db.atomic():
        prova = Prova.create(nome=nome, filtros=json.dumps(configuracao))
        for item in vinculadas:
            ProvaQuestao.create(
                prova=prova.id,
                questao=item.questao_id,
                questao_versao=versions[item.questao_id].id,
                ordem=item.ordem,
            )
    return prova.id


def listar_provas(incluir_concluidas: bool = False) -> list[dict]:
    init_db()
    qtd = fn.COUNT(ProvaQuestao.questao).alias("qtd_questoes")
    query = (Prova.select(Prova.id, Prova.nome, Prova.filtros, Prova.criada_em, qtd)
             .join(ProvaQuestao, join_type=JOIN.LEFT_OUTER)
             .group_by(Prova.id)
             .order_by(Prova.criada_em.desc()))
    provas = []
    for prova in query:
        concluida = (Tentativa.select()
                     .where((Tentativa.prova == prova.id) & Tentativa.finalizada_em.is_null(False))
                     .exists())
        if concluida and not incluir_concluidas:
            continue
        try:
            configuracao = json.loads(prova.filtros or "{}")
        except (TypeError, json.JSONDecodeError):
            configuracao = {}
        provas.append({"id": prova.id, "nome": prova.nome, "criada_em": _legacy_value(prova.criada_em), "qtd_questoes": prova.qtd_questoes, "concluida": concluida, "em_andamento": Tentativa.select().where((Tentativa.prova == prova.id) & Tentativa.finalizada_em.is_null(True)).exists(), "tempo_limite_min": _tempo_limite_da_configuracao(configuracao)})
    return provas


def obter_prova(prova_id: int) -> dict | None:
    init_db()
    prova = Prova.get_or_none(Prova.id == prova_id)
    if prova is None:
        return None
    try:
        configuracao = json.loads(prova.filtros or "{}")
    except (TypeError, json.JSONDecodeError):
        configuracao = {}
    return {"id": prova.id, "nome": prova.nome, "tempo_limite_min": _tempo_limite_da_configuracao(configuracao)}


def iniciar_tentativa(prova_id: int) -> int:
    init_db()
    prova = Prova.get_or_none(Prova.id == prova_id)
    if prova is None:
        raise ValueError("A prova informada não existe.")
    if Tentativa.select().where(
        (Tentativa.prova == prova_id) & Tentativa.finalizada_em.is_null(False)
    ).exists():
        raise ValueError("Esta prova já foi finalizada.")
    aberta = Tentativa.get_or_none(
        (Tentativa.prova == prova_id) & Tentativa.finalizada_em.is_null(True)
    )
    if aberta is not None:
        return aberta.id
    composicao = list(ProvaQuestao.select().where(ProvaQuestao.prova == prova_id))
    if not composicao:
        raise ValueError("A prova não possui questões.")
    indisponiveis = [
        item.questao_id for item in composicao
        if not item.questao_versao_id or not version_is_eligible(item.questao_versao)
    ]
    if indisponiveis:
        raise ValueError(
            f"Não é possível iniciar: {len(indisponiveis)} questão(ões) não têm conteúdo e gabarito "
            "conferidos com fonte íntegra. A composição histórica foi preservada."
        )
    return Tentativa.create(prova=prova_id).id


def salvar_progresso(tentativa_id, respostas, indice, tempo_seg):
    init_db()
    with db.atomic():
        tentativa = Tentativa.get_by_id(tentativa_id)
        if tentativa.finalizada_em is not None:
            raise ValueError("Esta tentativa já foi finalizada.")
        ids = {q.questao_id for q in ProvaQuestao.select().where(ProvaQuestao.prova == tentativa.prova_id)}
        if set(respostas) - ids:
            raise ValueError("Resposta não pertence à prova.")
        ProgressoTentativa.insert(tentativa=tentativa_id, respostas=json.dumps(respostas),
                                 indice=max(0, indice), tempo_seg=max(0, tempo_seg)).on_conflict_replace().execute()


def obter_progresso(tentativa_id):
    init_db()
    progresso = ProgressoTentativa.get_or_none(ProgressoTentativa.tentativa == tentativa_id)
    if progresso is None:
        return {"respostas": {}, "indice": 0, "tempo_seg": 0}
    return {"respostas": {int(k): v for k, v in json.loads(progresso.respostas).items()},
            "indice": progresso.indice, "tempo_seg": progresso.tempo_seg}


def finalizar_tentativa(tentativa_id: int, respostas_usuario: dict, tempo_gasto_seg: int) -> dict:
    init_db()
    total_acertos = 0
    total_questoes = len(respostas_usuario)
    detalhes_erradas = []
    tentativa = Tentativa.get_by_id(tentativa_id)
    if tentativa.finalizada_em is not None:
        raise ValueError("Esta tentativa já foi finalizada.")
    # Questões não respondidas continuam fazendo parte da prova. O total da
    # nota deve vir da composição da prova, e não da quantidade de respostas.
    if tentativa.prova_id:
        itens = list(ProvaQuestao.select().where(ProvaQuestao.prova == tentativa.prova_id))
        questoes_da_prova = {row.questao_id for row in itens}
        invalidas = set(respostas_usuario) - questoes_da_prova
        if invalidas:
            raise ValueError("A tentativa contém respostas para questões que não pertencem à prova.")
        if any(item.questao_versao_id is None for item in itens):
            raise ValueError(
                "Esta tentativa legada não tem snapshot da versão usada. Ela foi preservada sem finalização "
                "para evitar calcular o histórico com conteúdo ou gabarito atuais."
            )
        versoes = {item.questao_id: item.questao_versao for item in itens}
        conteudos = {qid: json.loads(version.conteudo_json) for qid, version in versoes.items()}
        total_questoes = sum(
            normalizar_gabarito(conteudo.get("gabarito"), conteudo.get("tipo")) != "Anulada"
            for conteudo in conteudos.values()
        )
    with db.atomic():
        for q_id, resposta in respostas_usuario.items():
            if tentativa.prova_id:
                version = versoes[q_id]
                conteudo = conteudos[q_id]
                gabarito = conteudo.get("gabarito")
                tipo = conteudo.get("tipo")
                enunciado = conteudo.get("enunciado")
            else:
                questao = Questao.get_by_id(q_id)
                version = _ultima_versao_questao(q_id)
                conteudo = _questao_dict(questao)
                gabarito, tipo, enunciado = questao.gabarito, questao.tipo, questao.enunciado
            if normalizar_gabarito(gabarito, tipo) == "Anulada":
                continue
            resposta_normalizada = normalizar_gabarito(resposta, tipo)
            gabarito_normalizado = normalizar_gabarito(gabarito, tipo)
            correta = gabarito_normalizado is not None and resposta_normalizada == gabarito_normalizado
            total_acertos += int(correta)
            if not correta:
                detalhes_erradas.append({"id": q_id, "enunciado": enunciado, "marcada": resposta, "correta": gabarito, "questao_versao_id": version.id if version else None})
            Resposta.create(tentativa=tentativa_id, questao=q_id, questao_versao=version.id if version else None, resposta_marcada=resposta_normalizada, correta=correta)
        ProgressoTentativa.delete().where(ProgressoTentativa.tentativa == tentativa_id).execute()
        nota = (total_acertos / total_questoes * 100) if total_questoes else 0
        Tentativa.update(finalizada_em=datetime.datetime.now(), total_acertos=total_acertos, nota=nota, tempo_gasto_seg=tempo_gasto_seg).where(Tentativa.id == tentativa_id).execute()
    return {"acertos": total_acertos, "total": total_questoes, "nota": nota, "erradas": detalhes_erradas}


@_verificar_fontes_em_lote
def buscar_questoes_da_prova(prova_id: int) -> list[dict]:
    init_db()
    query = (ProvaQuestao.select(ProvaQuestao, Questao)
             .join(Questao).where(ProvaQuestao.prova == prova_id)
             .order_by(ProvaQuestao.ordem))
    questoes = []
    for link in query:
        questao = link.questao
        data = _questao_dict(questao)
        version_id = link.questao_versao_id
        if version_id:
            version = QuestaoVersao.get_or_none(QuestaoVersao.id == version_id)
            if version:
                snapshot = json.loads(version.conteudo_json)
                data.update(snapshot)
                data["id"] = questao.id
                data["questao_versao_id"] = version.id
                data["apresentacao_fonte"] = _apresentacao_fonte(version)
        else:
            data["snapshot_legado_desconhecido"] = True
        questoes.append(data)
    prova = Prova.get_or_none(Prova.id == prova_id)
    try:
        configuracao = json.loads(prova.filtros or "{}") if prova else {}
    except (TypeError, json.JSONDecodeError):
        configuracao = {}
    fonte_id = configuracao.get("prova_cadastrada_id")
    if fonte_id:
        fonte = ProvaCadastrada.get_or_none(ProvaCadastrada.id == fonte_id)
        instrucoes = fonte.instrucoes_prova if fonte else None
        for questao in questoes:
            questao["instrucoes_prova"] = instrucoes or ""
    return questoes


def desempenho_por_disciplina() -> list[dict]:
    init_db()
    total = fn.COUNT(Resposta.id).alias("total_respondidas")
    acertos = fn.SUM(Case(None, ((Resposta.correta == True, 1),), 0)).alias("total_acertos")
    query = (Questao.select(Questao.disciplina, total, acertos)
             .join(Resposta, on=(Resposta.questao == Questao.id))
             .where(Questao.disciplina.is_null(False), Questao.disciplina != "")
             .group_by(Questao.disciplina))
    rows = []
    for row in query:
        total_respondidas = row.total_respondidas or 0
        total_acertos = row.total_acertos or 0
        rows.append({"disciplina": row.disciplina, "total_respondidas": total_respondidas, "total_acertos": total_acertos, "percentual": total_acertos / total_respondidas * 100 if total_respondidas else 0})
    return rows


def evolucao_notas() -> list[dict]:
    init_db()
    query = Tentativa.select(Tentativa.iniciada_em, Tentativa.nota).where(Tentativa.finalizada_em.is_null(False)).order_by(Tentativa.iniciada_em)
    return [{"iniciada_em": _legacy_value(row.iniciada_em), "nota": row.nota} for row in query]


def questoes_mais_erradas(limite=10) -> list[dict]:
    init_db()
    erros = fn.COUNT(Resposta.id).alias("erros")
    query = (Questao.select(Questao.id, Questao.enunciado, erros)
             .join(Resposta, on=(Resposta.questao == Questao.id))
             .where(Resposta.correta == False)
             .group_by(Questao.id, Questao.enunciado)
             .order_by(erros.desc()).limit(limite))
    return [{"id": row.id, "enunciado": row.enunciado, "erros": row.erros} for row in query]


def resumo_dashboard() -> dict:
    """Retorna os indicadores usados pela página inicial em uma única API."""
    init_db()
    total_questoes = Questao.select().where(Questao.ativa == True).count()
    total_provas = Prova.select().count()
    provas_realizadas = Tentativa.select().where(Tentativa.finalizada_em.is_null(False)).count()
    total_respostas = Resposta.select().count()
    total_acertos = Resposta.select().where(Resposta.correta == True).count()
    revisoes_hoje = RevisaoEspacada.select().where(RevisaoEspacada.proxima_revisao <= datetime.date.today()).count()
    return {
        "total_questoes": total_questoes,
        "total_provas": total_provas,
        "provas_realizadas": provas_realizadas,
        "total_respostas": total_respostas,
        "total_acertos": total_acertos,
        "taxa_acerto": total_acertos / total_respostas * 100 if total_respostas else 0,
        "revisoes_hoje": revisoes_hoje,
    }
