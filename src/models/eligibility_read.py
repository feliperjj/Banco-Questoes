"""Prefetch para listas/contagens; nunca encapsula gravações nem persiste decisões.

O snapshot é descartado ao terminar a leitura. A geração e o início de uma
tentativa continuam verificando as fontes atuais pela autoridade do domínio.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from src.db.models import (Questao, Alternativa, QuestaoVersao, DocumentoFonte,
                           EvidenciaQuestao, RevisaoConteudo, RevisaoGabarito,
                           ValidacaoAutomatica, ResolucaoDiagnostico)

_snapshot = ContextVar('eligibility_read_snapshot', default=None)


@contextmanager
def eligibility_read():
    if _snapshot.get() is not None:
        yield
        return
    latest_versions = {}
    for version in QuestaoVersao.select().order_by(QuestaoVersao.questao, QuestaoVersao.numero_versao):
        latest_versions[version.questao_id] = version
    versions = list(latest_versions.values())
    ids = [v.id for v in versions]
    data = {'latest': {v.questao_id: v for v in versions},
            QuestaoVersao: {v.id: v for v in versions},
            Questao: {v.id: v for v in Questao.select()},
            DocumentoFonte: {v.id: v for v in DocumentoFonte.select()}}
    data[Alternativa] = {}
    for row in Alternativa.select().order_by(Alternativa.letra):
        data[Alternativa].setdefault(row.questao_id, []).append(row)
    for model in (EvidenciaQuestao, RevisaoConteudo, RevisaoGabarito,
                  ValidacaoAutomatica, ResolucaoDiagnostico):
        groups = {i: [] for i in ids}
        for row in model.select().where(model.questao_versao.in_(ids)).order_by(model.id):
            groups[row.questao_versao_id].append(row)
        data[model] = groups
    data['evidence_ids'] = {row.id: row for group in data[EvidenciaQuestao].values() for row in group}
    token = _snapshot.set(data)
    try:
        yield
    finally:
        _snapshot.reset(token)


def record(model, ident):
    data = _snapshot.get()
    if data is not None and model in (Questao, DocumentoFonte, QuestaoVersao) and ident in data[model]:
        return data[model][ident]
    return model.get_or_none(model.id == ident) if model == QuestaoVersao else model.get_by_id(ident)


def version_rows(model, ident):
    data = _snapshot.get()
    if data is not None and ident in data[QuestaoVersao]:
        return data[model][ident]
    return None


def latest(question_id):
    data = _snapshot.get()
    return data['latest'].get(question_id) if data is not None else None


def alternatives(question_id):
    data = _snapshot.get()
    return data[Alternativa].get(question_id, []) if data is not None else None


def evidence_ids(ids):
    data = _snapshot.get()
    if data is None:
        return None
    found = [data['evidence_ids'][i] for i in ids if i in data['evidence_ids']]
    missing = [i for i in ids if i not in data['evidence_ids']]
    if missing:
        found.extend(EvidenciaQuestao.select().where(EvidenciaQuestao.id.in_(missing)))
    return found


def review(model, ident, *, non_pending=False, by_date=False):
    rows = version_rows(model, ident)
    if rows is None:
        query = model.select().where(model.questao_versao == ident)
        if non_pending:
            query = query.where(model.decisao != 'pendente')
        return query.order_by(model.criada_em.desc(), model.id.desc()).first() if by_date else query.order_by(model.id.desc()).first()
    rows = [r for r in rows if not non_pending or r.decisao != 'pendente']
    return max(rows, key=lambda r: (r.criada_em, r.id) if by_date else r.id, default=None)


def resolution(version_id, code, rule, fingerprint):
    rows = version_rows(ResolucaoDiagnostico, version_id)
    if rows is None:
        return (ResolucaoDiagnostico.select().where(
            (ResolucaoDiagnostico.questao_versao == version_id)
            & (ResolucaoDiagnostico.codigo == code)
            & (ResolucaoDiagnostico.versao_regra == rule)
            & (ResolucaoDiagnostico.fingerprint_evidencias == fingerprint)
        ).order_by(ResolucaoDiagnostico.criada_em.desc(), ResolucaoDiagnostico.id.desc()).first())
    return max((r for r in rows if r.codigo == code and r.versao_regra == rule
                and r.fingerprint_evidencias == fingerprint), key=lambda r: (r.criada_em, r.id), default=None)
