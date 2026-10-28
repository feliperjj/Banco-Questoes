from tests.ui_wait import wait_ui_jobs
"""Regressões de recursos, escopo e roteamento percorrendo fontes reais."""
from hashlib import sha256
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QFileDialog

from src.db.database import init_db
from src.config import DB_PATH
from src.db.models import Questao
from src.models import questoes_repo as repo
from src.importador import lote_verificado as adapter
from src.importador.extrator import extrair_gabaritos_pdf
from src.importador.gabarito_fonte import extract_answer_evidence
from src.importador.servico import importar_caderno
from src.ui.pages.importacao import ImportacaoPage
from test_importacao_lote_verificado import _write_text_pdf


COMMON = ["Prova Teste", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo 1"]
QUESTION = ["QUESTAO 1", "Complete statement for official question one.",
            "A) Alpha option", "B) Bravo option", "C) Charlie option", "D) Delta option", "E) Echo option"]


@pytest.fixture(autouse=True)
def restore_database():
    from src.models.importacao_rascunho import remover_rascunho
    remover_rascunho()
    yield
    remover_rascunho()
    init_db(str(DB_PATH))


def write_pages(path, pages):
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        page_id = len(objects) + 1
        kids.append(f"{page_id} 0 R")
        stream = bytearray(b"BT /F1 10 Tf 50 740 Td ")
        for index, line in enumerate(lines):
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream.extend((b"0 -18 Td " if index else b"") + f"({safe}) Tj ".encode("ascii"))
        stream.extend(b"ET")
        objects.extend([f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id+1} 0 R >>".encode(),
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"])
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    data, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(data)
    return path


def wait_idle(page):
    if page.task.running:
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        page.task.idle.connect(loop.quit)
        timer.timeout.connect(loop.quit)
        timer.start(60000)
        loop.exec()
        page.task.idle.disconnect(loop.quit)
    assert not page.task.running, page.feedback.text()


@pytest.mark.parametrize("failure", ["preparation", "persistence"])
def test_rollback_preserva_recursos_anteriores_e_remove_somente_novos(tmp_path, monkeypatch, failure):
    init_db(str(tmp_path / "rollback.sqlite"))
    book = _write_text_pdf(tmp_path / "book.pdf", COMMON + QUESTION)
    answer = _write_text_pdf(tmp_path / "answers.pdf", COMMON + ["GABARITO DEFINITIVO", "1 A"])
    old, fresh, invalid = [tmp_path / name for name in ("old.png", "new.png", "invalid.png")]
    for file in (old, fresh, invalid):
        file.write_bytes(file.name.encode())
    destination = tmp_path / "assets" / "importacao-v1" / sha256(book.read_bytes()).hexdigest()[:16]
    destination.mkdir(parents=True)
    existing = destination / "q1-old.png"
    existing.write_bytes(old.read_bytes())
    assets = [{"path": str(file), "sha256": sha256(file.read_bytes()).hexdigest()} for file in (old, fresh)]
    if failure == "preparation":
        assets.append({"path": str(invalid), "sha256": "wrong"})
    monkeypatch.setattr(adapter, "IMAGE_DIR", tmp_path / "assets")
    monkeypatch.setattr(adapter, "_extract_geometry", lambda *args: {"questions": [{"numero": 1, "assets": assets}], "issues": []})
    def fail(*args, **kwargs):
        raise ValueError("persistence failure")
    monkeypatch.setattr(repo, "criar_questoes_em_lote", fail)
    question = {"numero": 1, "enunciado": "Complete statement", "tipo": "certo_errado", "gabarito": "Certo"}
    with pytest.raises(ValueError):
        adapter.salvar_lote_verificado([question], caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Rollback")
    assert existing.read_bytes() == old.read_bytes()
    assert not (destination / "q1-new.png").exists()
    assert Questao.select().count() == 0


def test_recorte_visual_nativo_preserva_tabela_e_formula(tmp_path, monkeypatch):
    from PIL import Image
    from src.config import TEST_ROOT
    from src.models.provenance_service import assess_version, version_is_eligible
    from src.models import questoes_repo as repo
    init_db(str(tmp_path / "visual.sqlite"))
    book = _write_text_pdf(tmp_path / "visual-book.pdf", COMMON + [
        "QUESTAO 1", "Observe a tabela a seguir e calcule x = 2 + 3.",
        "Valor       Resultado", "2 + 3       5",
        "A) Cinco", "B) Seis", "C) Sete", "D) Oito", "E) Nove",
    ], graphics=b"0 0 1 RG 45 605 220 36 re S 45 623 m 265 623 l S")
    answer = _write_text_pdf(tmp_path / "visual-answers.pdf", COMMON + ["GABARITO DEFINITIVO", "1 A"])
    lote = importar_caderno(str(book))
    assert len(lote) == 1
    assert "imagem_path" in lote[0], lote[0].get("aviso_importacao")
    path = Path(lote[0]["imagem_path"])
    if not path.is_absolute():
        path = TEST_ROOT / path
    with Image.open(path) as image:
        assert image.width > 100 and image.height > 60
        pixels = image.convert("RGB").tobytes()
        assert sum(b > 200 and r < 80 and g < 80 for r, g, b in zip(pixels[0::3], pixels[1::3], pixels[2::3])) > 100
    result = adapter.salvar_lote_verificado(lote, caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Tabela e fórmula")
    version = repo.ultima_versao(result["ids"][0])
    # A linha numérica interna não abre outra questão: o recorte completo
    # agora é confrontado com os pixels da região e com todo o texto.
    assert version_is_eligible(version), result
    assert result["certificadas"] == 1 and result["pendentes"] == []
    manifest = assess_version(version.id)["validacao_automatica"]["manifesto"]
    assert manifest["apresentacao"]["questao"]
    assert Path(repo.obter_questao(result["ids"][0])["imagem_path"]) == path
    from PySide6.QtWidgets import QMessageBox
    from src.ui.components.question_source_review import QuestionSourceReviewDialog
    warnings = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    review = QuestionSourceReviewDialog(result["ids"][0])
    review.proof_identity.setPlainText("A123")
    review.scope_cargo.setPlainText("analista de sistemas")
    review.scope_code.setPlainText("A123")
    review.scope_version.setPlainText("1")
    review.reviewer.setPlainText("Revisora de teste")
    review.rationale.setPlainText("Conferi a tabela, a formula e todas as alternativas na pagina original.")
    review._record_content_evidence()
    review.answer_pdf.load_path(str(answer))
    review.answer_status.setCurrentIndex(review.answer_status.findData("definitivo"))
    review._record_answer_evidence()
    review.content_decision.setCurrentIndex(review.content_decision.findData("conferido"))
    review._review_content()
    review.answer_decision.setCurrentIndex(review.answer_decision.findData("definitivo_confirmado"))
    review._review_answer()
    assert not warnings, warnings
    assert version_is_eligible(repo.ultima_versao(result["ids"][0])), assess_version(review.version_id)
    from src.ui.pages.execucao_prova import ExecucaoProvaPage
    proof_id = repo.criar_prova("Tabela e formula", {}, 1, 0)
    execution = ExecucaoProvaPage()
    execution.resize(960, 640)
    execution.iniciar(proof_id, "Tabela e formula")
    wait_ui_jobs()
    assert not execution.lbl_imagem.pixmap().isNull()
    assert "x = 2 + 3" in execution.lbl_enunciado.toPlainText()
    execution.salvar_resposta_temp(True, result["ids"][0], "A")
    assert repo.finalizar_tentativa(execution.tentativa_id, execution.respostas_memoria, 3)["acertos"] == 1
    execution.timer.stop()
    assert "x = 2 + 3" in lote[0]["enunciado"]


def test_ui_exige_escopo_reconhecido_e_bloqueia_versao_trocada(tmp_path, monkeypatch):
    init_db(str(tmp_path / "scope.sqlite"))
    book = _write_text_pdf(tmp_path / "book.pdf", COMMON + QUESTION)
    answer = write_pages(tmp_path / "multi-scope.pdf", [
        COMMON + ["GABARITO DEFINITIVO", "1 A"],
        ["Cargo: AUDITOR FISCAL", "Codigo B234", "Tipo 2", "GABARITO DEFINITIVO", "1 B"],
    ])
    files = iter((str(book), str(answer)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (next(files), ""))
    page = ImportacaoPage()
    page.selecionar_arquivo()
    wait_idle(page)
    page.selecionar_gabarito()
    wait_idle(page)
    assert not page.session.questoes[0]["gabarito"]
    assert "várias opções" in page.feedback.text()
    assert page.cargo_gabarito_input.findText("analista de sistemas") >= 0
    assert page.codigo_gabarito_input.findText("A123") >= 0
    assert page.versao_gabarito_input.findText("2") >= 0
    page.cargo_gabarito_input.setText("analista de sistemas")
    page.codigo_gabarito_input.setText("A123")
    page.versao_gabarito_input.setText("2")
    page._reprocessar_gabarito()
    wait_idle(page)
    assert "diverge do caderno" in page.feedback.text()
    assert not page.session.questoes[0]["gabarito"]
    page.versao_gabarito_input.setText("1")
    page._reprocessar_gabarito()
    wait_idle(page)
    assert page.session.questoes[0]["gabarito"] == "A", page.feedback.text()


@pytest.mark.parametrize("first,last,code,version", [("PROVA 2", "PROVA 1", "Prova 1", None),
    ("TIPO II", "TIPO I", None, "I")])
def test_coluna_fisica_segue_rotulo_da_versao_com_cabecalhos_invertidos(tmp_path, first, last, code, version):
    answer = _write_text_pdf(tmp_path / "reversed.pdf", [
        first + " " * 70 + last,
        "1 B" + " " * 80 + "1 A",
        "2 C" + " " * 80 + "2 D",
    ])
    assert extrair_gabaritos_pdf(str(answer), code, versao=version, usar_ocr=False) == {1: "A", 2: "D"}
    evidence = extract_answer_evidence(answer, codigo_prova=code, versao=version, expected_answers={1: None, 2: None})
    assert {n: item["resposta"] for n, item in evidence["answers"].items()} == {1: "A", 2: "D"}, evidence


def test_caderno_misto_preserva_paginas_e_nao_inventa_conteudo_sem_texto(tmp_path):
    book = write_pages(tmp_path / "mixed.pdf", [COMMON + QUESTION,
        ["TEXTO DE APOIO", "Passagem compartilhada completa para avaliar o item de julgamento.",
         "ITEM PARA JULGAMENTO", "2.", "Esta afirmacao corresponde ao contexto fornecido."], []])
    lote = importar_caderno(str(book))
    assert [q["numero"] for q in lote] == [1, 2]
    assert [q["tipo"] for q in lote] == ["multipla_escolha", "certo_errado"]
    assert "Passagem compartilhada" in lote[1]["texto_apoio"], lote.relatorio
    assert lote.relatorio["leitura_paginas"][2]["perfil"] == "sem_texto"
    assert any("sem texto" in warning for warning in lote.avisos)
    corrected = importar_caderno(str(book), perfis_paginas={1: "questoes_nomeadas_v2", 2: "certo_errado_contexto_v1"})
    assert [q["numero"] for q in corrected] == [1, 2]
    incompatible = importar_caderno(str(book), perfis_paginas={1: "certo_errado_contexto_v1", 2: "certo_errado_contexto_v1"})
    assert [q["numero"] for q in incompatible] == [2]


def test_ui_corrige_leitura_por_pagina_e_retoma_escolhas_no_rascunho(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from src.ui.components.import_choices import PageProfileChoices
    book = write_pages(tmp_path / "ui-mixed.pdf", [COMMON + QUESTION,
        ["TEXTO DE APOIO", "Passagem compartilhada completa para avaliar o item de julgamento.",
         "ITEM PARA JULGAMENTO", "2.", "Esta afirmacao corresponde ao contexto fornecido."]])
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(book), ""))
    page = ImportacaoPage()
    page.selecionar_arquivo()
    wait_idle(page)
    errors = []
    def choose():
        dialog = QApplication.activeModalWidget()
        try:
            table = dialog.findChild(PageProfileChoices)
            for row, profile in enumerate(("questoes_nomeadas_v2", "certo_errado_contexto_v1")):
                choice = table.cellWidget(row, 2)
                choice.setCurrentIndex(choice.findData(profile))
        except Exception as error:
            errors.append(str(error))
        finally:
            if dialog:
                dialog.accept()
    QTimer.singleShot(0, choose)
    page._conferir_paginas("caderno")
    wait_idle(page)
    assert not errors, errors
    assert [q["numero"] for q in page.session.questoes] == [1, 2]
    assert page._perfis_caderno_paginas == {1: "questoes_nomeadas_v2", 2: "certo_errado_contexto_v1"}
    assert page._salvar_rascunho()
    restored = ImportacaoPage()
    assert restored._perfis_caderno_paginas == page._perfis_caderno_paginas
    assert restored._paginas_caderno == page._paginas_caderno
    assert restored.session.questoes[1]["texto_apoio"] == page.session.questoes[1]["texto_apoio"]


def test_perfil_incompativel_nao_reintroduz_respostas_por_tabela_ou_ocr(tmp_path):
    from src.importador.gabaritos import extrair_gabaritos_pdf as read_answers
    answer = _write_text_pdf(tmp_path / "incompatible.pdf", ["1 - A", "2 - B", "3 - C"])
    calls = []
    result = read_answers(str(answer), perfil_escolhido="cex_itens_em_grade", numeros_esperados={1, 2, 3},
                          _ocr=lambda *args, **kwargs: calls.append(kwargs) or {1: "A"})
    assert result == {}
    assert not calls
    assert any("incompatível" in warning for warning in result.avisos)


def test_ui_treino_parcial_retoma_e_simulado_respeita_filtros_e_quantidade(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox, QStackedWidget
    from src.ui.pages.gerador_prova import GeradorProvaPage
    from src.ui.pages.provas_importadas import ProvasImportadasPage
    from src.ui.pages.execucao_prova import ExecucaoProvaPage
    init_db(str(tmp_path / "modes.sqlite"))
    statements = [f"Complete statement for official question number {word}." for word in ("one", "two", "three")]
    lines = list(COMMON)
    for number, statement in enumerate(statements, 1):
        lines += [f"QUESTAO {number}", statement] + QUESTION[2:]
    book = _write_text_pdf(tmp_path / "modes-book.pdf", lines)
    answer = _write_text_pdf(tmp_path / "modes-answers.pdf", COMMON + ["GABARITO DEFINITIVO", "1 A", "2 B", "3 C"])
    lote = importar_caderno(str(book))
    assert len(lote) == 3
    for index, question in enumerate(lote):
        question.update(disciplina="Matemática" if index != 1 else "Português", banca="Banca do teste",
                        topico="Operações" if index != 1 else "Leitura")
    lote[2]["enunciado"] = "Texto alterado que nao pertence a esta fonte."
    result = adapter.salvar_lote_verificado(lote, caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Composição original",
        prova={"nome": "Composição original", "lote_indices": [0, 1, 2],
               "composicao": [{"dados": question, "lote_index": i} for i, question in enumerate(lote)]})
    assert result["certificadas"] == 2, result
    assert [row["elegivel"] for row in result["elegibilidade"]] == [True, True, False]
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    generator = GeradorProvaPage()
    generator.nome_input.setText("Simulado filtrado")
    generator.disciplina_input.setCurrentText("Matemática")
    generator.banca_input.setCurrentText("Banca do teste")
    generator.topico_input.setCurrentText("Operações")
    generator.tipo_input.setCurrentIndex(generator.tipo_input.findData("multipla_escolha"))
    generator.qtd_input.setValue(2)
    generator.gerar_prova()
    wait_ui_jobs()
    random_proof = next(item for item in repo.listar_provas() if item["nome"] == "Simulado filtrado")
    assert [item["id"] for item in repo.buscar_questoes_da_prova(random_proof["id"])] == [result["ids"][0]]
    assert "apenas 1" in messages[-1]
    original = repo.listar_provas_cadastradas()[0]
    assert not original["pronta"] and original["qtd_avaliaveis"] == 2
    from src.ui.components.imported_exam_preview import ImportedExamPreviewDialog
    preview = ImportedExamPreviewDialog(original, repo.consultar_questoes_importadas(original['id']))
    for position in (1, 3):
        preview.position.setValue(position)
        assert 'Treino parcial: 2 de 3' in preview.notice.text()
    stack = QStackedWidget()
    imported, execution = ProvasImportadasPage(), ExecucaoProvaPage()
    stack.addWidget(imported)
    stack.addWidget(execution)
    imported.fazer_prova(original)
    wait_ui_jobs()
    assert stack.currentWidget() is execution
    assert execution.questoes and [q["numero_oficial"] for q in execution.questoes] == [1, 2]
    partial_id, attempt_id = execution.prova_id, execution.tentativa_id
    import json
    from src.db.models import Prova
    assert json.loads(Prova.get_by_id(partial_id).filtros)["modo"] == "prova_importada_parcial"
    execution.salvar_resposta_temp(True, result["ids"][0], "A")
    execution.proxima_questao()
    execution.tempo_gasto = 12
    execution._salvar_progresso()
    execution.timer.stop()
    resumed = ExecucaoProvaPage()
    resumed.iniciar(partial_id, "Treino parcial retomado")
    wait_ui_jobs()
    assert resumed.tentativa_id == attempt_id
    assert resumed.idx_atual == 1 and resumed.tempo_gasto == 12
    assert resumed.respostas_memoria == {result["ids"][0]: "A"}
    resumed.salvar_resposta_temp(True, result["ids"][1], "B")
    resumed.confirmar_finalizacao()
    assert "Acertos: 2 de 2" in messages[-1]
    random_execution = ExecucaoProvaPage()
    random_execution.iniciar(random_proof["id"], "Simulado filtrado")
    wait_ui_jobs()
    random_execution.salvar_resposta_temp(True, result["ids"][0], "A")
    random_execution.confirmar_finalizacao()
    assert "Acertos: 1 de 1" in messages[-1]


def test_ui_falha_real_de_leitura_preserva_edicao_e_permite_repetir(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    book = _write_text_pdf(tmp_path / "first.pdf", COMMON + QUESTION)
    broken = tmp_path / "retry.pdf"
    broken.write_bytes(b"invalid PDF")
    choices = iter((str(book), str(broken), str(broken)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (next(choices), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    page = ImportacaoPage()
    page.selecionar_arquivo()
    wait_idle(page)
    page.editor.enunciado_input.setPlainText("Edicao preservada antes da falha real de leitura.")
    before = [dict(question) for question in page.session.questoes]
    page.selecionar_arquivo()
    wait_idle(page)
    assert page.session.questoes == before
    assert page.session.caminho == str(book)
    assert "preservada" in page.feedback.text()
    _write_text_pdf(broken, COMMON + QUESTION)
    page.selecionar_arquivo()
    wait_idle(page)
    assert page.session.caminho == str(broken)
    assert len(page.session.questoes) == 1
    assert page.session.questoes[0]["enunciado"] == QUESTION[1]


def test_ui_formato_desconhecido_oferece_escolha_e_retoma_sem_aprovar(tmp_path, monkeypatch):
    book = _write_text_pdf(tmp_path / "unknown.pdf", ["Documento em formato nao reconhecido", "Conteudo sem marcador oficial de questao."])
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(book), ""))
    page = ImportacaoPage()
    page.selecionar_arquivo()
    wait_idle(page)
    assert not page.session.questoes
    assert page.perfil_caderno_combo.isEnabled()
    assert page.btn_reprocessar_caderno.isEnabled()
    choice = page.perfil_caderno_combo.findData("questoes_nomeadas_v2")
    assert choice >= 0
    page.perfil_caderno_combo.setCurrentIndex(choice)
    page._reprocessar_caderno()
    wait_idle(page)
    assert not page.session.questoes and not page.session.salvas
    assert "perfil escolhido não reconheceu" in page.feedback.text()
    assert page._salvar_rascunho()
    restored = ImportacaoPage()
    assert restored.session.caminho == str(book)
    assert not restored.session.questoes
    assert restored.btn_reprocessar_caderno.isEnabled()


def test_leitura_da_pagina_e_reutilizada_sem_reusar_fonte_alterada(tmp_path, monkeypatch):
    import pdfplumber
    from src.importador.pdf_fonte import readable_source_page
    from src.models.provenance_service import source_pdf, begin_source_verification_batch, end_source_verification_batch
    path = _write_text_pdf(tmp_path / "cached-page.pdf", ["Original source text."])
    original = pdfplumber.page.Page.dedupe_chars
    calls = []
    def counted(page, *args, **kwargs):
        calls.append(page)
        return original(page, *args, **kwargs)
    monkeypatch.setattr(pdfplumber.page.Page, "dedupe_chars", counted)
    token = begin_source_verification_batch()
    try:
        with source_pdf(path) as pdf:
            first = readable_source_page(pdf.pages[0])
            assert readable_source_page(pdf.pages[0]) is first
            assert len(calls) == 1
        _write_text_pdf(path, ["Changed source text with a different length."])
        with source_pdf(path) as pdf:
            changed = readable_source_page(pdf.pages[0])
            assert "Changed source" in changed.extract_text()
            assert changed is not first
            assert len(calls) == 2
    finally:
        end_source_verification_batch(token)


def test_inventario_reconcilia_papeis_sem_inventar_referencia_conferida(tmp_path):
    from scripts.catalogar_padroes import inventariar_documentos
    _write_text_pdf(tmp_path / "book.pdf", COMMON + QUESTION)
    _write_text_pdf(tmp_path / "outra-prova.pdf", ["GABARITO DEFINITIVO", "1 A"])
    write_pages(tmp_path / "unassociated.pdf", [["Documento textual"], []])
    result = inventariar_documentos(tmp_path,
        {"book.pdf": {"confirmado": True, "gabarito": "outra-prova.pdf", "cargo": "ANALISTA"}},
        [{"arquivo": "samples/book.pdf", "quantidade_extraida": 1}])
    assert result["total_documentos"] == 3 and result["sem_associacao_confirmada"] == 1
    records = {Path(item["arquivo"]).name: item for item in result["documentos"]}
    assert records["outra-prova.pdf"]["papel_confirmado"] == ["gabarito"]
    assert records["book.pdf"]["quantidade_extraida_observada"] == 1
    assert records["book.pdf"]["total_conferido_independentemente"] is None
    assert len(records["unassociated.pdf"]["paginas"]) == 2
    assert records["unassociated.pdf"]["paginas"][1]["caracteres_textuais"] == 0
    assert all(len(item["sha256"]) == 64 and not item["fidelidade_integral_conferida"] for item in result["documentos"])


@pytest.mark.parametrize("rejected,legacy", [(False, False), (True, False), (False, True)])
def test_reimportacao_completa_retoma_salvamento_parcial_sem_duplicar(tmp_path, rejected, legacy):
    from src.db.models import QuestaoVersao, EvidenciaQuestao, ProvaCadastrada
    from src.models.provenance_service import review_content
    init_db(str(tmp_path / "partial-import.sqlite"))
    book = _write_text_pdf(tmp_path / "book.pdf", COMMON + QUESTION + [
        "QUESTAO 2", "Different complete statement for the second official question.", *QUESTION[2:]])
    answer = _write_text_pdf(tmp_path / "answers.pdf", COMMON + ["GABARITO DEFINITIVO", "1 A", "2 B"])
    lote = importar_caderno(str(book))
    assert len(lote) == 2
    first = adapter.salvar_lote_verificado([lote[0]], caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Parcial")
    first_id = first["ids"][0]
    version = repo.ultima_versao(first_id)
    if legacy:
        import json
        extraction = version.execucao_extracao
        parameters = json.loads(extraction.parametros_json)
        parameters.pop("hash_fonte_gabarito")
        extraction.parametros_json = json.dumps(parameters)
        extraction.save()
    evidence_count = EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == version.id).count()
    if rejected:
        review_content(version.id, decision="rejeitado", reviewer="Revisora de teste",
                       rationale="Rejeicao explicita preservada na retomada.", evidence_ids=[])
    resumed = adapter.salvar_lote_verificado(lote, caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Retomada",
        prova={"nome": "Retomada", "lote_indices": [0, 1],
               "composicao": [{"dados": question, "lote_index": i} for i, question in enumerate(lote)]})
    assert resumed["ids"][0] == first_id
    assert Questao.select().count() == 2
    assert QuestaoVersao.select().count() == 2
    assert ProvaCadastrada.select().count() == 1
    assert resumed["retomada_parcial"]
    assert EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == version.id).count() == evidence_count
    assert resumed["elegibilidade"][0]["elegivel"] is not rejected


def test_mesmos_pdfs_com_escopos_distintos_nao_fundem_provas(tmp_path):
    from src.db.models import ProvaCadastrada
    init_db(str(tmp_path / "different-scopes.sqlite"))
    book = _write_text_pdf(tmp_path / "book.pdf", COMMON + ["Tipo 2"] + QUESTION)
    answer = _write_text_pdf(tmp_path / "answers.pdf", COMMON + ["Tipo 2", "GABARITO DEFINITIVO", "1 A"])
    lote = importar_caderno(str(book))
    composition = {"nome": "Escopo", "lote_indices": [0], "composicao": [{"dados": lote[0], "lote_index": 0}]}
    first = adapter.salvar_lote_verificado(lote, caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Um", versao_gabarito="1", prova=composition)
    second = adapter.salvar_lote_verificado(lote, caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Dois", versao_gabarito="2", prova=composition)
    assert second["prova_id"] != first["prova_id"]
    assert second["ids"] != first["ids"]
    assert ProvaCadastrada.select().count() == 2


def test_par_existente_sem_escopo_nao_e_fundido_nem_duplicado(tmp_path):
    from src.db.models import ProvaCadastrada
    init_db(str(tmp_path / "legacy-scope.sqlite"))
    book = _write_text_pdf(tmp_path / "book.pdf", COMMON + QUESTION)
    answer = _write_text_pdf(tmp_path / "answers.pdf", COMMON + ["GABARITO DEFINITIVO", "1 A"])
    lote = importar_caderno(str(book))
    composition = {"nome": "Legado", "lote_indices": [0], "composicao": [{"dados": lote[0], "lote_index": 0}]}
    result = adapter.salvar_lote_verificado(lote, caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Legado", prova=composition)
    extraction = repo.ultima_versao(result["ids"][0]).execucao_extracao
    extraction.parametros_json = "{}"
    extraction.save()
    with pytest.raises(ValueError, match="sem escopo de importação registrado"):
        adapter.salvar_lote_verificado(lote, caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Legado", prova=composition)
    assert Questao.select().count() == 1 and ProvaCadastrada.select().count() == 1


def test_reimportacao_reutiliza_copias_integras_quando_origens_foram_removidas(tmp_path):
    from src.db.models import DocumentoFonte
    init_db(str(tmp_path / "relocated.sqlite"))
    book = _write_text_pdf(tmp_path / "book.pdf", COMMON + QUESTION)
    answer = _write_text_pdf(tmp_path / "answers.pdf", COMMON + ["GABARITO DEFINITIVO", "1 A"])
    lote = importar_caderno(str(book))
    composition = {"nome": "Cópias", "lote_indices": [0], "composicao": [{"dados": lote[0], "lote_index": 0}]}
    first = adapter.salvar_lote_verificado(lote, caminho_caderno=str(book), caminho_gabarito=str(answer), nome_prova="Cópias", prova=composition)
    copied_book, copied_answer = tmp_path / "copy-book.pdf", tmp_path / "copy-answers.pdf"
    copied_book.write_bytes(book.read_bytes())
    copied_answer.write_bytes(answer.read_bytes())
    book.unlink()
    answer.unlink()
    resumed = adapter.salvar_lote_verificado(lote, caminho_caderno=str(copied_book), caminho_gabarito=str(copied_answer), nome_prova="Cópias", prova=composition)
    assert resumed["reutilizada"] and resumed["ids"] == first["ids"]
    assert resumed["prova_id"] == first["prova_id"]
    assert resumed["certificadas"] == 1
    assert DocumentoFonte.select().count() == 2 and Questao.select().count() == 1
    assert {source.localizacao for source in DocumentoFonte.select()} == {str(copied_book.resolve()), str(copied_answer.resolve())}
