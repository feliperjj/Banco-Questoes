import datetime

from peewee import (
    AutoField, BooleanField, CompositeKey, DateField, DateTimeField,
    ForeignKeyField, IntegerField, Model, TextField, FloatField,
)

from src.db.database import db


class BaseModel(Model):
    class Meta:
        database = db


class Questao(BaseModel):
    id = AutoField()
    enunciado = TextField()
    tipo = TextField()
    disciplina = TextField(null=True)
    topico = TextField(null=True)
    banca = TextField(null=True)
    ano = IntegerField(null=True)
    cargo = TextField(null=True)
    orgao = TextField(null=True)
    dificuldade = TextField(null=True)
    gabarito = TextField(null=True)
    comentario = TextField(null=True)
    ativa = BooleanField(default=True)
    criada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "questoes"


class Alternativa(BaseModel):
    id = AutoField()
    questao = ForeignKeyField(Questao, column_name="questao_id", backref="alternativas")
    letra = TextField()
    texto = TextField()

    class Meta:
        table_name = "alternativas"


class Prova(BaseModel):
    id = AutoField()
    nome = TextField()
    filtros = TextField(null=True)
    criada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "provas"


class ProvaQuestao(BaseModel):
    prova = ForeignKeyField(Prova, column_name="prova_id", backref="prova_questoes")
    questao = ForeignKeyField(Questao, column_name="questao_id", backref="prova_questoes")
    ordem = IntegerField(null=True)

    class Meta:
        table_name = "prova_questoes"
        primary_key = CompositeKey("prova", "questao")


class Tentativa(BaseModel):
    id = AutoField()
    prova = ForeignKeyField(Prova, column_name="prova_id", backref="tentativas", null=True)
    iniciada_em = DateTimeField(default=datetime.datetime.now)
    finalizada_em = DateTimeField(null=True)
    total_acertos = IntegerField(null=True)
    nota = FloatField(null=True)
    tempo_gasto_seg = IntegerField(null=True)

    class Meta:
        table_name = "tentativas"


class Resposta(BaseModel):
    id = AutoField()
    tentativa = ForeignKeyField(Tentativa, column_name="tentativa_id", backref="respostas", null=True)
    questao = ForeignKeyField(Questao, column_name="questao_id", backref="respostas", null=True)
    resposta_marcada = TextField(null=True)
    correta = BooleanField(null=True)
    tempo_resposta_seg = IntegerField(null=True)

    class Meta:
        table_name = "respostas"


class RevisaoEspacada(BaseModel):
    questao = ForeignKeyField(Questao, column_name="questao_id", backref="revisao_espacada", primary_key=True)
    proxima_revisao = DateField(null=True)
    intervalo_dias = IntegerField(null=True)
    fator_facilidade = FloatField(default=2.5)
    acertos_seguidos = IntegerField(default=0)

    class Meta:
        table_name = "revisao_espacada"


ALL_MODELS = [Questao, Alternativa, Prova, ProvaQuestao, Tentativa, Resposta, RevisaoEspacada]
