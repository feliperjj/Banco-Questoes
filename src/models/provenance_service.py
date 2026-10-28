"""Rastreabilidade, versões imutáveis e decisões de revisão para questões."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from contextvars import ContextVar, Token
from contextlib import contextmanager

import pdfplumber
from peewee import IntegrityError

from src.db.database import db, init_db
from src.models import eligibility_read as read_batch
from src.db.models import (
    Alternativa,
    DocumentoFonte,
    EvidenciaQuestao,
    ExecucaoExtracao,
    Questao,
    QuestaoVersao,
    ResolucaoDiagnostico,
    RevisaoConteudo,
    RevisaoGabarito,
    ValidacaoAutomatica,
)
from src.config import ROOT_DIR, TEST_ROOT
from src.importador.validacao import normalizar_gabarito, problemas_estrutura


CONTEUDO_REVIEW = {"nao_revisado", "pendente", "conferido", "rejeitado"}
GABARITO_REVIEW = {"desconhecido", "preliminar", "definitivo_confirmado", "anulado", "conflitante"}
EVIDENCE_PARTS = {"conteudo", "contexto", "recurso_visual", "gabarito"}
CONTENT_PARTS = {"conteudo", "contexto", "recurso_visual"}
DIAGNOSTIC_RULE_VERSION = "funil-v2"
AUTOMATIC_RULE_VERSION = "pdf-geometrico-v1"
_source_verification_batch: ContextVar[dict | None] = ContextVar("source_verification_batch", default=None)
OBJECTIVE_STRUCTURE_PROBLEMS = {
    "Enunciado vazio", "Gabarito incompatível com o tipo da questão",
    "Alternativas ausentes ou com letras repetidas", "Alternativa do gabarito ausente",
}


def _canonical_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_source(path: str | Path, *, tipo: str = "desconhecido") -> int:
    """Registra um documento pela assinatura do conteúdo e sua localização observada."""
    init_db()
    source_path = Path(path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Documento-fonte indisponível: {source_path}")
    digest = _digest_bytes(source_path.read_bytes())
    physical_type = source_path.suffix.lower().lstrip(".") or tipo
    with db.atomic():
        row = DocumentoFonte.get_or_none(DocumentoFonte.sha256 == digest)
        if row:
            changed = []
            if row.disponibilidade != "presente" or not Path(row.localizacao or "").is_file():
                row.localizacao = str(source_path)
                row.disponibilidade = "presente"
                changed.extend([DocumentoFonte.localizacao, DocumentoFonte.disponibilidade])
            if row.tipo != physical_type:
                row.tipo = physical_type
                changed.append(DocumentoFonte.tipo)
            if changed:
                row.save(only=changed)
            return row.id
        row = DocumentoFonte.create(
            sha256=digest,
            tipo=physical_type,
            localizacao=str(source_path),
            disponibilidade="presente",
        )
        return row.id


def verify_source(source_id: int) -> dict:
    """Compara o arquivo atual com o SHA-256 registrado, sem alterar o estado."""
    source = read_batch.record(DocumentoFonte, source_id)
    path = Path(source.localizacao).expanduser() if source.localizacao else None
    if path is None or not path.is_file():
        return {"disponivel": False, "integro": False, "motivo": "arquivo_ausente"}
    cache = _source_verification_batch.get()
    stat = path.stat()
    cache_key = (source.id, str(path.resolve()), stat.st_size, stat.st_mtime_ns, source.sha256)
    if cache is not None and cache_key in cache:
        return dict(cache[cache_key])
    actual = _digest_bytes(path.read_bytes())
    if not source.sha256:
        result = {"disponivel": True, "integro": False, "motivo": "hash_desconhecido"}
        if cache is not None:
            cache[cache_key] = result
        return dict(result)
    result = {
        "disponivel": True,
        "integro": actual == source.sha256,
        "motivo": "integro" if actual == source.sha256 else "hash_divergente",
        "sha256_registrado": source.sha256,
        "sha256_atual": actual,
    }
    if cache is not None:
        cache[cache_key] = result
    return dict(result)


def begin_source_verification_batch() -> Token:
    """Inicia cache em memória limitado a uma análise/fila consistente."""
    return _source_verification_batch.set({})


def end_source_verification_batch(token: Token) -> None:
    cache = _source_verification_batch.get() or {}
    for key, value in cache.items():
        if key[0] == "pdf_document":
            value.close()
    _source_verification_batch.reset(token)


@contextmanager
def source_pdf(path):
    """Reutiliza a leitura de até quatro PDFs somente durante um lote."""
    path = Path(path).resolve()
    cache = _source_verification_batch.get()
    if cache is None:
        with pdfplumber.open(path) as document:
            yield document
        return
    stat = path.stat()
    key = ("pdf_document", str(path), stat.st_size, stat.st_mtime_ns)
    if key not in cache:
        pdf_keys = [entry for entry in cache if entry[0] == "pdf_document"]
        if len(pdf_keys) >= 4:
            cache.pop(pdf_keys[0]).close()
        cache[key] = pdfplumber.open(path)
    yield cache[key]


def _current_content(questao: Questao) -> dict:
    data = {name: getattr(questao, name) for name in (
        "numero_oficial", "enunciado", "texto_apoio", "tipo", "disciplina", "topico", "banca", "ano",
        "cargo", "orgao", "dificuldade", "gabarito", "comentario", "imagem_path",
    )}
    image_path = _resource_path(data.get("imagem_path"))
    if data.get("imagem_path"):
        data["imagem_sha256"] = _hash_file(image_path) if image_path and image_path.is_file() else None
    data["alternativas"] = [
        {"letra": alt.letra, "texto": alt.texto}
        for alt in (read_batch.alternatives(questao.id) if read_batch.alternatives(questao.id) is not None else Alternativa.select().where(Alternativa.questao == questao.id).order_by(Alternativa.letra))
    ]
    return data


def _resource_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    root = TEST_ROOT or ROOT_DIR
    return (root / path).resolve()


def _hash_file(path: Path) -> str:
    cache = _source_verification_batch.get()
    stat = path.stat()
    key = ("file_sha256", str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if cache is not None and key in cache:
        return cache[key]
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    result = digest.hexdigest()
    if cache is not None:
        cache[key] = result
    return result


def _verify_facsimile_pixels(item: dict, evidence_by_id: dict[int, EvidenciaQuestao]) -> None:
    """Confirma que o PNG é exatamente o recorte RGB da página PDF declarada."""
    try:
        from PIL import Image
        from src.importador.pdf_render import render_region
        scale = float(item.get("scale"))
        if not 1.0 <= scale <= 3.0:
            raise ValueError("escala_facsimile_invalida")
        evidence = evidence_by_id.get(item.get("evidencia_id"))
        if evidence is None or evidence.parte not in {"conteudo", "contexto"} or evidence.pagina is None:
            raise ValueError("evidencia_facsimile_invalida")
        source = read_batch.record(DocumentoFonte, evidence.documento_fonte_id)
        if source.tipo.casefold() != "pdf" or not source.localizacao:
            raise ValueError("facsimile_exige_pdf")
        with Image.open(_resource_path(item["path"])) as actual:
            actual_rgb = actual.convert("RGB")
        x0, y0, x1, y1 = map(float, (evidence.x0, evidence.y0, evidence.x1, evidence.y1))
        expected = render_region(source.localizacao, evidence.pagina, (x0, y0, x1, y1), scale=scale)
        if list(actual_rgb.size) != expected["size"] or hashlib.sha256(actual_rgb.tobytes()).hexdigest() != expected["pixels_sha256"]:
            raise ValueError("pixels_facsimile_divergentes")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("facsimile_recurso_invalido") from error


def _norm_source_text(value: str) -> str:
    import unicodedata
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value or "")
    value = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", re.sub(r"[^\wÀ-ÿ]+", " ", value, flags=re.UNICODE).casefold()).strip()


def _verify_automatic_identity(manifest: dict, refs: list[EvidenciaQuestao], texts=None) -> None:
    identity = manifest.get("identidade") or {}
    scope = manifest.get("escopo") or {}
    key = identity.get("catalogo_chave")
    if key:
        config_path = ROOT_DIR / "config" / "gabaritos.json"
        if identity.get("catalogo_sha256") != _hash_file(config_path):
            raise ValueError("catalogo_alterado")
        from src.importador.catalogo import carregar_catalogo, normalizar_chave
        catalog = carregar_catalogo(config_path)
        entry = catalog.get(normalizar_chave(key))
        if not entry or entry.get("confirmado") is not True:
            raise ValueError("associacao_catalogo_nao_confirmada")
        sample_root = (ROOT_DIR / "samples").resolve()
        book = (sample_root / key).resolve()
        if not book.is_relative_to(sample_root):
            raise ValueError("caminho_catalogo_invalido")
        allowed_answers = {(sample_root / entry["gabarito"]).resolve()}
        if entry.get("complemento"):
            allowed_answers.add((sample_root / entry["complemento"]).resolve())
        for ref in refs:
            source = read_batch.record(DocumentoFonte, ref.documento_fonte_id)
            path = Path(source.localizacao).resolve()
            role = "gabarito" if ref.parte == "gabarito" else "caderno"
            declared = (identity.get("equivalencia_documental") or {}).get(role)
            allowed = allowed_answers if role == "gabarito" else {book}
            if declared is not None:
                from src.importador.comparacao_fontes import comparar_documentos
                if declared.get("sha256_fonte") != source.sha256 or not any(
                        reference.is_file() and comparar_documentos(path, reference) == declared for reference in allowed):
                    raise ValueError("equivalencia_documental_nao_comprovada")
            elif path not in allowed:
                raise ValueError("fonte_diverge_do_catalogo")
        book_hash = _hash_file(book)
        expected = {"prova": entry.get("prova") or "pdf:" + book_hash,
                    "cargo": entry.get("cargo") or "caderno-unico",
                    "codigo": entry.get("codigo") or entry.get("prova") or "caderno-unico",
                    "versao": "sha256:" + book_hash}
        if any(scope.get(name) != value for name, value in expected.items()):
            raise ValueError("escopo_diverge_do_catalogo")
    elif texts is not None:
        # Fora do catálogo, a identidade precisa constar literalmente nos dois
        # documentos; valores autocontidos em JSON não demonstram identidade.
        for text in texts:
            if any(not _norm_source_text(str(scope.get(name) or "")) or
                   _norm_source_text(str(scope[name])) not in text
                   for name in ("prova", "cargo", "codigo", "versao")):
                raise ValueError("identidade_nao_confirmada_na_fonte")
    else:
        # Certificados sem vínculo de catálogo têm as fontes completas
        # revalidadas para que uma alteração de escopo não passe silenciosa.
        import pdfplumber
        docs = []
        for sid in {ref.documento_fonte_id for ref in refs}:
            source = read_batch.record(DocumentoFonte, sid)
            with source_pdf(source.localizacao) as pdf:
                docs.append(_norm_source_text("\n".join(page.extract_text() or "" for page in pdf.pages)))
        _verify_automatic_identity(manifest, refs, docs)


def _verify_source_claims(manifest: dict, refs: list[EvidenciaQuestao], version: QuestaoVersao) -> None:
    """Confirma número, enunciado, alternativas e gabarito no texto PDF real."""
    try:
        import pdfplumber
        from src.importador.pdf_fonte import readable_source_page
        content = _version_content(version)
        presentation_ids = {item["evidencia_id"] for item in manifest["apresentacao"]["questao"]}
        content_refs = [ref for ref in refs if ref.parte == "conteudo" and ref.id in presentation_ids]
        answer_refs = [ref for ref in refs if ref.parte == "gabarito"]
        if not content_refs or not answer_refs:
            raise ValueError("evidencias_conteudo_gabarito_ausentes")
        context_refs = [ref for ref in refs if ref.parte == "contexto"]
        pieces = {"conteudo": [], "gabarito": [], "contexto": []}
        raw_pieces = {"conteudo": [], "gabarito": [], "contexto": []}
        content_first_line = ""
        for label, ref in ([("conteudo", ref) for ref in content_refs] + [("gabarito", ref) for ref in answer_refs]
                           + [("contexto", ref) for ref in context_refs]):
            source = read_batch.record(DocumentoFonte, ref.documento_fonte_id)
            if source.tipo.casefold() != "pdf" or ref.pagina is None:
                raise ValueError("claims_exigem_pdf")
            with source_pdf(source.localizacao) as pdf:
                original_page = pdf.pages[ref.pagina - 1]
                raw_text = original_page.crop((ref.x0, ref.y0, ref.x1, ref.y1)).extract_text() or ""
                page = readable_source_page(original_page)
                text = page.crop((ref.x0, ref.y0, ref.x1, ref.y1)).extract_text(x_tolerance=2, y_tolerance=3) or ""
            if label == "conteudo" and not content_first_line and text.strip():
                content_first_line = text.strip().splitlines()[0]
            normalized = _norm_source_text(text)
            if not normalized:
                raise ValueError("pdf_regiao_sem_texto")
            pieces[label].append(normalized)
            raw_pieces[label].append(_norm_source_text(raw_text))
        pieces = {key: [" ".join(value), " ".join(raw_pieces[key])] for key, value in pieces.items()}
        for label in ("conteudo", "gabarito"):
            terms = manifest["identidade"].get(label + "_termos", [])
            if any(not _norm_source_text(str(term)) or not any(_norm_source_text(str(term)) in variant for variant in pieces[label]) for term in terms):
                raise ValueError(label + "_alegado_nao_consta_na_fonte")
        number = str(content.get("numero_oficial") or "")
        first_marker = re.search(rf"(?:^|\s)0*{re.escape(number)}[.)\-:]\s", content_first_line)
        if not any(re.search(rf"(?:quest[aã]o|item)\s*0*{re.escape(number)}\b|^\s*0*{re.escape(number)}\b", variant) for variant in pieces["conteudo"]) and not (first_marker and first_marker.start() < 16):
            raise ValueError("numero_nao_marcado_na_fonte")
        statement = _norm_source_text(content.get("enunciado") or "")
        if not statement or not any(statement in variant for variant in pieces["conteudo"]):
            raise ValueError("conteudo_nao_confirmado_na_fonte")
        support = _norm_source_text(content.get("texto_apoio") or "")
        if support and not any(support in variant for variant in pieces["contexto"]):
            raise ValueError("contexto_nao_confirmado_na_fonte")
        answer = str(content.get("gabarito") or "").strip()
        aliases = {"Certo": {"certo", "c"}, "Errado": {"errado", "e"}}.get(answer, {_norm_source_text(answer)})
        if not aliases or not any(re.search(rf"(?:^|\s)0*{number}\s+{re.escape(token)}(?:\s|$)", variant) for token in aliases for variant in pieces["gabarito"]):
            raise ValueError("gabarito_nao_confirmado_na_fonte")
        if any(not _norm_source_text(str(alt.get("texto") or "")) or
               not any(_norm_source_text(str(alt["texto"])) in variant for variant in pieces["conteudo"])
               for alt in content.get("alternativas", [])):
            raise ValueError("alternativas_nao_confirmadas_na_fonte")
        _verify_automatic_identity(manifest, refs)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("leitura_fonte_invalida") from error


def create_question_version(
    question_id: int,
    *,
    source_id: int | None = None,
    extraction_id: int | None = None,
    content_review: str = "pendente",
    answer_review: str = "desconhecido",
) -> int:
    """Captures a new snapshot; previous versions and their reviews remain untouched."""
    init_db()
    if content_review not in CONTEUDO_REVIEW or answer_review not in GABARITO_REVIEW:
        raise ValueError("Estado de revisão desconhecido.")
    question = Questao.get_by_id(question_id)
    data = _current_content(question)
    serialized = _canonical_json(data)
    digest = _digest_bytes(serialized.encode("utf-8"))
    with db.atomic():
        latest = (QuestaoVersao.select()
                  .where(QuestaoVersao.questao == question_id)
                  .order_by(QuestaoVersao.numero_versao.desc()).first())
        if latest:
            # Edições de conteúdo preservam a fonte e a execução que deram
            # origem à versão, salvo quando a chamada informa uma nova origem.
            if source_id is None:
                source_id = latest.documento_fonte_id
            if extraction_id is None:
                extraction_id = latest.execucao_extracao_id
        if (latest and _version_content_matches(latest, data)
                and latest.documento_fonte_id == source_id
                and latest.execucao_extracao_id == extraction_id):
            return latest.id
        return QuestaoVersao.create(
            questao=question_id,
            numero_versao=(latest.numero_versao + 1 if latest else 1),
            hash_conteudo=digest,
            conteudo_json=serialized,
            documento_fonte=source_id,
            execucao_extracao=extraction_id,
            revisao_conteudo=content_review,
            revisao_gabarito=answer_review,
        ).id


def register_extraction(
    source_id: int | None,
    *,
    extractor: str,
    extractor_version: str | None = None,
    profile: str | None = None,
    profile_version: str | None = None,
    parameters: dict | None = None,
    diagnostics: list | None = None,
) -> int:
    init_db()
    return ExecucaoExtracao.create(
        documento_fonte=source_id,
        extrator=extractor,
        versao_extrator=extractor_version,
        perfil=profile,
        versao_perfil=profile_version,
        parametros_json=_canonical_json(parameters or {}),
        diagnosticos_json=json.dumps(diagnostics or [], ensure_ascii=False),
    ).id


def add_evidence(
    version_id: int,
    source_id: int,
    *,
    part: str,
    page: int | None = None,
    document_locator: str | None = None,
    bounds: tuple[float, float, float, float] | None = None,
    coordinate_system: str | None = None,
    page_size: tuple[float, float] | None = None,
    rotation: int | None = None,
    scope: dict | None = None,
    excerpt: str | None = None,
) -> int:
    init_db()
    if part not in EVIDENCE_PARTS:
        raise ValueError("Parte inválida; use conteúdo, contexto, recurso visual ou gabarito.")
    version = QuestaoVersao.get_or_none(QuestaoVersao.id == version_id)
    if version is None:
        raise ValueError("A versão da questão não existe.")
    if not _version_is_current(version):
        raise ValueError("A questão mudou desde o snapshot; selecione ou crie a versão atual antes de anexar evidência.")
    if not isinstance(scope, dict) or any(not str(scope.get(field) or "").strip()
                                          for field in ("prova", "cargo", "codigo", "versao")):
        raise ValueError("Identifique explicitamente prova, cargo, código e versão da evidência.")
    if part == "gabarito" and scope.get("situacao_gabarito") not in {"preliminar", "definitivo", "documento_fornecido", "anulado", "conflitante"}:
        raise ValueError("Informe se o gabarito é preliminar, definitivo, anulado ou conflitante.")
    if page is None and not document_locator:
        raise ValueError("Informe uma página PDF ou identificador de parágrafo/tabela DOCX.")
    if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page < 1):
        raise ValueError("Página inválida; use uma página a partir de 1.")
    if rotation is not None and rotation not in {0, 90, 180, 270}:
        raise ValueError("Rotação inválida; use 0, 90, 180 ou 270 graus.")
    if bounds is None or len(bounds) != 4 or not all(math.isfinite(float(value)) for value in bounds):
        raise ValueError("Informe coordenadas finitas para a região da evidência.")
    x0, y0, x1, y1 = map(float, bounds)
    if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
        raise ValueError("A região precisa ter largura e altura positivas e coordenadas não negativas.")
    if page_size is None or len(page_size) != 2 or not all(math.isfinite(float(value)) and float(value) > 0 for value in page_size):
        raise ValueError("Informe dimensões de página finitas e positivas.")
    source = read_batch.record(DocumentoFonte, source_id)
    integrity = verify_source(source.id)
    if not integrity["disponivel"] or not integrity["integro"]:
        raise ValueError("A fonte está ausente ou diverge do hash registrado.")
    source_path = Path(source.localizacao)
    if source.tipo.casefold() == "pdf":
        if page is None:
            raise ValueError("Evidência PDF exige uma página numerada.")
        coordinate = (coordinate_system or "").casefold()
        if "pdf-point" not in coordinate or "origem superior esquerda" not in coordinate:
            raise ValueError("O sistema de coordenadas PDF deve declarar pontos e origem superior esquerda.")
        try:
            with source_pdf(source_path) as pdf:
                if page > len(pdf.pages):
                    raise ValueError(f"A fonte tem {len(pdf.pages)} páginas; a página {page} não existe.")
                pdf_page = pdf.pages[page - 1]
                width, height = float(pdf_page.width), float(pdf_page.height)
                actual_rotation = int(getattr(pdf_page, "rotation", 0) or 0) % 360
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(f"Não foi possível validar a página do PDF: {error}") from error
        if not math.isclose(float(page_size[0]), width, abs_tol=1.0) or not math.isclose(float(page_size[1]), height, abs_tol=1.0):
            raise ValueError("As dimensões informadas divergem das dimensões da página PDF.")
        if rotation is None or rotation != actual_rotation:
            raise ValueError("A rotação informada diverge da rotação real da página PDF.")
        if x1 > width or y1 > height:
            raise ValueError("A região ultrapassa os limites da página PDF.")
    elif source.tipo.casefold() == "docx":
        if page is not None or not re.fullmatch(r"(?:paragraph|table):[1-9]\d*", document_locator or ""):
            raise ValueError("DOCX exige identificador paragraph:N ou table:N; paginação não é estável.")
    else:
        raise ValueError("Tipo de fonte não suportado para conferência de evidência.")
    with db.atomic():
        duplicate = EvidenciaQuestao.get_or_none(
            (EvidenciaQuestao.questao_versao == version_id)
            & (EvidenciaQuestao.documento_fonte == source_id)
            & (EvidenciaQuestao.parte == part)
            & (EvidenciaQuestao.pagina == page)
            & (EvidenciaQuestao.identificador_documento == document_locator)
            & (EvidenciaQuestao.x0 == x0) & (EvidenciaQuestao.y0 == y0)
            & (EvidenciaQuestao.x1 == x1) & (EvidenciaQuestao.y1 == y1)
            & (EvidenciaQuestao.escopo_json == _canonical_json(scope))
        )
        if duplicate:
            return duplicate.id
        evidence = EvidenciaQuestao.create(
            questao_versao=version_id,
            documento_fonte=source_id,
            parte=part,
            escopo_json=_canonical_json(scope),
            pagina=page,
            identificador_documento=document_locator,
            x0=bounds[0] if bounds else None,
            y0=bounds[1] if bounds else None,
            x1=bounds[2] if bounds else None,
            y1=bounds[3] if bounds else None,
            sistema_coordenadas=coordinate_system,
            largura_pagina=page_size[0] if page_size else None,
            altura_pagina=page_size[1] if page_size else None,
            rotacao_pagina=rotation,
            texto_evidencia=excerpt,
        )
        # Evidência nova altera a base documental da revisão. Força nova
        # decisão para que aprovações anteriores não sobrevivam à alteração.
        if part in CONTENT_PARTS:
            version.revisao_conteudo = "pendente"
            version.save(only=[QuestaoVersao.revisao_conteudo])
            RevisaoConteudo.create(
                questao_versao=version_id, decisao="pendente",
                justificativa="Nova evidência de conteúdo anexada; revisar novamente esta versão.",
                evidencia_json=json.dumps([evidence.id]),
            )
        else:
            version.revisao_gabarito = "desconhecido"
            version.save(only=[QuestaoVersao.revisao_gabarito])
            RevisaoGabarito.create(
                questao_versao=version_id, decisao="desconhecido",
                justificativa="Nova evidência de gabarito anexada; confirmar novamente esta versão.",
                evidencia_json=json.dumps([evidence.id]),
            )
        return evidence.id


def _version_content(version: QuestaoVersao) -> dict:
    return json.loads(version.conteudo_json)


def _evidence_for_decision(version_id: int, evidence_ids: list[int], allowed_parts: set[str]) -> list[EvidenciaQuestao]:
    ids = list(evidence_ids or [])
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Informe IDs de evidência existentes e sem repetição.")
    references = read_batch.evidence_ids(ids)
    if references is None:
        references = list(EvidenciaQuestao.select().where(EvidenciaQuestao.id.in_(ids)))
    by_id = {item.id: item for item in references}
    if len(by_id) != len(ids):
        raise ValueError("Um ou mais IDs de evidência não existem.")
    references = [by_id[item_id] for item_id in ids]
    if any(item.questao_versao_id != version_id for item in references):
        raise ValueError("Todas as evidências precisam pertencer à versão selecionada.")
    if any(item.parte not in allowed_parts for item in references):
        raise ValueError("A evidência selecionada é de outra parte da questão.")
    for item in references:
        try:
            scope = json.loads(item.escopo_json or "{}")
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("O escopo salvo na evidência está corrompido.") from error
        if any(not str(scope.get(field) or "").strip() for field in ("prova", "cargo", "codigo", "versao")):
            raise ValueError("A evidência não identifica prova, cargo, código e versão.")
    return references


def _same_scope(left: EvidenciaQuestao, right: EvidenciaQuestao) -> bool:
    a, b = json.loads(left.escopo_json or "{}"), json.loads(right.escopo_json or "{}")
    return all(a.get(field) == b.get(field) for field in ("prova", "cargo", "codigo", "versao"))


def _validate_evidence_sources(references: list[EvidenciaQuestao]) -> None:
    for item in references:
        integrity = verify_source(item.documento_fonte_id)
        if not integrity["disponivel"] or not integrity["integro"]:
            raise ValueError("A fonte está ausente ou foi alterada desde o registro da evidência.")


def _evidence_fingerprint(references: list[EvidenciaQuestao]) -> str:
    rows = []
    for item in sorted(references, key=lambda row: row.id):
        source = read_batch.record(DocumentoFonte, item.documento_fonte_id)
        rows.append({
            "id": item.id, "parte": item.parte, "fonte": source.sha256,
            "pagina": item.pagina, "localizador": item.identificador_documento,
            "limites": [item.x0, item.y0, item.x1, item.y1],
            "sistema_coordenadas": item.sistema_coordenadas,
            "tamanho_pagina": [item.largura_pagina, item.altura_pagina],
            "rotacao": item.rotacao_pagina,
            "texto": item.texto_evidencia,
            "escopo": item.escopo_json,
        })
    return _digest_bytes(_canonical_json({"rule": DIAGNOSTIC_RULE_VERSION, "evidencias": rows}).encode("utf-8"))


def _automatic_snapshot_hash(version: QuestaoVersao) -> str:
    return version.hash_conteudo


def _manifest_error(manifest: object) -> str | None:
    if not isinstance(manifest, dict):
        return "manifesto_invalido"
    required = {"regra", "numero_oficial", "gabarito", "escopo", "checks", "apresentacao", "verificador"}
    if not required.issubset(manifest):
        return "manifesto_incompleto"
    if manifest.get("regra") != AUTOMATIC_RULE_VERSION:
        return "regra_incompativel"
    identity = manifest.get("identidade")
    if not isinstance(identity, dict) or not isinstance(identity.get("conteudo_termos"), list) or not isinstance(identity.get("gabarito_termos"), list):
        return "identidade_termos_ausente"
    scope = manifest.get("escopo")
    if not isinstance(scope, dict) or any(not str(scope.get(k) or "").strip() for k in ("prova", "cargo", "codigo", "versao")):
        return "escopo_incompleto"
    checks = manifest.get("checks")
    required_checks = {"identidade", "numero", "conteudo_completo", "alternativas", "contexto", "recursos", "gabarito"}
    if not isinstance(checks, dict) or any(checks.get(k) is not True for k in required_checks):
        return "checks_incompletos"
    presentation = manifest.get("apresentacao")
    if not isinstance(presentation, dict) or presentation.get("modo") != "facsimile":
        return "facsimile_invalido"
    question = presentation.get("questao")
    if not isinstance(question, list) or not question:
        return "facsimile_questao_ausente"
    for item in question + (presentation.get("contexto") or []):
        if (not isinstance(item, dict) or not isinstance(item.get("evidencia_id"), int) or not item.get("path")
                or not item.get("sha256") or not isinstance(item.get("scale"), (int, float))
                or not 1.0 <= float(item["scale"]) <= 3.0):
            return "recurso_facsimile_invalido"
    verifier = manifest.get("verificador")
    if not isinstance(verifier, dict) or not str(verifier.get("metodo") or "").strip() or not str(verifier.get("versao") or "").strip():
        return "verificador_invalido"
    return None


def record_automatic_validation(version_id: int, *, evidence_ids: list[int], manifest: dict) -> int:
    """Valida e grava certificado append-only; nunca cria revisão humana."""
    init_db()
    version = QuestaoVersao.get_or_none(QuestaoVersao.id == version_id)
    if version is None:
        raise ValueError("A versão da questão não existe.")
    if not _version_is_current(version):
        raise ValueError("O snapshot da versão está desatualizado.")
    latest_content = RevisaoConteudo.select().where((RevisaoConteudo.questao_versao == version_id) & (RevisaoConteudo.decisao != "pendente")).order_by(RevisaoConteudo.id.desc()).first()
    latest_answer = RevisaoGabarito.select().where((RevisaoGabarito.questao_versao == version_id) & (RevisaoGabarito.decisao != "pendente")).order_by(RevisaoGabarito.id.desc()).first()
    if latest_content and latest_content.decisao == "rejeitado":
        raise ValueError("rejeicao_humana_explicitamente_bloqueia")
    if latest_answer and latest_answer.decisao in {"conflitante", "anulado"}:
        raise ValueError("conflito_humano_explicitamente_bloqueia")
    error = _manifest_error(manifest)
    if error:
        raise ValueError(error)
    refs = _evidence_for_decision(version_id, evidence_ids, CONTENT_PARTS | {"gabarito"})
    if not any(item.parte == "conteudo" for item in refs) or not any(item.parte == "gabarito" for item in refs):
        raise ValueError("A validação exige evidência de conteúdo e gabarito.")
    scope = manifest["escopo"]
    for ref in refs:
        saved = json.loads(ref.escopo_json or "{}")
        if any(saved.get(k) != scope.get(k) for k in ("prova", "cargo", "codigo", "versao")):
            raise ValueError("Escopo da evidência diverge do manifesto.")
    _validate_evidence_sources(refs)
    content = _version_content(version)
    if manifest["numero_oficial"] != content.get("numero_oficial") or str(manifest["gabarito"]).strip() != str(content.get("gabarito") or "").strip():
        raise ValueError("Número ou gabarito diverge do snapshot.")
    status = {json.loads(ref.escopo_json or "{}").get("situacao_gabarito") for ref in refs if ref.parte == "gabarito"}
    if not status.intersection({"definitivo", "documento_fornecido"}) or status.intersection({"preliminar", "conflitante", "anulado"}):
        raise ValueError("Situação de gabarito não libera validação automática.")
    question_ids = {item["evidencia_id"] for item in manifest["apresentacao"]["questao"]}
    ref_ids = {ref.id for ref in refs}
    if not question_ids.issubset(ref_ids) or any(next(ref for ref in refs if ref.id == item).parte != "conteudo" for item in question_ids):
        raise ValueError("Fac-símile referencia evidência inexistente ou externa à versão.")
    context_items = manifest["apresentacao"].get("contexto") or []
    if context_items and any(next((ref.parte for ref in refs if ref.id == item["evidencia_id"]), None) != "contexto" for item in context_items):
        raise ValueError("Fac-símile de contexto exige evidências de contexto.")
    facsimile_items = manifest["apresentacao"]["questao"] + (manifest["apresentacao"].get("contexto") or [])
    evidence_by_id = {ref.id: ref for ref in refs}
    for item in facsimile_items:
        path = _resource_path(item["path"])
        if not path or not path.is_file() or _hash_file(path) != item["sha256"]:
            raise ValueError("Recurso do fac-símile ausente ou alterado.")
        _verify_facsimile_pixels(item, evidence_by_id)
    _verify_source_claims(manifest, refs, version)
    fingerprint = _evidence_fingerprint(refs)
    serialized_ids = json.dumps(sorted(ref_ids), separators=(",", ":"))
    existing = ValidacaoAutomatica.get_or_none(
        (ValidacaoAutomatica.questao_versao == version_id) &
        (ValidacaoAutomatica.versao_regra == AUTOMATIC_RULE_VERSION) &
        (ValidacaoAutomatica.hash_snapshot == _automatic_snapshot_hash(version)) &
        (ValidacaoAutomatica.fingerprint_evidencias == fingerprint) &
        (ValidacaoAutomatica.evidencia_json == serialized_ids) &
        (ValidacaoAutomatica.manifesto_json == _canonical_json(manifest))
    )
    if existing:
        return existing.id
    try:
        return ValidacaoAutomatica.create(
            questao_versao=version_id, versao_regra=AUTOMATIC_RULE_VERSION,
            hash_snapshot=_automatic_snapshot_hash(version), fingerprint_evidencias=fingerprint,
            evidencia_json=serialized_ids, manifesto_json=_canonical_json(manifest),
        ).id
    except IntegrityError as error:
        existing = ValidacaoAutomatica.get_or_none(
            (ValidacaoAutomatica.questao_versao == version_id) &
            (ValidacaoAutomatica.versao_regra == AUTOMATIC_RULE_VERSION) &
            (ValidacaoAutomatica.hash_snapshot == _automatic_snapshot_hash(version)) &
            (ValidacaoAutomatica.fingerprint_evidencias == fingerprint)
        )
        if existing and existing.evidencia_json == serialized_ids and existing.manifesto_json == _canonical_json(manifest):
            return existing.id
        raise ValueError("certificado_concorrente_divergente") from error


def get_automatic_validation(version_id: int) -> dict:
    version = read_batch.record(QuestaoVersao, version_id)
    result = {"valida": False, "motivos": [], "manifesto": {}, "registro_id": None}
    if version is None:
        result["motivos"].append("versao_inexistente")
        return result
    latest_content = read_batch.review(RevisaoConteudo, version_id, non_pending=True)
    latest_answer = read_batch.review(RevisaoGabarito, version_id, non_pending=True)
    if (latest_content and latest_content.decisao == "rejeitado") or (latest_answer and latest_answer.decisao in {"conflitante", "anulado"}):
        result["motivos"].append("rejeicao_ou_conflito_humano")
        return result
    rows = read_batch.version_rows(ValidacaoAutomatica, version_id)
    if rows is not None:
        rows = [r for r in reversed(rows) if r.versao_regra == AUTOMATIC_RULE_VERSION]
    else:
        rows = list(ValidacaoAutomatica.select().where(
            (ValidacaoAutomatica.questao_versao == version_id)
            & (ValidacaoAutomatica.versao_regra == AUTOMATIC_RULE_VERSION)
        ).order_by(ValidacaoAutomatica.id.desc()))
    for row in rows:
        try:
            manifest = json.loads(row.manifesto_json or "{}")
            ids = json.loads(row.evidencia_json or "[]")
            refs = _evidence_for_decision(version_id, ids, CONTENT_PARTS | {"gabarito"})
            if row.hash_snapshot != _automatic_snapshot_hash(version) or not _version_is_current(version):
                raise ValueError("snapshot_desatualizado")
            if _manifest_error(manifest):
                raise ValueError(_manifest_error(manifest))
            if row.fingerprint_evidencias != _evidence_fingerprint(refs):
                raise ValueError("fingerprint_evidencias_divergente")
            _validate_evidence_sources(refs)
            _verify_automatic_identity(manifest, refs)
            content = _version_content(version)
            if manifest.get("numero_oficial") != content.get("numero_oficial") or str(manifest.get("gabarito")).strip() != str(content.get("gabarito") or "").strip():
                raise ValueError("snapshot_numero_ou_gabarito_divergente")
            scopes = [json.loads(ref.escopo_json or "{}") for ref in refs]
            expected_scope = manifest.get("escopo") or {}
            if any(any(scope.get(k) != expected_scope.get(k) for k in ("prova", "cargo", "codigo", "versao")) for scope in scopes):
                raise ValueError("escopo_divergente")
            if any(scope.get("situacao_gabarito") in {"preliminar", "conflitante", "anulado"} for scope in scopes):
                raise ValueError("gabarito_nao_libera")
            for item in (manifest.get("apresentacao", {}).get("questao", []) + manifest.get("apresentacao", {}).get("contexto", [])):
                path = _resource_path(item.get("path"))
                if not path or not path.is_file() or _hash_file(path) != item.get("sha256"):
                    raise ValueError("recurso_facsimile_alterado")
            result.update({"valida": True, "manifesto": manifest, "registro_id": row.id})
            if manifest.get("escopo", {}).get("situacao_gabarito") == "documento_fornecido":
                result["motivos"].append("gabarito_documento_fornecido")
            return result
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            result["motivos"].append(str(error))
    return result


def _diagnostic(code: str, stage: str, severity: str, nature: str, message: str,
                part: str | None = None, location: dict | None = None,
                evidence: list[int] | None = None, action: str | None = None) -> dict:
    return {
        "codigo": code, "etapa": stage, "severidade": severity, "natureza": nature,
        "mensagem": message, "parte": part, "localizacao": location,
        "evidencia_disponivel": list(evidence or []), "acao_necessaria": action,
    }


def _version_is_current(version: QuestaoVersao) -> bool:
    current = _current_content(read_batch.record(Questao, version.questao_id))
    return _version_content_matches(version, current)


def _version_content_matches(version: QuestaoVersao, current: dict) -> bool:
    """Aceita snapshots anteriores ao hash de imagem sem reescrevê-los.

    A integridade de uma imagem legada sem digest continua pendente no
    diagnóstico, mas a compatibilidade de schema não invalida todo o snapshot.
    """
    try:
        saved = json.loads(version.conteudo_json)
    except (TypeError, json.JSONDecodeError):
        return False
    comparable = dict(current)
    if "imagem_sha256" not in saved:
        comparable.pop("imagem_sha256", None)
    return _digest_bytes(_canonical_json(comparable).encode("utf-8")) == version.hash_conteudo


def review_content(version_id: int, *, decision: str, reviewer: str, rationale: str, evidence_ids: list[int]) -> int:
    init_db()
    if decision not in {"conferido", "rejeitado", "pendente"} or not reviewer.strip() or not rationale.strip():
        raise ValueError("Decisão, pessoa responsável e justificativa são obrigatórias.")
    version = QuestaoVersao.get_by_id(version_id)
    if not _version_is_current(version):
        raise ValueError("O conteúdo mudou depois da versão; crie uma nova versão antes de revisar.")
    references = (_evidence_for_decision(version_id, evidence_ids, CONTENT_PARTS)
                  if evidence_ids else [])
    if decision == "conferido":
        if not references:
            raise ValueError("A conferência exige evidência da parte de conteúdo desta versão.")
        _validate_evidence_sources(references)
        problems = [problem for problem in problemas_estrutura(_version_content(version))
                    if problem in OBJECTIVE_STRUCTURE_PROBLEMS]
        if problems:
            raise ValueError("A estrutura da questão precisa ser corrigida: " + "; ".join(problems))
        expected_cargo = str(_version_content(version).get("cargo") or "").strip()
        if expected_cargo and any(json.loads(item.escopo_json or "{}").get("cargo") != expected_cargo for item in references):
            raise ValueError("O cargo declarado na evidência diverge do cargo desta versão.")
        latest_answer = (RevisaoGabarito.select().where(
            (RevisaoGabarito.questao_versao == version_id)
            & (RevisaoGabarito.decisao.in_(["definitivo_confirmado", "anulado"]))
        ).order_by(RevisaoGabarito.criada_em.desc(), RevisaoGabarito.id.desc()).first())
        if latest_answer:
            try:
                answer_ids = json.loads(latest_answer.evidencia_json or "[]")
                answer_refs = _evidence_for_decision(version_id, answer_ids, {"gabarito"})
            except ValueError:
                answer_refs = []
            if answer_refs and any(not _same_scope(item, answer_refs[0]) for item in references):
                raise ValueError("A prova, o cargo, o código ou a versão do conteúdo diverge do gabarito confirmado.")
    with db.atomic():
        evidence_json = json.dumps([item.id for item in references])
        latest = (RevisaoConteudo.select().where(RevisaoConteudo.questao_versao == version_id)
                  .order_by(RevisaoConteudo.criada_em.desc(), RevisaoConteudo.id.desc()).first())
        if (latest and latest.decisao == decision
                and latest.responsavel_declarado == reviewer.strip()
                and latest.justificativa == rationale.strip()
                and latest.evidencia_json == evidence_json):
            return latest.id
        row = RevisaoConteudo.create(
            questao_versao=version_id,
            decisao=decision,
            responsavel_declarado=reviewer,
            justificativa=rationale.strip(),
            evidencia_json=evidence_json,
        )
        version.revisao_conteudo = decision
        version.save(only=[QuestaoVersao.revisao_conteudo])
        return row.id


def review_answer(
    version_id: int,
    *,
    answer: str | None,
    decision: str,
    reviewer: str,
    rationale: str,
    evidence_ids: list[int],
) -> int:
    init_db()
    if decision not in GABARITO_REVIEW or not reviewer.strip() or not rationale.strip():
        raise ValueError("Decisão, pessoa responsável e justificativa são obrigatórias.")
    version = QuestaoVersao.get_by_id(version_id)
    if not _version_is_current(version):
        raise ValueError("O conteúdo mudou depois da versão; crie uma nova versão antes de revisar o gabarito.")
    requires_answer_evidence = decision in {"preliminar", "definitivo_confirmado", "anulado", "conflitante"}
    references = (_evidence_for_decision(version_id, evidence_ids, {"gabarito"})
                  if evidence_ids else [])
    if requires_answer_evidence:
        if not references:
            raise ValueError("A decisão de gabarito exige evidência da parte de gabarito desta versão.")
        _validate_evidence_sources(references)
        scope = json.loads(references[0].escopo_json or "{}")
        expected_status = {
            "preliminar": "preliminar", "definitivo_confirmado": "definitivo",
            "anulado": "anulado", "conflitante": "conflitante",
        }[decision]
        if scope.get("situacao_gabarito") != expected_status:
            raise ValueError("A situação declarada da evidência diverge da decisão do gabarito.")
        expected_cargo = str(_version_content(version).get("cargo") or "").strip()
        if expected_cargo and any(json.loads(item.escopo_json or "{}").get("cargo") != expected_cargo for item in references):
            raise ValueError("O cargo declarado no gabarito diverge do cargo desta versão.")
        if len({json.dumps(json.loads(item.escopo_json or "{}"), sort_keys=True) for item in references}) > 1:
            raise ValueError("As evidências de gabarito pertencem a escopos diferentes.")
        content_review = (RevisaoConteudo.select().where(
            (RevisaoConteudo.questao_versao == version_id)
            & (RevisaoConteudo.decisao == "conferido")
        ).order_by(RevisaoConteudo.criada_em.desc(), RevisaoConteudo.id.desc()).first())
        if content_review:
            content_refs = _evidence_for_decision(version_id, json.loads(content_review.evidencia_json or "[]"), CONTENT_PARTS)
            if any(not _same_scope(item, references[0]) for item in content_refs):
                raise ValueError("A prova, o cargo, o código ou a versão do gabarito diverge do conteúdo conferido.")
    if decision in {"definitivo_confirmado", "anulado"}:
        content = _version_content(version)
        expected = "Anulada" if decision == "anulado" else normalizar_gabarito(answer, content.get("tipo"))
        if expected is None or (decision == "anulado" and answer not in {None, "Anulada", "X"}):
            raise ValueError("Gabarito incompatível com o tipo ou decisão.")
        if decision == "definitivo_confirmado" and expected != normalizar_gabarito(content.get("gabarito"), content.get("tipo")):
            raise ValueError("A resposta precisa ser salva como nova versão antes de ser confirmada.")
        if decision == "anulado" and normalizar_gabarito(content.get("gabarito"), content.get("tipo")) != "Anulada":
            raise ValueError("A anulação precisa estar registrada no conteúdo da versão.")
    else:
        expected = answer
    with db.atomic():
        evidence_json = json.dumps([item.id for item in references])
        latest = (RevisaoGabarito.select().where(RevisaoGabarito.questao_versao == version_id)
                  .order_by(RevisaoGabarito.criada_em.desc(), RevisaoGabarito.id.desc()).first())
        if (latest and latest.gabarito == expected and latest.decisao == decision
                and latest.responsavel_declarado == reviewer.strip()
                and latest.justificativa == rationale.strip()
                and latest.evidencia_json == evidence_json):
            return latest.id
        row = RevisaoGabarito.create(
            questao_versao=version_id,
            gabarito=expected,
            decisao=decision,
            responsavel_declarado=reviewer,
            justificativa=rationale.strip(),
            evidencia_json=evidence_json,
        )
        version.revisao_gabarito = decision
        version.save(only=[QuestaoVersao.revisao_gabarito])
        return row.id


def assess_version(version_id: int) -> dict:
    """Retorna decisão explicável, com todos os motivos e sem efeito colateral no banco."""
    version = read_batch.record(QuestaoVersao, version_id)
    if version is None:
        item = _diagnostic("versao_inexistente", "identidade", "bloqueio", "objetiva",
                           "A versão solicitada não existe.", action="Selecione uma versão existente.")
        return {"versao_id": version_id, "liberada": False, "etapa_principal": "identidade",
                "pendencias": [item], "bloqueios_objetivos": [item], "alertas": [],
                "decisoes_humanas_necessarias": [], "estado_conteudo": "nao_verificado",
                "estado_gabarito": "desconhecido", "versao_regra": DIAGNOSTIC_RULE_VERSION}

    content = _version_content(version)
    all_evidence = read_batch.version_rows(EvidenciaQuestao, version.id)
    if all_evidence is None:
        all_evidence = list(EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == version.id).order_by(EvidenciaQuestao.id))
    content_review = read_batch.review(RevisaoConteudo, version.id, by_date=True)
    answer_review = read_batch.review(RevisaoGabarito, version.id, by_date=True)
    content_ids = []
    answer_ids = []
    content_refs = []
    answer_refs = []
    diagnostics = []

    if not _version_is_current(version):
        diagnostics.append(_diagnostic("snapshot_desatualizado", "identidade", "bloqueio", "objetiva",
            "O conteúdo atual diverge do snapshot selecionado.", action="Crie uma nova versão e confira-a antes de liberar."))
    number = content.get("numero_oficial")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        diagnostics.append(_diagnostic("numeracao_ausente", "numeracao", "bloqueio", "objetiva",
            "A versão não tem número oficial explícito.", action="Identifique o número no original; a posição na lista não o substitui."))

    if content_review and content_review.decisao == "conferido":
        try:
            content_ids = json.loads(content_review.evidencia_json or "[]")
            content_refs = _evidence_for_decision(version.id, content_ids, CONTENT_PARTS)
            _validate_evidence_sources(content_refs)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            diagnostics.append(_diagnostic("evidencia_conteudo_invalida", "revisao_conteudo", "bloqueio", "objetiva",
                str(error), part="conteudo", evidence=content_ids, action="Registre evidência acessível da versão e confira o conteúdo novamente."))
    else:
        state = content_review.decisao if content_review else version.revisao_conteudo
        diagnostics.append(_diagnostic("conteudo_nao_conferido", "revisao_conteudo", "bloqueio", "decisao_humana",
            f"Conteúdo está em estado '{state or 'não verificado'}'.", part="conteudo",
            action="Confira o snapshot com evidência de conteúdo ou registre rejeição/pêndencia."))

    if answer_review and answer_review.decisao == "definitivo_confirmado":
        try:
            answer_ids = json.loads(answer_review.evidencia_json or "[]")
            answer_refs = _evidence_for_decision(version.id, answer_ids, {"gabarito"})
            _validate_evidence_sources(answer_refs)
            if any(json.loads(item.escopo_json or "{}").get("situacao_gabarito") != "definitivo" for item in answer_refs):
                raise ValueError("A evidência não identifica um gabarito definitivo.")
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            diagnostics.append(_diagnostic("evidencia_gabarito_invalida", "associacao_gabarito", "bloqueio", "objetiva",
                str(error), part="gabarito", evidence=answer_ids, action="Confirme a região de gabarito definitivo desta mesma versão."))
    else:
        state = answer_review.decisao if answer_review else version.revisao_gabarito
        code = "gabarito_preliminar" if state == "preliminar" else "gabarito_conflitante" if state == "conflitante" else "gabarito_anulado" if state == "anulado" else "gabarito_nao_confirmado"
        message = {
            "preliminar": "O gabarito é preliminar e não libera uma nova prova.",
            "conflitante": "Há conflito conhecido entre fontes de gabarito.",
            "anulado": "A questão está anulada e não é avaliável.",
        }.get(state, f"Gabarito está em estado '{state or 'não verificado'}'.")
        diagnostics.append(_diagnostic(code, "associacao_gabarito", "bloqueio", "decisao_humana",
            message, part="gabarito", action="Confirme gabarito definitivo, registre conflito ou mantenha pendente conforme a fonte."))

    for evidence in all_evidence:
        integrity = verify_source(evidence.documento_fonte_id)
        if not integrity["disponivel"] or not integrity["integro"]:
            diagnostics.append(_diagnostic("fonte_alterada" if integrity["disponivel"] else "fonte_ausente",
                "fonte", "bloqueio", "objetiva", f"A fonte da evidência {evidence.id} está indisponível ou diverge do hash registrado.",
                part=evidence.parte, location={"documento_fonte_id": evidence.documento_fonte_id,
                "pagina": evidence.pagina, "identificador": evidence.identificador_documento}, evidence=[evidence.id],
                action="Localize a fonte original íntegra e registre novamente a evidência."))

    if content_refs and answer_refs:
        if any(not _same_scope(item, answer_refs[0]) for item in content_refs):
            diagnostics.append(_diagnostic("escopo_divergente", "identidade", "bloqueio", "objetiva",
                "Prova, cargo, código ou versão da evidência de conteúdo diverge do gabarito.",
                evidence=content_ids + answer_ids, action="Selecione evidências do mesmo escopo documental."))
    if content.get("imagem_path"):
        resource = _resource_path(content["imagem_path"])
        if not resource or not resource.is_file():
            diagnostics.append(_diagnostic("recurso_visual_ausente", "estrutura", "bloqueio", "objetiva",
                "O recurso visual referenciado não está disponível.", part="recurso_visual",
                action="Restaure a imagem derivada do original e registre sua origem."))
        elif "imagem_sha256" not in content:
            diagnostics.append(_diagnostic("recurso_visual_integridade_desconhecida", "estrutura", "bloqueio", "objetiva",
                "Esta versão legada não registra o hash do recurso visual.", part="recurso_visual",
                action="Confira o derivado com o original e crie uma versão que registre seu hash."))
        elif not content.get("imagem_sha256") or _hash_file(resource) != content["imagem_sha256"]:
            diagnostics.append(_diagnostic("recurso_visual_alterado", "estrutura", "bloqueio", "objetiva",
                "O recurso visual diverge do hash da versão.", part="recurso_visual",
                action="Gere novamente o derivado a partir da fonte íntegra e crie uma nova versão."))

    objective_by_text = {
        "Enunciado vazio": ("enunciado_vazio", "O enunciado está vazio."),
        "Gabarito incompatível com o tipo da questão": ("gabarito_incompativel", "O gabarito é incompatível com o tipo da questão."),
        "Alternativas ausentes ou com letras repetidas": ("alternativas_invalidas", "Alternativas estão ausentes, duplicadas ou fora de sequência."),
        "Alternativa do gabarito ausente": ("alternativa_gabarito_ausente", "A alternativa indicada pelo gabarito não existe."),
    }
    alert_by_text = {
        "Possíveis alternativas fundidas": ("alternativas_possivelmente_fundidas", "Há sinal heurístico de alternativas fundidas."),
        "Rodapé misturado ao conteúdo": ("rodape_misturado_suspeito", "Há sinal heurístico de rodapé misturado ao conteúdo."),
        "Comando aparentemente incompleto": ("comando_incompleto_suspeito", "Há sinal heurístico de comando incompleto."),
    }
    alerts = []
    for problem in problemas_estrutura(content):
        if problem in objective_by_text:
            code, message = objective_by_text[problem]
            diagnostics.append(_diagnostic(code, "estrutura", "bloqueio", "objetiva", message,
                action="Corrija a estrutura em uma nova versão."))
        else:
            code, message = alert_by_text.get(problem, ("estrutura_suspeita", problem))
            alerts.append(_diagnostic(code, "estrutura", "aviso", "suspeita", message,
                action="Confira o sinal com o original; não corte ou rejeite sem evidência."))

    evidence_fingerprint = _evidence_fingerprint(all_evidence)
    unresolved_alerts = []
    for alert in alerts:
        resolution = read_batch.resolution(version.id, alert['codigo'], DIAGNOSTIC_RULE_VERSION, evidence_fingerprint)
        if resolution:
            alert["resolucao"] = {
                "decisao": resolution.decisao,
                "responsavel": resolution.responsavel_declarado,
                "justificativa": resolution.justificativa,
                "resolvida_em": resolution.criada_em.isoformat() if resolution.criada_em else None,
            }
            if resolution.decisao == "erro_confirmado":
                alert["severidade"] = "bloqueio"
                alert["natureza"] = "erro_confirmado"
                diagnostics.append(alert)
            else:
                alert["severidade"] = "informativo"
                alert["natureza"] = "suspeita_descartada_com_evidencia"
                diagnostics.append(alert)
        else:
            unresolved_alerts.append(alert)
            diagnostics.append(alert)

    blocked = [item for item in diagnostics if item["severidade"] == "bloqueio"]
    decisions = [item for item in diagnostics if item["natureza"] == "decisao_humana"] + unresolved_alerts
    automatic = get_automatic_validation(version.id)
    explicit_human_rejection = (
        (content_review and content_review.decisao == "rejeitado") or
        (answer_review and answer_review.decisao in {"conflitante", "anulado"})
    )
    if automatic["valida"] and not explicit_human_rejection:
        # Certificado automático substitui apenas a pendência humana; não
        # dispensa bloqueios objetivos nem rejeições explícitas.
        decisions = [item for item in decisions if item.get("natureza") != "decisao_humana"]
        blocked = [item for item in blocked if item.get("natureza") != "decisao_humana"]
        diagnostics = [item for item in diagnostics if item.get("natureza") != "decisao_humana"]
        # O confronto exato dos campos e o fac-símile íntegro resolvem os
        # sinais heurísticos de extração; erros confirmados nunca são dispensados.
        for alert in unresolved_alerts:
            alert["severidade"] = "informativo"
            alert["natureza"] = "verificacao_automatica"
            alert["resolucao"] = {"decisao": "conteudo_preservado_na_fonte", "origem": "automatica"}
        decisions = [item for item in decisions if item not in unresolved_alerts]
        unresolved_alerts = []
    released = not blocked and not decisions and (bool(content_refs and answer_refs) or automatic["valida"])
    if any(item["codigo"] in {"fonte_alterada", "fonte_ausente", "escopo_divergente", "snapshot_desatualizado"} for item in diagnostics):
        stage = "identidade_fonte"
    elif any(item["etapa"] == "numeracao" for item in diagnostics):
        stage = "numeracao"
    elif any(item["etapa"] == "estrutura" and item["severidade"] == "bloqueio" for item in diagnostics):
        stage = "estrutura"
    elif unresolved_alerts:
        stage = "revisao_alertas"
    elif released:
        stage = "liberada"
    elif not content_review or content_review.decisao != "conferido":
        stage = "revisao_conteudo"
    elif not answer_review or answer_review.decisao != "definitivo_confirmado":
        stage = "confirmacao_gabarito"
    else:
        stage = "liberada" if released else "bloqueada"
    return {
        "versao_id": version.id,
        "versao_avaliada": version.numero_versao,
        "versao_regra": DIAGNOSTIC_RULE_VERSION,
        "tipo_liberacao": "automatica" if automatic["valida"] else ("humana" if released else None),
        "estado_validacao_automatica": "verificado_automaticamente" if automatic["valida"] else "nao_verificado",
        "validacao_automatica": automatic,
        "liberada": released,
        "etapa_principal": stage,
        "pendencias": diagnostics,
        "bloqueios_objetivos": blocked,
        "alertas": alerts,
        "decisoes_humanas_necessarias": decisions,
        "estado_conteudo": "verificado_automaticamente" if automatic["valida"] else content_review.decisao if content_review else version.revisao_conteudo or "nao_verificado",
        "estado_gabarito": "verificado_automaticamente" if automatic["valida"] else answer_review.decisao if answer_review else version.revisao_gabarito or "desconhecido",
        "denominadores": {"questoes": 1, "versoes": 1, "documentos": len({item.documento_fonte_id for item in all_evidence})},
    }


def resolve_diagnostic(
    version_id: int, *, code: str, decision: str, reviewer: str,
    rationale: str, evidence_ids: list[int],
) -> int:
    """Registra decisão humana sobre suspeita, sem permitir dispensar erro objetivo."""
    init_db()
    if decision not in {"alerta_descartado", "erro_confirmado"} or not reviewer.strip() or not rationale.strip():
        raise ValueError("Decisão, responsável e justificativa são obrigatórios.")
    version = QuestaoVersao.get_or_none(QuestaoVersao.id == version_id)
    if version is None or not _version_is_current(version):
        raise ValueError("A versão mudou ou não existe; reavalie o snapshot atual antes de resolver alertas.")
    assessment = assess_version(version_id)
    alert = next((item for item in assessment["alertas"] if item["codigo"] == code), None)
    if alert is None or alert["natureza"] != "suspeita":
        raise ValueError("O código não é uma suspeita ativa desta versão; bloqueios objetivos não podem ser dispensados.")
    references = _evidence_for_decision(version_id, evidence_ids, CONTENT_PARTS | {"gabarito"})
    _validate_evidence_sources(references)
    fingerprint = _evidence_fingerprint(list(EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == version_id)))
    with db.atomic():
        existing = ResolucaoDiagnostico.get_or_none(
            (ResolucaoDiagnostico.questao_versao == version_id)
            & (ResolucaoDiagnostico.codigo == code)
            & (ResolucaoDiagnostico.versao_regra == DIAGNOSTIC_RULE_VERSION)
            & (ResolucaoDiagnostico.decisao == decision)
            & (ResolucaoDiagnostico.responsavel_declarado == reviewer.strip())
            & (ResolucaoDiagnostico.justificativa == rationale.strip())
            & (ResolucaoDiagnostico.fingerprint_evidencias == fingerprint)
        )
        if existing:
            return existing.id
        return ResolucaoDiagnostico.create(
            questao_versao=version_id, codigo=code, versao_regra=DIAGNOSTIC_RULE_VERSION,
            decisao=decision, responsavel_declarado=reviewer.strip(),
            justificativa=rationale.strip(), evidencia_json=json.dumps([item.id for item in references]),
            fingerprint_evidencias=fingerprint,
        ).id


def version_is_eligible(version: QuestaoVersao) -> bool:
    return bool(assess_version(version.id)["liberada"])
