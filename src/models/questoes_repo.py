import json
import random

import datetime

from peewee import Case, JOIN, fn

from src.db.database import db, init_db
from src.db.models import Alternativa, Prova, ProvaQuestao, Questao, Resposta, RevisaoEspacada, Tentativa


def _as_dict(model, fields=None):
    names = fields or [field.name for field in model._meta.sorted_fields]
    return {name: _legacy_value(getattr(model, name)) for name in names}


def _legacy_value(value):
    """Mantém os textos de data que a antiga camada sqlite3 devolvia."""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return str(value)
    return value


def _questao_dict(questao):
    dados = _as_dict(questao)
    if questao.tipo == "multipla_escolha":
        dados["alternativas"] = [_as_dict(alt, ["letra", "texto"]) for alt in Alternativa.select().where(Alternativa.questao == questao.id)]
    return dados


def criar_questao(dados: dict) -> int:
    init_db()
    campos = ("enunciado", "tipo", "disciplina", "topico", "banca", "ano", "cargo", "orgao", "dificuldade", "gabarito", "comentario")
    with db.atomic():
        questao = Questao.create(**{campo: dados.get(campo) for campo in campos})
        if questao.tipo == "multipla_escolha" and "alternativas" in dados:
            for alt in dados["alternativas"]:
                Alternativa.create(questao=questao.id, letra=alt["letra"], texto=alt["texto"])
    return questao.id


def atualizar_questao(q_id: int, dados: dict):
    init_db()
    campos = ("enunciado", "tipo", "disciplina", "topico", "banca", "ano", "cargo", "orgao", "dificuldade", "gabarito", "comentario")
    with db.atomic():
        questao = Questao.get_by_id(q_id)
        for campo in campos:
            setattr(questao, campo, dados.get(campo))
        questao.save()
        if questao.tipo == "multipla_escolha" and "alternativas" in dados:
            Alternativa.delete().where(Alternativa.questao == q_id).execute()
            for alt in dados["alternativas"]:
                Alternativa.create(questao=q_id, letra=alt["letra"], texto=alt["texto"])


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
    if filtros and filtros.get("topico"):
        query = query.where(Questao.topico == filtros["topico"])
    return [_questao_dict(questao) for questao in query]


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


def criar_prova(nome: str, filtros: dict, quantidade: int, tempo_limite_min: int) -> int:
    init_db()
    query = Questao.select(Questao.id).where(Questao.ativa == True)
    if filtros and filtros.get("disciplina"):
        query = query.where(Questao.disciplina == filtros["disciplina"])
    if filtros and filtros.get("tipo"):
        query = query.where(Questao.tipo == filtros["tipo"])
    if filtros and filtros.get("topico"):
        query = query.where(Questao.topico == filtros["topico"])
    todas_questoes = [questao.id for questao in query]
    if not todas_questoes:
        return 0
    selecionadas = random.sample(todas_questoes, min(quantidade, len(todas_questoes)))
    with db.atomic():
        prova = Prova.create(nome=nome, filtros=json.dumps(filtros))
        for ordem, q_id in enumerate(selecionadas, 1):
            ProvaQuestao.create(prova=prova.id, questao=q_id, ordem=ordem)
    return prova.id


def listar_provas() -> list[dict]:
    init_db()
    qtd = fn.COUNT(ProvaQuestao.questao).alias("qtd_questoes")
    query = (Prova.select(Prova.id, Prova.nome, Prova.criada_em, qtd)
             .join(ProvaQuestao, join_type=JOIN.LEFT_OUTER)
             .group_by(Prova.id)
             .order_by(Prova.criada_em.desc()))
    return [{"id": p.id, "nome": p.nome, "criada_em": _legacy_value(p.criada_em), "qtd_questoes": p.qtd_questoes} for p in query]


def iniciar_tentativa(prova_id: int) -> int:
    init_db()
    return Tentativa.create(prova=prova_id).id


def finalizar_tentativa(tentativa_id: int, respostas_usuario: dict, tempo_gasto_seg: int) -> dict:
    init_db()
    total_acertos = 0
    total_questoes = len(respostas_usuario)
    detalhes_erradas = []
    with db.atomic():
        for q_id, resposta in respostas_usuario.items():
            questao = Questao.get_by_id(q_id)
            correta = resposta == questao.gabarito
            total_acertos += int(correta)
            if not correta:
                detalhes_erradas.append({"id": q_id, "enunciado": questao.enunciado, "marcada": resposta, "correta": questao.gabarito})
            Resposta.create(tentativa=tentativa_id, questao=q_id, resposta_marcada=resposta, correta=correta)
        nota = (total_acertos / total_questoes * 100) if total_questoes else 0
        Tentativa.update(finalizada_em=datetime.datetime.now(), total_acertos=total_acertos, nota=nota, tempo_gasto_seg=tempo_gasto_seg).where(Tentativa.id == tentativa_id).execute()
    return {"acertos": total_acertos, "total": total_questoes, "nota": nota, "erradas": detalhes_erradas}


def buscar_questoes_da_prova(prova_id: int) -> list[dict]:
    init_db()
    query = Questao.select().join(ProvaQuestao).where(ProvaQuestao.prova == prova_id).order_by(ProvaQuestao.ordem)
    return [_questao_dict(questao) for questao in query]


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
