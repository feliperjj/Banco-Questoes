"""Synthetic deterministic resources shared by database and review tests."""

from pathlib import Path


def write_test_pdf(path: Path, width: int = 612, height: int = 792) -> Path:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << >> /Contents 4 0 R >>".encode(),
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def approve_with_evidence(question_id: int, source_path: Path, answer: str) -> int:
    from src.db.models import Questao
    from src.models import questoes_repo as repo
    from src.models.provenance_service import (
        add_evidence, create_question_version, create_source,
        review_answer, review_content,
    )

    write_test_pdf(source_path)
    question = Questao.get_by_id(question_id)
    if not question.numero_oficial:
        # IDs are used only to choose distinct synthetic test numbers; production
        # code must always obtain this value from the document's explicit marker.
        repo.atualizar_questao(question_id, {"numero_oficial": question_id})
    source_id = create_source(source_path, tipo="pdf")
    version_id = create_question_version(question_id, source_id=source_id)
    scope = {"prova": "fixture", "cargo": "fixture", "codigo": "T1", "versao": "1"}
    content_evidence = add_evidence(
        version_id, source_id, part="conteudo", page=1,
        bounds=(0, 0, 612, 396), coordinate_system="pdf-point; origem superior esquerda",
        page_size=(612, 792), rotation=0, scope=scope,
        excerpt="Área sintética para conteúdo; não representa revisão do acervo.",
    )
    answer_evidence = add_evidence(
        version_id, source_id, part="gabarito", page=1,
        bounds=(0, 396, 612, 792), coordinate_system="pdf-point; origem superior esquerda",
        page_size=(612, 792), rotation=0,
        scope={**scope, "situacao_gabarito": "definitivo"},
        excerpt="Área sintética para gabarito; não representa revisão do acervo.",
    )
    review_content(
        version_id, decision="conferido", reviewer="Teste automatizado",
        rationale="Fixture sintético; não é revisão humana do acervo.",
        evidence_ids=[content_evidence],
    )
    review_answer(
        version_id, answer=answer, decision="definitivo_confirmado",
        reviewer="Teste automatizado",
        rationale="Fixture sintético; não é revisão humana do acervo.",
        evidence_ids=[answer_evidence],
    )
    return version_id
