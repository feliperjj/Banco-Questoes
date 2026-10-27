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
    numero_oficial = IntegerField(null=True)
    enunciado = TextField()
    texto_apoio = TextField(null=True)
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
    imagem_path = TextField(null=True)
    ativa = BooleanField(default=True)
    criada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "questoes"


class DocumentoFonte(BaseModel):
    """Arquivo original rastreado por conteúdo, sem confiar no nome para identificá-lo."""

    id = AutoField()
    sha256 = TextField(null=True, unique=True, index=True)
    tipo = TextField(default="desconhecido")
    identificacao_prova = TextField(null=True)
    cargo = TextField(null=True)
    ano = IntegerField(null=True)
    versao = TextField(null=True)
    localizacao = TextField(null=True)
    disponibilidade = TextField(default="desconhecida")
    criado_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "documentos_fonte"


class ExecucaoExtracao(BaseModel):
    id = AutoField()
    documento_fonte = ForeignKeyField(DocumentoFonte, column_name="documento_fonte_id", backref="extracoes", null=True)
    extrator = TextField()
    versao_extrator = TextField(null=True)
    perfil = TextField(null=True)
    versao_perfil = TextField(null=True)
    parametros_json = TextField(default="{}")
    diagnosticos_json = TextField(default="[]")
    executada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "execucoes_extracao"


class QuestaoVersao(BaseModel):
    id = AutoField()
    questao = ForeignKeyField(Questao, column_name="questao_id", backref="versoes")
    numero_versao = IntegerField()
    hash_conteudo = TextField()
    conteudo_json = TextField()
    documento_fonte = ForeignKeyField(DocumentoFonte, column_name="documento_fonte_id", backref="versoes_questao", null=True)
    execucao_extracao = ForeignKeyField(ExecucaoExtracao, column_name="execucao_extracao_id", backref="versoes_questao", null=True)
    revisao_conteudo = TextField(default="pendente")
    revisao_gabarito = TextField(default="desconhecido")
    criada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "questoes_versoes"
        indexes = ((('questao', 'numero_versao'), True),)


class EvidenciaQuestao(BaseModel):
    id = AutoField()
    questao_versao = ForeignKeyField(QuestaoVersao, column_name="questao_versao_id", backref="evidencias")
    documento_fonte = ForeignKeyField(DocumentoFonte, column_name="documento_fonte_id", backref="evidencias")
    parte = TextField()
    escopo_json = TextField(default="{}")
    pagina = IntegerField(null=True)
    identificador_documento = TextField(null=True)
    x0 = FloatField(null=True)
    y0 = FloatField(null=True)
    x1 = FloatField(null=True)
    y1 = FloatField(null=True)
    sistema_coordenadas = TextField(null=True)
    largura_pagina = FloatField(null=True)
    altura_pagina = FloatField(null=True)
    rotacao_pagina = IntegerField(null=True)
    texto_evidencia = TextField(null=True)

    class Meta:
        table_name = "evidencias_questao"


class RevisaoConteudo(BaseModel):
    id = AutoField()
    questao_versao = ForeignKeyField(QuestaoVersao, column_name="questao_versao_id", backref="revisoes_conteudo")
    decisao = TextField()
    responsavel_declarado = TextField(null=True)
    justificativa = TextField()
    evidencia_json = TextField(default="[]")
    criada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "revisoes_conteudo"


class RevisaoGabarito(BaseModel):
    id = AutoField()
    questao_versao = ForeignKeyField(QuestaoVersao, column_name="questao_versao_id", backref="revisoes_gabarito")
    gabarito = TextField(null=True)
    decisao = TextField()
    responsavel_declarado = TextField(null=True)
    justificativa = TextField()
    evidencia_json = TextField(default="[]")
    criada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "revisoes_gabarito"


class ResolucaoDiagnostico(BaseModel):
    id = AutoField()
    questao_versao = ForeignKeyField(QuestaoVersao, column_name="questao_versao_id", backref="resolucoes_diagnostico")
    codigo = TextField()
    versao_regra = TextField()
    decisao = TextField()
    responsavel_declarado = TextField()
    justificativa = TextField()
    evidencia_json = TextField(default="[]")
    fingerprint_evidencias = TextField()
    criada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "resolucoes_diagnostico"


class ValidacaoAutomatica(BaseModel):
    """Certificado imutável de validação documental, sem autoria humana."""

    id = AutoField()
    questao_versao = ForeignKeyField(QuestaoVersao, column_name="questao_versao_id", backref="validacoes_automaticas")
    versao_regra = TextField()
    hash_snapshot = TextField()
    fingerprint_evidencias = TextField()
    evidencia_json = TextField(default="[]")
    manifesto_json = TextField(default="{}")
    criada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "validacoes_automaticas"
        indexes = ((('questao_versao', 'versao_regra', 'hash_snapshot', 'fingerprint_evidencias'), True),)


class Alternativa(BaseModel):
    id = AutoField()
    questao = ForeignKeyField(Questao, column_name="questao_id", backref="alternativas")
    letra = TextField()
    texto = TextField()

    class Meta:
        table_name = "alternativas"


class ProvaCadastrada(BaseModel):
    """Prova de origem importada e reutilizável na geração de simulados."""

    id = AutoField()
    nome = TextField()
    arquivo_questoes = TextField(null=True)
    arquivo_gabarito = TextField(null=True)
    documento_fonte_questoes = ForeignKeyField(DocumentoFonte, column_name="documento_fonte_questoes_id", backref="provas_questoes", null=True)
    documento_fonte_gabarito = ForeignKeyField(DocumentoFonte, column_name="documento_fonte_gabarito_id", backref="provas_gabarito", null=True)
    instrucoes_prova = TextField(null=True)
    ativa = BooleanField(default=True)
    criada_em = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "provas_cadastradas"


class ProvaCadastradaQuestao(BaseModel):
    prova_cadastrada = ForeignKeyField(
        ProvaCadastrada,
        column_name="prova_cadastrada_id",
        backref="questoes_vinculadas",
    )
    questao = ForeignKeyField(Questao, column_name="questao_id", backref="provas_cadastradas")
    questao_versao = ForeignKeyField(QuestaoVersao, column_name="questao_versao_id", backref="provas_cadastradas", null=True)
    ordem = IntegerField()

    class Meta:
        table_name = "prova_cadastrada_questoes"
        primary_key = CompositeKey("prova_cadastrada", "questao")


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
    questao_versao = ForeignKeyField(QuestaoVersao, column_name="questao_versao_id", backref="composicoes_prova", null=True)
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
    questao_versao = ForeignKeyField(QuestaoVersao, column_name="questao_versao_id", backref="respostas", null=True)
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


class ProgressoTentativa(BaseModel):
    tentativa = ForeignKeyField(Tentativa, primary_key=True, backref="progresso")
    respostas = TextField(default="{}")
    indice = IntegerField(default=0)
    tempo_seg = IntegerField(default=0)

    class Meta:
        table_name = "progresso_tentativas"


ALL_MODELS = [
    Questao,
    DocumentoFonte,
    ExecucaoExtracao,
    QuestaoVersao,
    EvidenciaQuestao,
    RevisaoConteudo,
    RevisaoGabarito,
    ResolucaoDiagnostico,
    ValidacaoAutomatica,
    Alternativa,
    ProvaCadastrada,
    ProvaCadastradaQuestao,
    Prova,
    ProvaQuestao,
    Tentativa,
    Resposta,
    RevisaoEspacada,
    ProgressoTentativa,
]
