"""Ações assistidas do funil, sem aprovação implícita de conteúdo ou gabarito."""
import json
import math
from io import BytesIO

from src.db.database import db, init_db
from src.db.models import DocumentoFonte, QuestaoVersao
from src.models import questoes_repo as repo
from src.models.provenance_service import (
    register_extraction, source_pdf, verify_source,
)
from src.importador.validacao import normalizar_gabarito


FIELD_LABELS = {
    'enunciado': 'Enunciado', 'texto_apoio': 'Texto de apoio',
    'alternativas': 'Alternativas', 'gabarito': 'Gabarito',
    'numero_oficial': 'Número oficial',
}

STAGE_LABELS = {
    'identidade_fonte': 'Conferir fonte e identidade', 'identidade': 'Conferir identidade',
    'numeracao': 'Identificar número oficial', 'estrutura': 'Corrigir estrutura',
    'revisao_alertas': 'Conferir alertas', 'revisao_conteudo': 'Conferir conteúdo',
    'confirmacao_gabarito': 'Confirmar gabarito', 'liberada': 'Liberada', 'bloqueada': 'Bloqueada',
}


def render_source_region(source_id, page_number, bounds):
    """Renderiza só o recorte íntegro para consulta, inclusive PDFs sem texto."""
    if not verify_source(source_id)['integro']:
        raise ValueError('A fonte está ausente ou alterada. Localize o PDF original íntegro.')
    from src.importador.pdf_render import render_image
    source = DocumentoFonte.get_by_id(source_id)
    image = render_image(source.localizacao, page_number, bounds, scale=1.5)
    if not verify_source(source_id)['integro']:
        raise ValueError('A fonte mudou durante a renderização. Reabra o original.')
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def diagnostic_target(item):
    """Escolhe a área da conferência; nunca transforma suspeita em aprovação."""
    code = item['codigo']
    if 'numeracao' in code or item.get('etapa') == 'numeracao':
        return 'numero_oficial'
    if code in {'alternativas_invalidas', 'alternativas_possivelmente_fundidas'}:
        return 'alternativas'
    if ('gabarito' in code or item.get('parte') == 'gabarito'
            or item.get('etapa') in {'associacao_gabarito', 'confirmacao_gabarito'}):
        return 'gabarito'
    if item.get('parte') == 'contexto':
        return 'texto_apoio'
    return 'enunciado'


def read_source_region(source_id, page_number, bounds):
    """Relê uma página/recorte selecionado e devolve proposta sem gravar dados."""
    if not verify_source(source_id)['integro']:
        raise ValueError('A fonte está ausente ou alterada. Localize o PDF original íntegro.')
    source = DocumentoFonte.get_by_id(source_id)
    bounds = tuple(float(v) for v in bounds)
    if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
        raise ValueError('Informe quatro coordenadas válidas para o recorte.')
    with source_pdf(source.localizacao) as pdf:
        if not 1 <= page_number <= len(pdf.pages):
            raise ValueError('A página selecionada não existe neste PDF.')
        page = pdf.pages[page_number - 1]
        x0, y0, x1, y1 = bounds
        if not (0 <= x0 < x1 <= float(page.width) and 0 <= y0 < y1 <= float(page.height)):
            raise ValueError('O recorte deve ficar dentro da página e ter largura e altura positivas.')
        text = page.crop(bounds).extract_text() or ''
    if not verify_source(source_id)['integro']:
        raise ValueError('A fonte mudou durante a leitura. Reabra o original e tente novamente.')
    if not text.strip():
        raise ValueError('O recorte não contém texto extraível. Confira a imagem e faça a correção manual.')
    return {'text': text, 'source_id': source_id, 'sha256': source.sha256,
            'page': page_number, 'bounds': list(bounds)}


def _local_review_source(version_id, source_id):
    """Snapshot da versão e da fonte; consulta não registra aprovações."""
    from src.models.provenance_service import _version_is_current
    version = QuestaoVersao.get_by_id(version_id)
    latest = repo.ultima_versao(version.questao_id)
    if latest.id != version_id or not _version_is_current(version) or not repo.obter_questao(version.questao_id)['ativa']:
        raise ValueError('A questão mudou. Atualize a conferência antes de analisar.')
    if version.documento_fonte_id != source_id:
        raise ValueError('Selecione a fonte de conteúdo vinculada a esta versão.')
    source = DocumentoFonte.get_by_id(source_id)
    if not verify_source(source_id)['integro']:
        raise ValueError('A fonte está ausente ou alterada. Reabra o original íntegro.')
    return version, source


def suggest_source_region(version_id, field, source_id, page_number, bounds, *,
                          letter=None, cancel_event=None, runtime=None, cache_dir=None):
    """Assistência local para conteúdo; a aplicação continua sendo uma ação humana."""
    if field not in {'enunciado', 'texto_apoio', 'alternativas'}:
        raise ValueError('A IA auxilia a transcrição de conteúdo. Número e gabarito exigem conferência explícita da fonte.')
    version, source = _local_review_source(version_id, source_id)
    content = json.loads(version.conteudo_json)
    if field == 'alternativas':
        matches = [a for a in content.get('alternativas', []) if a['letra'] == letter]
        if len(matches) != 1:
            raise ValueError('Selecione uma alternativa existente nesta questão.')
        current_text = matches[0]['texto']
    else:
        if letter is not None:
            raise ValueError('Selecione o recorte do campo de texto, sem alternativa.')
        current_text = content.get(field) or ''
    from src.importador.ia_revisao import analyze_region
    result = analyze_region(source.localizacao, page_number, bounds, current_text,
        letter=letter, expected_sha256=source.sha256, cancel_event=cancel_event,
        runtime=runtime, cache_dir=cache_dir)
    _local_review_source(version_id, source_id)
    evidence = result.pop('region')
    result['evidence'] = evidence
    result['region'] = {'source_id': source_id, 'sha256': source.sha256,
                        'page': page_number, 'bounds': evidence['bounds']}
    result.update(version_id=version_id, field=field, letter=letter)
    return result


def remember_local_example(version_id, evidence, text, reviewer, confirmed, *, found=True):
    """Só a confirmação explícita de uma pessoa transforma um recorte em label."""
    version, source = _local_review_source(version_id, evidence['source_id'])
    if source.sha256 != evidence['source_sha256']:
        raise ValueError('A fonte mudou. Releia o original antes de guardar o exemplo.')
    from src.db.models import ProvaCadastradaQuestao
    proof_ids = sorted({item.prova_cadastrada_id for item in ProvaCadastradaQuestao.select().where(
        ProvaCadastradaQuestao.questao_id == version.questao_id)})
    if len(proof_ids) > 1:
        raise ValueError('A questão pertence a mais de uma prova. Defina um grupo comum na preparação do dataset antes de incluí-la.')
    group_id = f'prova-{proof_ids[0]}' if proof_ids else f'fonte-{source.sha256}'
    from src.models.ia_dataset import record_reviewed_example
    return record_reviewed_example(image_bytes=evidence['image_bytes'],
        source_sha256=source.sha256, group_id=group_id,
        page=evidence['page'], bounds=evidence['bounds'], text=text,
        reviewer=reviewer, confirmed=confirmed, found=found)


def apply_field_correction(version_id, field, value, *, region=None):
    """Edita um campo da versão atual dentro de transação, sem herdar decisões."""
    init_db()
    if field not in FIELD_LABELS:
        raise ValueError('Selecione um campo de conteúdo, numeração ou gabarito.')
    with db.atomic():
        version = QuestaoVersao.get_by_id(version_id)
        latest = repo.ultima_versao(version.questao_id)
        if latest.id != version_id or not repo.obter_questao(version.questao_id)['ativa']:
            raise ValueError('A questão mudou ou foi excluída. Atualize a conferência antes de corrigir.')
        content = json.loads(version.conteudo_json)
        # Também impede sobrescrever alterações feitas fora do fluxo de versões.
        from src.models.provenance_service import _version_is_current
        if not _version_is_current(version):
            raise ValueError('O conteúdo mudou. Atualize a conferência antes de corrigir.')
        if field == 'numero_oficial':
            if isinstance(value, bool) or not str(value).isdigit() or int(value) < 1:
                raise ValueError('Informe o número positivo que aparece no original.')
            value = int(value)
        elif field == 'gabarito':
            value = normalizar_gabarito(value, content['tipo'])
            allowed = {'A', 'B', 'C', 'D', 'E'} if content['tipo'] == 'multipla_escolha' else {'Certo', 'Errado'}
            if value not in allowed | {'Anulada'}:
                raise ValueError('Informe uma resposta compatível com o tipo da questão.')
            if content['tipo'] == 'multipla_escolha' and value != 'Anulada' and value not in {
                    a['letra'] for a in content.get('alternativas', [])}:
                raise ValueError('A alternativa indicada não existe nesta questão.')
        elif field == 'alternativas':
            if (not isinstance(value, list) or not value
                    or any(not isinstance(a, dict) or a.get('letra') not in {'A', 'B', 'C', 'D', 'E'}
                           or not a.get('texto', '').strip() for a in value)
                    or [a['letra'] for a in value] != list('ABCDE'[:len(value)])):
                raise ValueError('Informe alternativas A–E em sequência, sem repetições e com texto.')
            if content['tipo'] != 'multipla_escolha':
                raise ValueError('Esta questão é de certo ou errado.')
        else:
            value = str(value).strip()
            if field == 'enunciado' and not value:
                raise ValueError('O enunciado não pode ficar vazio.')
        if value == content.get(field):
            return version_id
        parameters = {'versao_base': version_id, 'campo': field}
        source_id = version.documento_fonte_id
        if region:
            source = DocumentoFonte.get_by_id(region['source_id'])
            if source.sha256 != region['sha256'] or not verify_source(source.id)['integro']:
                raise ValueError('A fonte da releitura mudou. Releia o recorte antes de salvar.')
            source_id = source.id
            parameters.update(pagina=region['page'], recorte=region['bounds'], sha256=region['sha256'])
        # Uma correção não pode reaproveitar a apresentação/certificado da
        # extração anterior como se descrevesse automaticamente o novo campo.
        extraction_id = register_extraction(
            source_id, extractor='releitura_parcial_assistida' if region else 'correcao_parcial_manual',
            extractor_version='1', parameters=parameters)
        repo.atualizar_questao(version.questao_id, {field: value}, extraction_id=extraction_id)
        return repo.ultima_versao(version.questao_id).id
