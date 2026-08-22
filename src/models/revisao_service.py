import datetime

from src.db.database import db, init_db
from src.db.models import Alternativa, Questao, RevisaoEspacada


def registrar_erro(questao_id: int):
    init_db()
    hoje = datetime.date.today()
    with db.atomic():
        registro, criado = RevisaoEspacada.get_or_create(
            questao=questao_id,
            defaults={"proxima_revisao": hoje, "intervalo_dias": 1, "fator_facilidade": 2.5, "acertos_seguidos": 0},
        )
        if not criado:
            registro.proxima_revisao = hoje
            registro.intervalo_dias = 1
            registro.fator_facilidade = max(1.3, registro.fator_facilidade - 0.2)
            registro.acertos_seguidos = 0
            registro.save()


def processar_revisao(questao_id: int, acertou: bool):
    init_db()
    if not acertou:
        registrar_erro(questao_id)
        return
    hoje = datetime.date.today()
    with db.atomic():
        registro, _ = RevisaoEspacada.get_or_create(
            questao=questao_id,
            defaults={"proxima_revisao": hoje, "intervalo_dias": 1, "fator_facilidade": 2.5, "acertos_seguidos": 0},
        )
        acertos = registro.acertos_seguidos + 1
        if acertos == 1:
            intervalo = 1
        elif acertos == 2:
            intervalo = 6
        else:
            intervalo = round(registro.intervalo_dias * registro.fator_facilidade)
        registro.acertos_seguidos = acertos
        registro.intervalo_dias = intervalo
        registro.fator_facilidade = min(2.5, registro.fator_facilidade + 0.1)
        registro.proxima_revisao = hoje + datetime.timedelta(days=intervalo)
        registro.save()


def questoes_para_revisar_hoje() -> list[dict]:
    init_db()
    query = (Questao.select(Questao, RevisaoEspacada)
             .join(RevisaoEspacada, attr="revisao")
             .where(RevisaoEspacada.proxima_revisao <= datetime.date.today()))
    questoes = []
    for questao in query:
        revisao = questao.revisao
        dados = {"id": questao.id, "enunciado": questao.enunciado, "tipo": questao.tipo, "gabarito": questao.gabarito, "proxima_revisao": str(revisao.proxima_revisao)}
        if questao.tipo == "multipla_escolha":
            dados["alternativas"] = [{"letra": alt.letra, "texto": alt.texto} for alt in Alternativa.select().where(Alternativa.questao == questao.id)]
        questoes.append(dados)
    return questoes
