import json
import random

import datetime

from peewee import Case, JOIN, fn, prefetch

from src.db.database import db, init_db
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
)
from src.importador.validacao import gabarito_valido, normalizar_gabarito, problemas_estrutura


CAMPOS_QUESTAO = ("enunciado", "tipo", "disciplina", "topico", "banca", "ano", "cargo", "orgao", "dificuldade", "gabarito", "comentario")
GABARITOS_AVALIAVEIS = ("A", "B", "C", "D", "E", "Certo", "Errado")


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


def _criar_questao_sem_transacao(dados: dict) -> int:
    questao = Questao.create(**{campo: dados.get(campo) for campo in CAMPOS_QUESTAO})
    if questao.tipo == "multipla_escolha":
        for alt in dados.get("alternativas") or []:
            Alternativa.create(questao=questao.id, letra=alt["letra"], texto=alt["texto"])
    return questao.id


def criar_questao(dados: dict) -> int:
    init_db()
    with db.atomic():
        return _criar_questao_sem_transacao(dados)


def criar_questoes_em_lote(lista_dados: list[dict]) -> list[int]:
    init_db()
    ids = []
    with db.atomic():
        for dados in lista_dados:
            ids.append(_criar_questao_sem_transacao(dados))
    return ids


def atualizar_questao(q_id: int, dados: dict):
    init_db()
    with db.atomic():
        questao = Questao.get_by_id(q_id)
        for campo in CAMPOS_QUESTAO:
            if campo in dados:
                setattr(questao, campo, dados[campo])
        questao.save()
        if questao.tipo == "multipla_escolha" and "alternativas" in dados:
            Alternativa.delete().where(Alternativa.questao == q_id).execute()
            for alt in dados["alternativas"]:
                Alternativa.create(questao=q_id, letra=alt["letra"], texto=alt["texto"])
        elif questao.tipo != "multipla_escolha":
            # Alternativas não fazem parte de questões certo/errado. Remova
            # resíduos ao trocar o tipo para evitar que reapareçam depois.
            Alternativa.delete().where(Alternativa.questao == q_id).execute()


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
        if not problemas_estrutura(dados):
            validos.append(questao.id)
    return query.where(Questao.id.in_(validos))


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
            ProvaQuestao.create(prova=prova.id, questao=q_id, ordem=ordem)
    return prova.id


def criar_prova_cadastrada(
    nome: str,
    lista_dados: list[dict],
    arquivo_questoes: str | None = None,
    arquivo_gabarito: str | None = None,
) -> int:
    """Salva um lote importado como uma prova de origem reutilizável."""
    init_db()
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome da prova cadastrada.")
    if not lista_dados:
        raise ValueError("A prova precisa possuir ao menos uma questão.")
    with db.atomic():
        prova = ProvaCadastrada.create(
            nome=nome,
            arquivo_questoes=arquivo_questoes or None,
            arquivo_gabarito=arquivo_gabarito or None,
        )
        for ordem, dados in enumerate(lista_dados, 1):
            questao_id = dados.get("_questao_id") or _criar_questao_sem_transacao(dados)
            if not Questao.get_or_none(Questao.id == questao_id):
                raise ValueError("A questão revisada não existe mais no banco.")
            ProvaCadastradaQuestao.create(
                prova_cadastrada=prova.id,
                questao=questao_id,
                ordem=ordem,
            )
    return prova.id


def listar_provas_cadastradas() -> list[dict]:
    """Lista provas de origem e indica se já podem gerar uma nova prova."""
    init_db()
    total = fn.COUNT(ProvaCadastradaQuestao.questao).alias("qtd_questoes")
    avaliaveis = fn.SUM(
        Case(
            None,
            (
                (
                    (Questao.ativa == True)
                    & Questao.gabarito.in_(GABARITOS_AVALIAVEIS),
                    1,
                ),
            ),
            0,
        )
    ).alias("qtd_avaliaveis")
    query = (
        ProvaCadastrada.select(
            ProvaCadastrada.id,
            ProvaCadastrada.nome,
            ProvaCadastrada.arquivo_questoes,
            ProvaCadastrada.arquivo_gabarito,
            ProvaCadastrada.criada_em,
            total,
            avaliaveis,
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
        qtd_avaliaveis = int(prova.qtd_avaliaveis or 0)
        provas.append(
            {
                "id": prova.id,
                "nome": prova.nome,
                "arquivo_questoes": prova.arquivo_questoes,
                "arquivo_gabarito": prova.arquivo_gabarito,
                "criada_em": _legacy_value(prova.criada_em),
                "qtd_questoes": qtd,
                "qtd_avaliaveis": qtd_avaliaveis,
                "pronta": qtd > 0 and qtd == qtd_avaliaveis,
            }
        )
    return provas


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

        avaliaveis = sum(q.gabarito in GABARITOS_AVALIAVEIS for q in questoes_lote)
        questao_ids = [q.id for q in questoes_lote]
        lotes.append(
            {
                "id": questao_ids[0],
                "origem_tipo": "lote_importado",
                "nome": " · ".join(partes_nome),
                "qtd_questoes": len(questoes_lote),
                "qtd_avaliaveis": avaliaveis,
                "pronta": len(questoes_lote) == avaliaveis,
                "questao_ids": questao_ids,
                "criada_em": _legacy_value(questoes_lote[0].criada_em),
            }
        )
    return list(reversed(lotes))


def criar_prova_a_partir_de_questoes(
    nome: str, questao_ids: list[int], tempo_limite_min: int = 0
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
        if not por_id[qid].ativa or por_id[qid].gabarito not in GABARITOS_AVALIAVEIS
    ]
    if indisponiveis:
        raise ValueError(
            f"A prova importada possui {len(indisponiveis)} questão(ões) "
            "sem gabarito avaliável ou inativas."
        )
    configuracao = {
        "modo": "prova_importada_lote",
        "lote_importacao_id": ids[0],
        "_tempo_limite_min": max(0, int(tempo_limite_min or 0)),
    }
    with db.atomic():
        prova = Prova.create(nome=nome, filtros=json.dumps(configuracao))
        for ordem, qid in enumerate(ids, 1):
            ProvaQuestao.create(prova=prova.id, questao=qid, ordem=ordem)
    return prova.id


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
        qtd_avaliaveis = (
            Questao.select()
            .join(ProvaQuestao)
            .where(
                (ProvaQuestao.prova == prova.id)
                & (Questao.ativa == True)
                & Questao.gabarito.in_(GABARITOS_AVALIAVEIS)
            )
            .count()
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
        if not item.questao.ativa or item.questao.gabarito not in GABARITOS_AVALIAVEIS
    ]
    if indisponiveis:
        raise ValueError(
            "A prova cadastrada possui "
            f"{len(indisponiveis)} questão(ões) sem gabarito avaliável ou inativas. "
            "Corrija a importação antes de utilizá-la."
        )
    configuracao = {
        "modo": "prova_cadastrada",
        "prova_cadastrada_id": fonte.id,
        "_tempo_limite_min": max(0, int(tempo_limite_min or 0)),
    }
    with db.atomic():
        prova = Prova.create(nome=nome, filtros=json.dumps(configuracao))
        for item in vinculadas:
            ProvaQuestao.create(
                prova=prova.id,
                questao=item.questao_id,
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
        if not item.questao.ativa or item.questao.gabarito not in GABARITOS_AVALIAVEIS
    ]
    if indisponiveis:
        raise ValueError(
            "A prova existente possui "
            f"{len(indisponiveis)} questão(ões) sem gabarito avaliável ou inativas."
        )
    configuracao = {
        "modo": "prova_existente",
        "prova_existente_id": fonte.id,
        "_tempo_limite_min": max(0, int(tempo_limite_min or 0)),
    }
    with db.atomic():
        prova = Prova.create(nome=nome, filtros=json.dumps(configuracao))
        for item in vinculadas:
            ProvaQuestao.create(
                prova=prova.id,
                questao=item.questao_id,
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
        questoes_da_prova = {row.questao_id for row in ProvaQuestao.select(ProvaQuestao.questao).where(ProvaQuestao.prova == tentativa.prova_id)}
        invalidas = set(respostas_usuario) - questoes_da_prova
        if invalidas:
            raise ValueError("A tentativa contém respostas para questões que não pertencem à prova.")
        total_questoes = (ProvaQuestao.select(ProvaQuestao, Questao)
                           .join(Questao)
                           .where((ProvaQuestao.prova == tentativa.prova_id) & (Questao.gabarito != "Anulada"))
                           .count())
    with db.atomic():
        for q_id, resposta in respostas_usuario.items():
            questao = Questao.get_by_id(q_id)
            if questao.gabarito == "Anulada":
                continue
            resposta_normalizada = normalizar_gabarito(resposta, questao.tipo)
            gabarito_normalizado = normalizar_gabarito(questao.gabarito, questao.tipo)
            correta = gabarito_normalizado is not None and resposta_normalizada == gabarito_normalizado
            total_acertos += int(correta)
            if not correta:
                detalhes_erradas.append({"id": q_id, "enunciado": questao.enunciado, "marcada": resposta, "correta": questao.gabarito})
            Resposta.create(tentativa=tentativa_id, questao=q_id, resposta_marcada=resposta_normalizada, correta=correta)
        ProgressoTentativa.delete().where(ProgressoTentativa.tentativa == tentativa_id).execute()
        nota = (total_acertos / total_questoes * 100) if total_questoes else 0
        Tentativa.update(finalizada_em=datetime.datetime.now(), total_acertos=total_acertos, nota=nota, tempo_gasto_seg=tempo_gasto_seg).where(Tentativa.id == tentativa_id).execute()
    return {"acertos": total_acertos, "total": total_questoes, "nota": nota, "erradas": detalhes_erradas}


def buscar_questoes_da_prova(prova_id: int) -> list[dict]:
    init_db()
    query = Questao.select().join(ProvaQuestao).where(ProvaQuestao.prova == prova_id).order_by(ProvaQuestao.ordem)
    return [_questao_dict(questao) for questao in prefetch(query, Alternativa)]


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
