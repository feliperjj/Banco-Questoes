"""Persistência de importações com evidências do caderno e do gabarito."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from functools import lru_cache
from functools import wraps
from contextvars import ContextVar

from src.config import IMAGE_DIR, ROOT_DIR
from src.importador.catalogo import carregar_catalogo, normalizar_chave
from src.importador.gabarito_fonte import extract_answer_evidence
from src.importador.pdf_fonte import extract_pdf_source
from src.importador.pdf_render import rendering_batch
from src.importador.perfis.documentos import classificar_caderno, classificar_gabarito
from src.importador.validacao import normalizar_gabarito
from src.models.provenance_service import source_pdf


_new_assets = ContextVar("importacao_new_assets", default=None)


def _rollback_new_assets(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        created = []
        token = _new_assets.set(created)
        try:
            return function(*args, **kwargs)
        except Exception as error:
            for path in created:
                try:
                    path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    error.add_note(f"Não foi possível remover o recurso temporário {path}: {cleanup_error}")
            raise
        finally:
            _new_assets.reset(token)
    return wrapped


class ImportacaoCancelada(RuntimeError):
    """Cancelamento cooperativo que preserva o lote e a transação."""


def _check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise ImportacaoCancelada("Importação cancelada com segurança.")


@rendering_batch
def _extract_geometry(path, questions, asset_dir):
    return extract_pdf_source(path, expected_questions=questions, asset_dir=asset_dir)


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=512)
def _metadata_cached(path: str, modified_ns: int, size: int,
                     page_number: int) -> tuple[tuple[float, float], int]:
    # Same PDF pages are referenced by many question and context evidences.
    # Include file identity in the cache key so a changed source cannot reuse
    # stale page geometry in a later import.
    with source_pdf(Path(path)) as pdf:
        page = pdf.pages[page_number - 1]
        return (float(page.width), float(page.height)), int(getattr(page, "rotation", 0) or 0) % 360


def _metadata(path: Path, page_number: int) -> tuple[tuple[float, float], int]:
    resolved = path.resolve()
    stat = resolved.stat()
    return _metadata_cached(str(resolved), stat.st_mtime_ns, stat.st_size, page_number)


def _answer_status(path: Path) -> str:
    from src.importador.pdf_texto import _corrigir_encoding_ocr
    with source_pdf(path) as pdf:
        text = "\n".join(_corrigir_encoding_ocr(page.extract_text() or "") for page in pdf.pages)
    from .perfis.documentos import situacao_gabarito
    return situacao_gabarito(text)


def _geometry_issues_for_number(issues: list[str], number: int) -> list[str]:
    """Apply numbered geometry diagnostics only to the affected question."""
    relevant = []
    for issue in issues:
        match = re.fullmatch(r"(?:ancora_nao_encontrada|marcador_duplicado):(\d+)", issue)
        if match:
            if int(match.group(1)) == number:
                relevant.append(issue)
            continue
        relevant.append(issue)
    return relevant


def _catalogue_binding(book: Path, answer: Path) -> tuple[str, dict] | tuple[None, None]:
    sample_root = (ROOT_DIR / "samples").resolve()
    try:
        key = normalizar_chave(book.resolve().relative_to(sample_root).as_posix())
        catalog = carregar_catalogo(ROOT_DIR / "config" / "gabaritos.json")
        entry = catalog.get(key)
        if not entry or entry.get("confirmado") is not True:
            return None, None
        allowed = [sample_root / entry["gabarito"]]
        if entry.get("complemento"):
            allowed.append(sample_root / entry["complemento"])
        if answer.resolve() in {path.resolve() for path in allowed}:
            return key, entry
    except (OSError, ValueError, KeyError):
        pass
    # Cópias baixadas podem diferir apenas em metadados/marca de download.
    # O código impresso só reduz os candidatos; a decisão exige equivalência
    # de todas as páginas, texto normalizado e pixels, nos dois documentos.
    from .perfis.documentos import _metadados
    from .comparacao_fontes import comparar_documentos
    with source_pdf(book) as document:
        codes = set(_metadados(document.pages[0].extract_text() or "").get("codigo", ()))
    catalog = carregar_catalogo(ROOT_DIR / "config" / "gabaritos.json")
    matches = []
    book_hash = _hash(book)
    for key, entry in catalog.items():
        if entry.get("confirmado") is not True:
            continue
        entry_codes = set(_metadados("\n".join(str(entry.get(field) or "") for field in ("codigo", "cargo", "prova"))).get("codigo", ()))
        reference = (sample_root / key).resolve()
        if not reference.is_relative_to(sample_root) or not reference.is_file():
            continue
        if not codes.intersection(entry_codes) and book_hash != _hash(reference):
            continue
        if comparar_documentos(book, reference) is None:
            continue
        allowed = [entry["gabarito"], *([entry["complemento"]] if entry.get("complemento") else [])]
        if any((sample_root / path).resolve().is_relative_to(sample_root)
               and (sample_root / path).is_file()
               and comparar_documentos(answer, sample_root / path) is not None for path in allowed):
            matches.append((key, entry))
    return matches[0] if len(matches) == 1 else (None, None)


def _scope(book: Path, answer: Path, catalog_key: str | None, entry: dict | None,
           *, codigo="", cargo="", versao="") -> tuple[dict | None, dict]:
    from .perfis.documentos import _normalizar, normalizar_versao, versao_da_selecao
    if catalog_key and entry:
        from .perfis.documentos import cabecalho_codigo_cargo
        header = cabecalho_codigo_cargo(str(entry.get("cargo") or ""))
        roles = {_normalizar(entry.get("cargo") or "")}
        if header:
            roles.add(_normalizar(header[1]))
        if cargo and entry.get("cargo") and _normalizar(cargo) not in roles:
            return None, {}
        code = entry.get("codigo") or entry.get("prova")
        if codigo and code and _normalizar(codigo) != _normalizar(code):
            return None, {}
        if versao:
            from .pdf_texto import extrair_texto_pdf
            known_versions = (classificar_caderno(extrair_texto_pdf(str(book))).metadados or {}).get("versao", ())
            if normalizar_versao(versao) not in known_versions:
                return None, {}
        reference_book = (ROOT_DIR / "samples" / catalog_key).resolve()
        digest = _hash(reference_book)
        identity = {"catalogo_chave": catalog_key,
                    "catalogo_sha256": _hash(ROOT_DIR / "config" / "gabaritos.json")}
        from .comparacao_fontes import comparar_documentos
        aliases = {}
        if book.resolve() != reference_book:
            aliases["caderno"] = comparar_documentos(book, reference_book)
            if aliases["caderno"] is None:
                return None, {}
        reference_answers = [ROOT_DIR / "samples" / entry["gabarito"]]
        if entry.get("complemento"):
            reference_answers.append(ROOT_DIR / "samples" / entry["complemento"])
        if answer.resolve() not in {path.resolve() for path in reference_answers}:
            aliases["gabarito"] = next((proof for path in reference_answers
                if (proof := comparar_documentos(answer, path)) is not None), None)
            if aliases["gabarito"] is None:
                return None, {}
        if aliases:
            identity["equivalencia_documental"] = aliases
        return ({"prova": entry.get("prova") or "pdf:" + digest,
                 "cargo": entry.get("cargo") or "caderno-unico",
                 "codigo": entry.get("codigo") or entry.get("prova") or "caderno-unico",
                 "versao": "sha256:" + digest},
                identity)

    from src.importador.pdf_texto import extrair_texto_pdf
    proof_profile = classificar_caderno(extrair_texto_pdf(str(book)))
    with source_pdf(answer) as document:
        answer_profile = classificar_gabarito("\n".join(page.extract_text() or "" for page in document.pages))
    proof_meta, answer_meta = proof_profile.metadados or {}, answer_profile.metadados or {}
    common = {name: sorted(set(proof_meta.get(name, ())) & set(answer_meta.get(name, ())))
              for name in ("codigo", "cargo", "versao")}
    selected = {"codigo": codigo.upper(), "cargo": _normalizar(cargo), "versao": normalizar_versao(versao)}
    if versao_da_selecao(codigo):
        selected["codigo"] = ""
        selected["versao"] = selected["versao"] or versao_da_selecao(codigo)
    for name, value in selected.items():
        if value:
            common[name] = [item for item in common[name] if item == value]
    if any(len(values) != 1 for values in common.values()):
        return None, {}
    scope = {"prova": common["codigo"][0], "codigo": common["codigo"][0],
             "cargo": common["cargo"][0], "versao": common["versao"][0]}
    return scope, {}


def _copy_assets(assets: list[dict], destination: Path, prefix: str) -> list[dict]:
    saved = []
    for asset in assets:
        source = Path(asset["path"])
        if not source.is_file() or _hash(source) != asset["sha256"]:
            raise ValueError("Um fac-símile foi alterado antes de ser salvo.")
        target = destination / f"{prefix}-{source.name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and _hash(target) != asset["sha256"]:
            raise ValueError("Um fac-símile existente diverge do original; ele foi preservado.")
        if not target.exists():
            shutil.copy2(source, target)
            created = _new_assets.get()
            if created is not None:
                created.append(target)
        saved.append({**asset, "path": str(target.resolve())})
    return saved


def _combined_preview(context, question, destination, number):
    """Preserva contexto visual também na consulta de versões ainda pendentes."""
    from PIL import Image
    from io import BytesIO
    frames = []
    for item in context + question:
        path = Path(item['path'])
        if _hash(path) != item['sha256']:
            raise ValueError('Um recurso do contexto foi alterado antes da apresentação.')
        with Image.open(path) as image:
            frames.append(image.convert('RGB').copy())
    if not frames:
        return None
    combined = Image.new('RGB', (max(frame.width for frame in frames), sum(frame.height for frame in frames) + 12 * (len(frames) - 1)), 'white')
    top = 0
    for frame in frames:
        combined.paste(frame, (0, top))
        top += frame.height + 12
    output = BytesIO()
    combined.save(output, format='PNG', optimize=True)
    data = output.getvalue()
    digest = sha256(data).hexdigest()
    target = destination / f'q{number}-context-preview-{digest[:16]}.png'
    if target.exists() and _hash(target) != digest:
        raise ValueError('Um recurso contextual existente foi alterado; ele foi preservado.')
    if not target.exists():
        target.write_bytes(data)
        if (created := _new_assets.get()) is not None:
            created.append(target)
    return str(target.resolve())


def _same_question_snapshot(question: dict, version) -> bool:
    try:
        snapshot = json.loads(version.conteudo_json)
        fields = ("numero_oficial", "enunciado", "texto_apoio", "tipo", "disciplina", "topico",
                  "banca", "ano", "cargo", "orgao", "dificuldade", "gabarito", "comentario", "imagem_path")
        incoming = dict(question)
        incoming.setdefault("numero_oficial", incoming.get("numero"))
        if any(snapshot.get(name) != incoming.get(name) for name in fields):
            return False
        alternatives = sorted(({"letra": item.get("letra"), "texto": item.get("texto", "")}
                              for item in (incoming.get("alternativas") or [])), key=lambda item: item["letra"] or "")
        if snapshot.get("alternativas", []) != alternatives:
            return False
        image_path = snapshot.get("imagem_path")
        if image_path and "imagem_sha256" in snapshot:
            path = Path(image_path)
            if not path.is_file() or _hash(path) != snapshot["imagem_sha256"]:
                return False
        return True
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _reconcile_eligibility(result, ids):
    from src.db.models import QuestaoVersao
    from src.models.provenance_service import assess_version
    result["verificadas"] = 0
    result["certificadas"] = 0
    result["elegibilidade"] = []
    pending = {item["numero"] for item in result["pendentes"]}
    for question_id in ids:
        version = (QuestaoVersao.select().where(QuestaoVersao.questao == question_id)
                   .order_by(QuestaoVersao.numero_versao.desc()).get())
        assessment = assess_version(version.id)
        eligible = bool(assessment["liberada"])
        result["verificadas"] += bool(assessment["validacao_automatica"]["valida"])
        result["certificadas"] += eligible
        number = json.loads(version.conteudo_json).get("numero_oficial")
        reasons = [item["codigo"] for item in assessment["pendencias"]]
        result["elegibilidade"].append({"questao_id": question_id, "versao_id": version.id,
            "numero": number, "elegivel": eligible, "motivos": reasons})
        if not eligible and number not in pending:
            result["pendentes"].append({"numero": number, "motivo": ";".join(reasons)})
    result["pendentes"] = [item for item in result["pendentes"] if not any(
        row["numero"] == item["numero"] and row["elegivel"] for row in result["elegibilidade"])]


def _same_import_scope(parameters, scope, requested):
    saved = parameters.get("associacao_escopo")
    if saved is not None or scope is not None:
        return saved == scope
    return ({key: value for key, value in parameters.get("escopo_solicitado", {}).items() if value}
            == {key: value for key, value in requested.items() if value})


def _find_existing_import(book: Path, answer: Path, scope, requested):
    from src.db.models import DocumentoFonte, ProvaCadastrada, ProvaCadastradaQuestao

    book_source = DocumentoFonte.get_or_none(DocumentoFonte.sha256 == _hash(book))
    answer_source = DocumentoFonte.get_or_none(DocumentoFonte.sha256 == _hash(answer))
    if book_source is None or answer_source is None:
        return None
    proofs = (ProvaCadastrada.select()
              .where((ProvaCadastrada.documento_fonte_questoes == book_source.id)
                     & (ProvaCadastrada.documento_fonte_gabarito == answer_source.id)
                     & (ProvaCadastrada.ativa == True))
              .order_by(ProvaCadastrada.id.desc()))
    unidentified_scope = False
    for proof in proofs:
        links = list(ProvaCadastradaQuestao.select()
                     .where(ProvaCadastradaQuestao.prova_cadastrada == proof.id)
                     .order_by(ProvaCadastradaQuestao.ordem))
        parameters = [json.loads(link.questao_versao.execucao_extracao.parametros_json or "{}")
                      if link.questao_versao_id and link.questao_versao.execucao_extracao_id else {} for link in links]
        if links and any("associacao_escopo" not in item and "escopo_solicitado" not in item for item in parameters):
            unidentified_scope = True
            continue
        if links and all(_same_import_scope(item, scope, requested) for item in parameters):
            return proof, links
    if unidentified_scope:
        raise ValueError("Este par já tem uma prova sem escopo de importação registrado. Confira a prova existente antes de reimportar; nenhum registro foi duplicado.")
    return None


def _find_partial_import(book, answer_hash, scope, requested, answer_path):
    from src.db.models import DocumentoFonte, QuestaoVersao, ExecucaoExtracao, EvidenciaQuestao
    from src.models import questoes_repo as repo
    source = DocumentoFonte.get_or_none(DocumentoFonte.sha256 == _hash(book))
    if source is None:
        return {}
    answer_source = DocumentoFonte.get_or_none(DocumentoFonte.sha256 == answer_hash)
    versions = (QuestaoVersao.select(QuestaoVersao, ExecucaoExtracao)
                .join(ExecucaoExtracao)
                .where(QuestaoVersao.documento_fonte == source.id)
                .order_by(QuestaoVersao.id.desc()))
    found, seen = {}, set()
    for version in versions:
        params = json.loads(version.execucao_extracao.parametros_json or "{}")
        if not _same_import_scope(params, scope, requested):
            continue
        saved_hash = params.get("hash_fonte_gabarito")
        if saved_hash != answer_hash:
            if saved_hash is not None:
                continue
            bound = answer_source and EvidenciaQuestao.select().where(
                (EvidenciaQuestao.questao_versao == version.id) & (EvidenciaQuestao.parte == "gabarito")
                & (EvidenciaQuestao.documento_fonte == answer_source.id)).exists()
            if not bound:
                if params.get("fonte_gabarito") == answer_path:
                    raise ValueError("O lote parcial antigo não registra o hash do gabarito nem evidência suficiente para comprová-lo. Retome o rascunho ou confira os registros existentes; nenhuma questão foi duplicada.")
                continue
        if version.questao_id in seen or not version.questao.ativa:
            continue
        seen.add(version.questao_id)
        current = repo.ultima_versao(version.questao_id)
        if current.id != version.id:
            raise ValueError("A versão atual de uma questão do lote parcial pertence a outra revisão. Confira essa versão antes de retomar a importação.")
        number = json.loads(version.conteudo_json).get("numero_oficial")
        if not isinstance(number, int) or isinstance(number, bool) or number in found:
            raise ValueError("O lote parcial tem numeração ausente ou ambígua. Confira os registros antes de reimportar; nenhuma questão foi duplicada.")
        found[number] = version
    return found


@_rollback_new_assets
@rendering_batch
def salvar_lote_verificado(questoes: list[dict], *, caminho_caderno: str,
                            caminho_gabarito: str | None, nome_prova: str,
                            instrucoes_prova: str = "", perfil_caderno: str = "",
                            codigo_gabarito: str = "", cargo_gabarito: str = "",
                            versao_gabarito: str = "",
                            extraction_metadata: dict | None = None,
                            prova: dict | None = None, cancel_event=None,
                            allow_new_version: bool = False) -> dict:
    """Salva a lista como lote atômico e tenta certificar somente evidências completas."""
    from src.db.database import db, init_db
    from src.db.models import QuestaoVersao
    from src.models import questoes_repo as repo
    from src.models.provenance_service import (
        begin_source_verification_batch,
        add_evidence, create_source,
        end_source_verification_batch, record_automatic_validation,
        preliminary_allowed_for_study,
    )

    init_db()
    _check_cancelled(cancel_event)
    book = Path(caminho_caderno).expanduser().resolve()
    answer = Path(caminho_gabarito).expanduser().resolve() if caminho_gabarito else None
    pdf_pair = book.suffix.lower() == ".pdf" and answer is not None and answer.suffix.lower() == ".pdf"
    geometry = answer_evidence = None
    scope = catalog_identity = None
    # Lotes revisados manualmente ainda podem ser salvos sem um caminho-fonte
    # acessível; use um identificador estável do caminho para staging nesse
    # caso, sem confundir esse identificador com a identidade documental.
    destination_key = _hash(book) if book.is_file() else sha256(str(book).encode("utf-8")).hexdigest()
    destination = IMAGE_DIR / "importacao-v1" / destination_key[:16]
    if pdf_pair:
        geometry = _extract_geometry(book, questoes, destination / "staging")
        _check_cancelled(cancel_event)
        answer_evidence = extract_answer_evidence(answer, codigo_prova=codigo_gabarito or None,
            cargo=cargo_gabarito or None, versao=versao_gabarito or None, expected_answers={q["numero"]: None for q in questoes
                if isinstance(q.get("numero"), int)})
        key, entry = _catalogue_binding(book, answer)
        scope, catalog_identity = _scope(book, answer, key, entry,
            codigo=codigo_gabarito, cargo=cargo_gabarito, versao=versao_gabarito)
        answer_status = _answer_status(answer)
    else:
        answer_status = "desconhecido"

    by_number = {item.get("numero"): item for item in (geometry or {}).get("questions", [])}
    responses = (answer_evidence or {}).get("answers", {})
    prepared_questions, assets_by_number = [], {}
    if geometry:
        for question in questoes:
            _check_cancelled(cancel_event)
            item = dict(question)
            number = item.get("numero")
            source_item = by_number.get(number)
            answer_item = responses.get(number)
            # The extracted key must be part of the exact version snapshot
            # that the provenance authority evaluates. Keep user-entered keys
            # intact; conflicts never appear in ``responses`` because the
            # answer extractor omits them.
            if item.get("gabarito") is None and answer_item:
                item["gabarito"] = normalizar_gabarito(answer_item["resposta"], item.get("tipo", ""))
            if source_item and source_item.get("assets"):
                saved = _copy_assets(source_item["assets"], destination, f"q{number}")
                assets_by_number[number] = {"questao": saved, "contexto": []}
                # Um recorte contextual já extraído pode conter a tabela ou
                # figura completa. A geometria ainda será verificada abaixo;
                # uma fronteira ambígua não pode substituir esse recurso.
                item["imagem_path"] = item.get("imagem_path") or saved[0]["path"]
            if source_item and source_item.get("context_assets"):
                saved_context = _copy_assets(source_item["context_assets"], destination, f"q{number}-ctx")
                assets_by_number.setdefault(number, {"questao": [], "contexto": []})["contexto"] = saved_context
                if not question.get('imagem_path') and assets_by_number[number]['questao']:
                    item['imagem_path'] = _combined_preview(saved_context,
                        assets_by_number[number]['questao'], destination, number)
            prepared_questions.append(item)
    else:
        prepared_questions = [dict(question) for question in questoes]

    metadata = dict(extraction_metadata or {})
    metadata.setdefault("extractor", "importacao_dois_funis_v1")
    metadata.setdefault("profile", perfil_caderno or "reconhecimento_assistido")
    metadata.setdefault("profile_version", "1")
    from .perfis.registro import obter_perfil
    registered = obter_perfil(metadata["profile"])
    if registered:
        metadata["profile_version"] = registered.versao
    metadata.setdefault("parameters", {})
    from .perfis.documentos import _normalizar, normalizar_versao
    requested = {"codigo": _normalizar(codigo_gabarito), "cargo": _normalizar(cargo_gabarito),
                 "versao": normalizar_versao(versao_gabarito)}
    answer_hash = _hash(answer) if pdf_pair else None
    preliminary_allowed = (answer_status == "preliminar" and preliminary_allowed_for_study(
        catalog_identity.get("catalogo_chave") if isinstance(catalog_identity, dict) else None,
        destination_key, answer_hash))
    metadata["parameters"] = {**metadata["parameters"],
        "fonte_gabarito": str(answer) if answer else None,
        "hash_fonte_gabarito": answer_hash,
        "escopo_solicitado": requested,
        "associacao_escopo": scope,
        "perfil_caderno": perfil_caderno,
        "perfis_gabarito_por_numero": sorted({item.get("metodo", "") for item in responses.values()}),
    }

    result = {"ids": [], "certificadas": 0, "pendentes": [], "geometria_issues": (geometry or {}).get("issues", [])}
    full_new_pair = bool(prova and len(prova.get("lote_indices", [])) == len(questoes)
                         and len(prova.get("composicao", [])) == len(questoes))
    existing_import = _find_existing_import(book, answer, scope, requested) if pdf_pair and full_new_pair else None
    existing_links = None
    partial, unchanged_partial = {}, set()
    if existing_import:
        existing_proof, candidate_links = existing_import
        identical = (len(candidate_links) == len(prepared_questions) and all(
            link.questao_versao_id and _same_question_snapshot(question, link.questao_versao)
            for question, link in zip(prepared_questions, candidate_links)
        ))
        if identical:
            result["ids"] = [link.questao_id for link in candidate_links]
            result["prova_id"] = existing_proof.id
            result["reutilizada"] = True
            reuse_token = begin_source_verification_batch()
            try:
                with db.atomic():
                    create_source(book, tipo="caderno_questoes")
                    create_source(answer, tipo="pdf")
                    _reconcile_eligibility(result, result["ids"])
                    _check_cancelled(cancel_event)
            finally:
                end_source_verification_batch(reuse_token)
            return result
        if not allow_new_version:
            raise ValueError("fonte_ja_importada_com_conteudo_diferente: marque a opção de criar nova versão para este par.")
        existing_links = candidate_links
    elif pdf_pair and full_new_pair:
        partial = _find_partial_import(book, answer_hash, scope, requested, str(answer))
        if partial:
            numbers = [question.get("numero") for question in prepared_questions]
            if len(set(numbers)) != len(numbers) or set(partial) - set(numbers):
                raise ValueError("A numeração do novo lote não corresponde ao salvamento parcial. Confira a composição antes de reimportar.")
            for question in prepared_questions:
                version = partial.get(question.get("numero"))
                if version and _same_question_snapshot(question, version):
                    unchanged_partial.add(question["numero"])
                elif version and not allow_new_version:
                    raise ValueError("fonte_ja_importada_com_conteudo_diferente: marque a opção de criar nova versão para este par.")
    try:
        verification_token = begin_source_verification_batch()
        with db.atomic():
            if partial:
                missing = [question for question in prepared_questions if question["numero"] not in partial]
                new_ids = iter(repo.criar_questoes_em_lote(missing, source_path=str(book), extraction_metadata=metadata) if missing else [])
                updates = [question for question in prepared_questions
                           if question["numero"] in partial and question["numero"] not in unchanged_partial]
                if updates:
                    from src.models.provenance_service import register_extraction
                    source_id = create_source(book, tipo="caderno_questoes")
                    extraction_id = register_extraction(source_id, extractor=metadata["extractor"],
                        profile=metadata["profile"], profile_version=metadata["profile_version"],
                        parameters=metadata["parameters"], diagnostics=metadata.get("diagnostics", []))
                    for question in updates:
                        repo.atualizar_questao(partial[question["numero"]].questao_id, question,
                                              source_id=source_id, extraction_id=extraction_id)
                    result["nova_versao"] = True
                ids = [partial[question["numero"]].questao_id if question["numero"] in partial else next(new_ids)
                       for question in prepared_questions]
                result["retomada_parcial"] = True
                result["reutilizadas"] = len(partial)
            elif existing_links is None:
                ids = repo.criar_questoes_em_lote(prepared_questions, source_path=str(book), extraction_metadata=metadata)
            else:
                from src.models.provenance_service import create_source, register_extraction
                source_id = create_source(book, tipo="caderno_questoes")
                extraction_id = register_extraction(
                    source_id,
                    extractor=metadata["extractor"],
                    extractor_version=metadata.get("extractor_version"),
                    profile=metadata.get("profile"),
                    profile_version=metadata.get("profile_version"),
                    parameters=metadata.get("parameters", {}),
                    diagnostics=metadata.get("diagnostics", []),
                )
                ids = [link.questao_id for link in existing_links]
                for question_id, question in zip(ids, prepared_questions):
                    repo.atualizar_questao(question_id, question, source_id=source_id, extraction_id=extraction_id)
                result["nova_versao"] = True
            result["ids"] = ids
            _check_cancelled(cancel_event)
            if prova:
                new_id_by_index = dict(zip(prova.get("lote_indices", []), ids))
                composition = []
                for item in prova.get("composicao", []):
                    data = dict(item["dados"])
                    data["_questao_id"] = item.get("questao_id") or new_id_by_index.get(item.get("lote_index"))
                    if not data["_questao_id"]:
                        raise ValueError("A composição original está incompleta; o salvamento foi revertido.")
                    composition.append(data)
                result["prova_id"] = repo.criar_prova_cadastrada(
                    prova["nome"], composition, arquivo_questoes=str(book),
                    arquivo_gabarito=str(answer) if answer else None,
                    instrucoes_prova=prova.get("instrucoes_prova", ""),
                )
            answer_source_id = create_source(answer, tipo="pdf") if pdf_pair else None
            result['situacao_gabarito'] = answer_status
            if not pdf_pair or not geometry or not answer_evidence or not scope:
                reason = ('gabarito_preliminar;' if answer_status == 'preliminar' else '') + 'evidencia_documental_incompleta'
                result["pendentes"] = [{"numero": question.get("numero"), "motivo": reason}
                                       for question in prepared_questions]
                _reconcile_eligibility(result, ids)
                return result

            for question, question_id in zip(prepared_questions, ids):
                _check_cancelled(cancel_event)
                number = question.get("numero")
                if number in unchanged_partial:
                    continue
                source_item = by_number.get(number)
                answer_item = responses.get(number)
                version = (QuestaoVersao.select().where(QuestaoVersao.questao == question_id)
                           .order_by(QuestaoVersao.numero_versao.desc()).first())
                if not source_item or not answer_item or not version:
                    result["pendentes"].append({"numero": number, "motivo": "evidencia_fisica_ausente"})
                    continue
                issues = list(source_item.get("issues", []))
                issues.extend(_geometry_issues_for_number(geometry.get("issues", []), number))
                if answer_evidence.get("issues"):
                    issues.extend(issue for issue in answer_evidence["issues"] if str(number) in issue)
                if not source_item.get("checks", {}).get("anchor_confirmed"):
                    issues.append("ancora_fisica_nao_confirmada")
                if not source_item.get("assets") or not source_item.get("checks", {}).get("region_valid"):
                    issues.append("facsimile_ou_regiao_invalida")
                if question.get("texto_apoio") and not source_item.get("context_regions"):
                    issues.append("contexto_sem_evidencia")
                if issues:
                    result["pendentes"].append({"numero": number, "motivo": ";".join(dict.fromkeys(issues))})
                    continue

                evidence_ids, question_images, context_images = [], [], []
                for region in source_item["regions"]:
                    page_size, rotation = _metadata(book, region["page"])
                    eid = add_evidence(version.id, version.documento_fonte_id, part="conteudo",
                        page=region["page"], bounds=tuple(region["bbox"]),
                        coordinate_system="pdf-point; origem superior esquerda", page_size=page_size,
                        rotation=rotation, scope=scope, excerpt=region.get("marker_text"))
                    evidence_ids.append(eid)
                    question_images.extend({**asset, "evidencia_id": eid} for asset in assets_by_number.get(number, {}).get("questao", [])
                                           if asset.get("region_index") == source_item["regions"].index(region))
                for region_index, region in enumerate(source_item.get("context_regions", [])):
                    page_size, rotation = _metadata(book, region["page"])
                    eid = add_evidence(version.id, version.documento_fonte_id, part="contexto",
                        page=region["page"], bounds=tuple(region["bbox"]),
                        coordinate_system="pdf-point; origem superior esquerda", page_size=page_size,
                        rotation=rotation, scope=scope, excerpt=region.get("text") or question.get("texto_apoio"))
                    evidence_ids.append(eid)
                    context_images.extend({**asset, "evidencia_id": eid}
                                           for asset in assets_by_number.get(number, {}).get("contexto", [])
                                           if asset.get("region_index") == region_index)

                region = answer_item["region"]
                page_size, answer_rotation = _metadata(answer, region["page"])
                answer_scope = {**scope, "situacao_gabarito": answer_status}
                answer_id = add_evidence(version.id, answer_source_id, part="gabarito",
                    page=region["page"], bounds=tuple(region["bbox"]),
                    coordinate_system="pdf-point; origem superior esquerda", page_size=page_size,
                    rotation=answer_rotation, scope=answer_scope,
                    excerpt=answer_item.get("scope_excerpt"))
                evidence_ids.append(answer_id)

                answer_value = normalizar_gabarito(answer_item["resposta"], question["tipo"])
                status = answer_status
                if answer_value == "Anulada":
                    status = "anulado"
                identity = {"conteudo_termos": [question["enunciado"]] +
                    [str(option.get("texto") or "") for option in question.get("alternativas") or []],
                    "gabarito_termos": [str(number), str(answer_item["resposta"])]}
                identity.update(catalog_identity)
                facsimile_question = [{**asset, "evidencia_id": asset["evidencia_id"]}
                                      for asset in question_images]
                manifest = {"regra": "pdf-geometrico-v1", "numero_oficial": number,
                    "gabarito": answer_value, "escopo": scope, "identidade": identity,
                    "checks": {key: True for key in ("identidade", "numero", "conteudo_completo", "alternativas", "contexto", "recursos", "gabarito")},
                    "apresentacao": {"modo": "facsimile", "questao": facsimile_question,
                                     "contexto": context_images},
                    "verificador": {"metodo": "ancora_geometrica_conteudo_e_gabarito", "versao": "importacao-dois-funis-v1"}}
                if (status == "preliminar" and not preliminary_allowed) or status == "anulado" or not facsimile_question:
                    result["pendentes"].append({"numero": number, "motivo": "gabarito_sem_status_liberavel_ou_facsimile"})
                    continue
                try:
                    record_automatic_validation(version.id, evidence_ids=evidence_ids, manifest=manifest)
                except ValueError as error:
                    result["pendentes"].append({"numero": number, "motivo": str(error)})
            _reconcile_eligibility(result, ids)
            _check_cancelled(cancel_event)
    finally:
        if "verification_token" in locals():
            end_source_verification_batch(verification_token)
    return result
