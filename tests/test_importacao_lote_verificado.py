from pathlib import Path
import json
from threading import Event

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox
import pytest

from src.config import DB_PATH
from src.db.database import init_db
from src.db.models import (
    DocumentoFonte, EvidenciaQuestao, ProvaCadastrada, ProvaCadastradaQuestao,
    Questao, QuestaoVersao, Resposta,
)
from src.importador.lote_verificado import ImportacaoCancelada, _answer_status, _geometry_issues_for_number, salvar_lote_verificado
from src.models.provenance_service import assess_version, get_automatic_validation, version_is_eligible
from src.models import questoes_repo as repo
from src.ui.pages.importacao import ImportacaoPage


@pytest.fixture(autouse=True)
def restore_default_test_database():
    yield
    init_db(str(DB_PATH))


def _write_text_pdf(path: Path, lines: list[str], *, graphics=b"") -> Path:
    stream = bytearray(b"BT /F1 10 Tf 50 740 Td ")
    for index, line in enumerate(lines):
        if index:
            stream.extend(b"0 -18 Td ")
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.extend(f"({safe}) Tj ".encode("ascii"))
    stream.extend(b"ET\n" + graphics)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    path.write_bytes(data)
    return path


def test_codigos_de_cargo_nao_sao_versoes_e_capa_preserva_especialidade():
    from src.importador.perfis.documentos import _metadados, versao_da_selecao, versoes_declaradas
    assert versoes_declaradas("T11 Tecnico\nT12 Tecnico\nS201 Analista de Sistemas") == []
    assert versao_da_selecao("T11") == ""
    assert versao_da_selecao("T2") == "2"
    assert versao_da_selecao("PROVA TIPO IV") == "4"
    meta = _metadados("S201 AGENTE DE TECNOLOGIA DA INFORMACAO E COMUNICACAO –\nAnalista de Sistemas")
    assert "S201" in meta["codigo"]
    assert "analista de sistemas" in meta["cargo"]
    assert not meta.get("versao")
    meta = _metadados('ANALISTA DE TECNOLOGIA DA INFORMACAO\nDESENVOLVIMENTO DE SOFTWARE\nPROVA OBJETIVA - TIPO 4')
    assert 'analista de tecnologia da informacao - desenvolvimento de software' in meta['cargo']
    assert meta['versao'] == ('4',)


def test_gabarito_com_blocos_empilhados_seleciona_cargo_e_tipo(tmp_path):
    from src.importador.gabaritos import extrair_gabaritos_pdf
    answer = _write_text_pdf(tmp_path / 'stacked.pdf', [
        'GABARITOS PRELIMINARES',
        'ANALISTA - DESENVOLVIMENTO DE SOFTWARE', 'PROVA TIPO 3', '1 2 3', 'A B C',
        'ANALISTA - DESENVOLVIMENTO DE SOFTWARE', 'PROVA TIPO 4', '1 2 3', 'D E A',
        'ANALISTA - GOVERNANCA', 'PROVA TIPO 4', '1 2 3', 'B C D',
    ])
    result = extrair_gabaritos_pdf(str(answer), cargo='ANALISTA - DESENVOLVIMENTO DE SOFTWARE',
                                 versao='4', usar_ocr=False)
    assert result == {1: 'D', 2: 'E', 3: 'A'}
    assert not result.conflitos
    assert result.perfil_documento.situacao == 'preliminar'
    wrong = extrair_gabaritos_pdf(str(answer), cargo='ANALISTA - GOVERNANCA', versao='4', usar_ocr=False)
    assert wrong == {1: 'B', 2: 'C', 3: 'D'}
    missing = extrair_gabaritos_pdf(str(answer), cargo='ANALISTA - DESENVOLVIMENTO DE SOFTWARE', versao='2', usar_ocr=False)
    assert missing == {}


def test_bloco_gabarito_com_mesmo_cargo_exige_codigo_exato():
    from src.importador.perfis.gabaritos_contexto import FiltroContexto
    lines = ["S401 Analista de Sistemas (Cod. Vaga: 1)", "1 2", "A B",
             "S402 Analista de Sistemas (Cod. Vaga: 2)", "1 2", "C D"]
    result = FiltroContexto("S402", "Analista de Sistemas").linhas_do_cargo(lines)
    assert result == lines[3:]
    assert FiltroContexto("S403", "Analista de Sistemas").linhas_do_cargo(lines) == []


def test_previa_pendente_conserva_pixels_do_contexto_e_da_questao(tmp_path):
    from PIL import Image
    from hashlib import sha256
    from src.importador.lote_verificado import _combined_preview
    assets = []
    for name, color in [('context', 'blue'), ('question', 'red')]:
        path = tmp_path / (name + '.png')
        Image.new('RGB', (50, 30), color).save(path)
        assets.append({'path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()})
    path = _combined_preview(assets[:1], assets[1:], tmp_path, 1)
    with Image.open(path) as preview:
        assert preview.size == (50, 72)
        assert preview.getpixel((10, 10)) == (0, 0, 255)
        assert preview.getpixel((10, 55)) == (255, 0, 0)
    assert _combined_preview(assets[:1], assets[1:], tmp_path, 1) == path
    Path(assets[0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='contexto foi alterado'):
        _combined_preview(assets[:1], assets[1:], tmp_path, 1)


def test_equivalencia_de_copias_confronta_texto_e_graficos(tmp_path):
    from src.importador.comparacao_fontes import comparar_documentos
    original = _write_text_pdf(tmp_path / "original.pdf", ["S201 Analista de Sistemas", "QUESTAO 1"])
    copy = tmp_path / "copy.pdf"
    copy.write_bytes(original.read_bytes() + b"\n%metadata-only difference\n")
    proof = comparar_documentos(copy, original)
    assert proof["regra"] == "pdf-texto-e-pixels-v1"
    assert proof["paginas"] == 1
    assert proof["sha256_fonte"] != proof["sha256_referencia"]
    _write_text_pdf(copy, ["S201 Analista de Sistemas", "QUESTAO 1"], graphics=b"0 0 0 rg 50 50 100 100 re f")
    assert comparar_documentos(copy, original) is None
    _write_text_pdf(copy, ["S201 Analista de Sistemas", "QUESTAO 2"])
    assert comparar_documentos(copy, original) is None


def test_autoridade_recomputa_equivalencia_e_recusa_prova_forjada(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from copy import deepcopy
    from src.importador import lote_verificado as adapter
    from src.models import provenance_service as authority
    init_db(str(tmp_path / 'aliases.sqlite'))
    samples = tmp_path / 'samples'
    samples.mkdir()
    (tmp_path / 'config').mkdir()
    book = _write_text_pdf(samples / 'book.pdf', ['S201 Analista de Sistemas', 'QUESTAO 1'])
    answer = _write_text_pdf(samples / 'answer.pdf', ['S201 Analista de Sistemas', '1 A'])
    catalog = {'book.pdf': {'gabarito': 'answer.pdf', 'cargo': 'S201 Analista de Sistemas',
        'codigo': 'S201', 'confirmado': True, 'evidencia': 'Cabecalho impresso'}}
    (tmp_path / 'config/gabaritos.json').write_text(json.dumps(catalog), encoding='utf-8')
    external_book, external_answer = tmp_path / 'external.pdf', tmp_path / 'external-key.pdf'
    external_book.write_bytes(book.read_bytes() + b'\n% copy\n')
    external_answer.write_bytes(answer.read_bytes() + b'\n% copy\n')
    monkeypatch.setattr(adapter, 'ROOT_DIR', tmp_path)
    monkeypatch.setattr(authority, 'ROOT_DIR', tmp_path)
    key, entry = adapter._catalogue_binding(external_book, external_answer)
    assert key == 'book.pdf'
    scope, identity = adapter._scope(external_book, external_answer, key, entry,
                                    codigo='S201', cargo='Analista de Sistemas')
    refs = [SimpleNamespace(parte=part, documento_fonte_id=authority.create_source(path, tipo='pdf'))
            for part, path in [('conteudo', external_book), ('gabarito', external_answer)]]
    manifest = {'escopo': scope, 'identidade': identity}
    authority._verify_automatic_identity(manifest, refs)
    forged = deepcopy(manifest)
    forged['identidade']['equivalencia_documental']['caderno']['fingerprint_paginas'] = '0' * 64
    with pytest.raises(ValueError, match='equivalencia_documental_nao_comprovada'):
        authority._verify_automatic_identity(forged, refs)
    assert adapter._scope(external_book, external_answer, key, entry, codigo='S202')[0] is None
    # Duas associações confirmadas para conteúdo idêntico permanecem ambíguas.
    (samples / 'second.pdf').write_bytes(book.read_bytes())
    catalog['second.pdf'] = dict(catalog['book.pdf'])
    (tmp_path / 'config/gabaritos.json').write_text(json.dumps(catalog), encoding='utf-8')
    assert adapter._catalogue_binding(external_book, external_answer) == (None, None)


@pytest.mark.parametrize("header", [
    "GABARITO PRELIMINAR",
    "GABARITOS OFICIAIS PRELIMINARES",
    "GABARITO OFICIAL PRELIMINAR",
    "GABARITO OFICIAL - PRELIMINAR",
    "Gabaritos preliminares da prova aplicada no dia 12/10/2025",
    "Resultado preliminar da avaliacao",
    "Resultados preliminares da avaliacao",
])
def test_status_de_gabarito_preliminar_bloqueia_certificacao(tmp_path, header):
    answer = _write_text_pdf(tmp_path / "preliminar.pdf", [header, "1 A", "2 B"])

    assert _answer_status(answer) == "preliminar"


def test_status_definitivo_reconhece_qualificador_oficial_sem_inferir_pelo_nome(tmp_path):
    answer = _write_text_pdf(tmp_path / 'sem-status-no-nome.pdf', ['GABARITOS OFICIAIS DEFINITIVOS', '1 A'])
    assert _answer_status(answer) == 'definitivo'
    answer = _write_text_pdf(tmp_path / 'separador.pdf', ['GABARITO OFICIAL - DEFINITIVO', '1 A'])
    assert _answer_status(answer) == 'definitivo'
    unspecified = _write_text_pdf(tmp_path / 'gabarito-definitivo.pdf', ['Gabaritos para publicacao', '1 A'])
    assert _answer_status(unspecified) == 'documento_fornecido'


def test_diagnostico_geometrico_numerado_so_bloqueia_questao_afetada():
    issues = ["ancora_nao_encontrada:0", "marcador_duplicado:2", "pdf_open:erro"]

    assert _geometry_issues_for_number(issues, 1) == ["pdf_open:erro"]
    assert _geometry_issues_for_number(issues, 2) == ["marcador_duplicado:2", "pdf_open:erro"]


@pytest.mark.parametrize(("answer_header", "expected_certified"), [
    ("GABARITO DEFINITIVO", 1),
    ("Gabaritos preliminares da prova aplicada", 0),
])
def test_pdf_pair_outside_samples_persists_evidence_and_respects_status(tmp_path, answer_header, expected_certified):
    init_db(str(tmp_path / "isolated.sqlite"))
    book = _write_text_pdf(tmp_path / "book.pdf", [
        "Prova Teste", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        "QUESTAO 1", "Complete statement for official question one.",
        "A) Alpha option", "B) Bravo option", "C) Charlie option", "D) Delta option", "E) Echo option",
    ])
    answer = _write_text_pdf(tmp_path / "answer.pdf", [
        "Prova Teste", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        answer_header, "1 A",
    ])
    question = {
        "numero": 1, "numero_oficial": 1,
        "enunciado": "Complete statement for official question one.",
        "texto_apoio": "", "tipo": "multipla_escolha", "disciplina": "",
        "topico": "", "banca": "", "ano": None, "cargo": "ANALISTA DE SISTEMAS",
        "orgao": "", "dificuldade": "", "gabarito": None, "comentario": "",
        "alternativas": [{"letra": letter, "texto": f"{name} option"}
                         for letter, name in zip("ABCDE", ("Alpha", "Bravo", "Charlie", "Delta", "Echo"))],
    }

    result = salvar_lote_verificado([question], caminho_caderno=str(book),
        caminho_gabarito=str(answer), nome_prova="Prova Teste",
        perfil_caderno="questoes_nomeadas_v2", codigo_gabarito="A123",
        cargo_gabarito="ANALISTA DE SISTEMAS",
        prova={"nome": "Prova Teste", "lote_indices": [0],
               "composicao": [{"dados": question, "lote_index": 0}]})

    assert len(result["ids"]) == 1
    assert result["prova_id"]
    assert result["certificadas"] == expected_certified, result
    version = QuestaoVersao.select().where(QuestaoVersao.questao == result["ids"][0]).get()
    assert json.loads(version.conteudo_json)["gabarito"] == "A"
    if expected_certified:
        assert get_automatic_validation(version.id)["valida"]
        assert version_is_eligible(version)
        assert assess_version(version.id)["tipo_liberacao"] == "automatica"
    else:
        assert not get_automatic_validation(version.id)["valida"]
        assert not version_is_eligible(version)


def test_ui_saves_pair_then_original_and_random_attempts(tmp_path):
    init_db(str(tmp_path / "ui-isolated.sqlite"))
    book = _write_text_pdf(tmp_path / "outside-book.pdf", [
        "Prova Teste", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        "QUESTAO 1", "Complete statement for official question one.",
        "A) Alpha option", "B) Bravo option", "C) Charlie option", "D) Delta option", "E) Echo option",
    ])
    answer = _write_text_pdf(tmp_path / "outside-answer.pdf", [
        "Prova Teste", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        "GABARITO DEFINITIVO", "1 A",
    ])
    question = {
        "numero": 1, "numero_oficial": 1,
        "enunciado": "Complete statement for official question one.", "texto_apoio": "",
        "tipo": "multipla_escolha", "disciplina": "", "topico": "", "banca": "",
        "ano": None, "cargo": "ANALISTA DE SISTEMAS", "orgao": "", "dificuldade": "",
        "gabarito": "A", "comentario": "",
        "alternativas": [{"letra": letter, "texto": f"{name} option"}
                         for letter, name in zip("ABCDE", ("Alpha", "Bravo", "Charlie", "Delta", "Echo"))],
    }
    page = ImportacaoPage()
    page.session.carregar([question], str(book))
    page.nome_prova_input.setText("Prova Teste")
    page.caminho_gabarito = str(answer)
    page.perfil_caderno_combo.addItem("Questões nomeadas", "questoes_nomeadas_v2")
    page._sync()
    loop = QEventLoop()
    page.task.idle.connect(loop.quit)
    page._salvar([0])
    if page.task.running:
        QTimer.singleShot(30000, loop.quit)
        loop.exec()

    assert page.session.salvas
    question_id = next(iter(page.session.salvas.values()))
    version = repo.ultima_versao(question_id)
    assert version_is_eligible(version)
    proof_id = repo.listar_provas_cadastradas()[0]["id"]
    original_id = repo.criar_prova_a_partir_de_cadastrada("Prova original", proof_id, 0)
    original_items = repo.buscar_questoes_da_prova(original_id)
    assert [item["numero_oficial"] for item in original_items] == [1]
    attempt_id = repo.iniciar_tentativa(original_id)
    result = repo.finalizar_tentativa(attempt_id, {question_id: "A"}, 4)
    assert result["acertos"] == 1

    random_id = repo.criar_prova("Aleatória", {}, 1, 0)
    random_items = repo.buscar_questoes_da_prova(random_id)
    assert len(random_items) == 1
    random_attempt = repo.iniciar_tentativa(random_id)
    random_result = repo.finalizar_tentativa(random_attempt, {question_id: "A"}, 3)
    assert random_result["acertos"] == 1


def test_ui_importa_pdfs_externos_do_arquivo_a_tentativa(tmp_path, monkeypatch):
    init_db(str(tmp_path / "full-ui-isolated.sqlite"))
    book = _write_text_pdf(tmp_path / "external-book.pdf", [
        "Prova Externa", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        "QUESTAO 1", "Complete statement for official question one.",
        "A) Alpha option", "B) Bravo option", "C) Charlie option", "D) Delta option", "E) Echo option",
    ])
    answer = _write_text_pdf(tmp_path / "external-answer.pdf", [
        "Prova Externa", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        "GABARITO DEFINITIVO", "1 A",
    ])
    choices = iter((str(book), str(answer)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (next(choices), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    from src.ui.main_window import MainWindow
    from PySide6.QtWidgets import QApplication
    window = MainWindow()
    page = window.pages.widget(2)

    def wait_idle(target=page):
        if not target.task.running:
            return
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        target.task.idle.connect(loop.quit)
        timer.timeout.connect(loop.quit)
        timer.start(60000)
        loop.exec()
        target.task.idle.disconnect(loop.quit)
        assert not target.task.running, target.feedback.text()

    page.selecionar_arquivo()
    wait_idle()
    assert len(page.session.questoes) == 1, page.feedback.text()
    page.cargo_gabarito_input.setText("ANALISTA DE SISTEMAS")
    page.codigo_gabarito_input.setText("A123")
    page.selecionar_gabarito()
    wait_idle()
    assert page.session.questoes[0]["gabarito"] == "A", page.feedback.text()
    page.steps.setCurrentIndex(2)
    page.salvar_todas()
    wait_idle()

    assert len(page.session.salvas) == 1
    question_id = next(iter(page.session.salvas.values()))
    version = repo.ultima_versao(question_id)
    assert version_is_eligible(version)
    source_paths = {row.localizacao for row in DocumentoFonte.select()}
    assert str(book.resolve()) in source_paths
    assert str(answer.resolve()) in source_paths
    assert {row.parte for row in EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == version.id)} >= {
        "conteudo", "gabarito"
    }

    proof_id = repo.listar_provas_cadastradas()[0]["id"]
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    def start_original():
        dialog = QApplication.activeModalWidget()
        if dialog and hasattr(dialog, "start"):
            dialog.start.click()
        elif dialog:
            dialog.reject()
    QTimer.singleShot(0, start_original)
    page.btn_abrir_prova.click()
    execution = window.pages.widget(5)
    assert window.pages.currentWidget() is execution
    original_id, original_attempt = execution.prova_id, execution.tentativa_id
    assert [item["numero_oficial"] for item in repo.buscar_questoes_da_prova(original_id)] == [1]
    execution.salvar_resposta_temp(True, question_id, "A")
    execution.confirmar_finalizacao()
    assert "Acertos: 1 de 1" in messages[-1]
    page.btn_gerar_simulado.click()
    assert window.menu.currentRow() == 3
    random_id = repo.criar_prova("Simulado externo", {}, 1, 0)
    assert len(repo.buscar_questoes_da_prova(random_id)) == 1
    attempt = repo.iniciar_tentativa(random_id)
    assert repo.finalizar_tentativa(attempt, {question_id: "A"}, 3)["acertos"] == 1

    choices = iter((str(book), str(answer)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (next(choices), ""))
    repeated = ImportacaoPage()
    repeated.selecionar_arquivo()
    wait_idle(repeated)
    repeated.cargo_gabarito_input.setText("ANALISTA DE SISTEMAS")
    repeated.codigo_gabarito_input.setText("A123")
    repeated.selecionar_gabarito()
    wait_idle(repeated)
    repeated.steps.setCurrentIndex(2)
    repeated.salvar_todas()
    wait_idle(repeated)
    assert Questao.select().count() == 1
    assert ProvaCadastrada.select().count() == 1
    assert repeated.session.salvas == {0: question_id}
    assert "reutilizada" in repeated.feedback.text()

    choices = iter((str(book), str(answer)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (next(choices), ""))
    revised = ImportacaoPage()
    revised.selecionar_arquivo()
    wait_idle(revised)
    revised.cargo_gabarito_input.setText("ANALISTA DE SISTEMAS")
    revised.codigo_gabarito_input.setText("A123")
    revised.selecionar_gabarito()
    wait_idle(revised)
    revised.editor.enunciado_input.setPlainText("Explicitly revised statement no longer matching the source.")
    revised.steps.setCurrentIndex(2)
    revised.salvar_todas()
    wait_idle(revised)
    assert "marque a opção de nova versão" in revised.feedback.text()
    assert QuestaoVersao.select().where(QuestaoVersao.questao == question_id).count() == 1
    revised.nova_versao_checkbox.setChecked(True)
    revised.salvar_todas()
    wait_idle(revised)
    assert Questao.select().count() == 1
    assert QuestaoVersao.select().where(QuestaoVersao.questao == question_id).count() == 2
    old_link = ProvaCadastradaQuestao.get(ProvaCadastradaQuestao.prova_cadastrada == proof_id)
    assert old_link.questao_versao_id == version.id
    historical_answer = Resposta.get(Resposta.tentativa == original_attempt)
    assert historical_answer.questao_versao_id == version.id
    assert not version_is_eligible(repo.ultima_versao(question_id))
    assert ProvaCadastrada.select().count() == 2
    assert "Nova versão criada" in revised.feedback.text()


def test_cancelar_persistencia_reverte_lote_inteiro(tmp_path, monkeypatch):
    init_db(str(tmp_path / "cancel-isolated.sqlite"))
    cancel_event = Event()
    original = repo.criar_questoes_em_lote

    def insert_then_cancel(*args, **kwargs):
        ids = original(*args, **kwargs)
        cancel_event.set()
        return ids

    monkeypatch.setattr(repo, "criar_questoes_em_lote", insert_then_cancel)
    question = {
        "numero": 1, "enunciado": "Questão de teste", "tipo": "certo_errado",
        "gabarito": "Certo", "alternativas": [],
    }

    with pytest.raises(ImportacaoCancelada):
        salvar_lote_verificado([question], caminho_caderno=str(tmp_path / "manual.docx"),
            caminho_gabarito=None, nome_prova="Lote cancelado", cancel_event=cancel_event)

    from src.db.models import Questao
    assert Questao.select().count() == 0


def test_metadados_pdf_sao_reutilizados_sem_reusar_fonte_alterada(tmp_path, monkeypatch):
    from src.importador import lote_verificado as adapter

    pdf = _write_text_pdf(tmp_path / "metadata.pdf", ["Metadados da fonte"])
    original = adapter.source_pdf
    calls = []

    def counted(path):
        calls.append(str(path))
        return original(path)

    adapter._metadata_cached.cache_clear()
    monkeypatch.setattr(adapter, "source_pdf", counted)
    first = adapter._metadata(pdf, 1)
    assert adapter._metadata(pdf, 1) == first
    assert len(calls) == 1

    _write_text_pdf(pdf, ["Metadados alterados", "Pagina adicional"])
    adapter._metadata(pdf, 1)
    assert len(calls) == 2


@pytest.mark.parametrize("family", ["multiple_numbered", "ce_context"])
def test_ui_importa_familias_externas_numerada_e_contextual(tmp_path, monkeypatch, family):
    init_db(str(tmp_path / f"{family}.sqlite"))
    common = ["Prova Externa", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I"]
    if family == "multiple_numbered":
        book_lines = common + [
            "1.", "Complete statement for official question one.",
            "A) Alpha option", "B) Bravo option", "C) Charlie option",
            "D) Delta option", "E) Echo option",
        ]
        answer_lines = common + ["GABARITO DEFINITIVO", "1 A"]
        expected_profile = "multipla_escolha_numerada_v1"
        expected_parts = {"conteudo", "gabarito"}
    else:
        book_lines = common + [
            "TEXTO DE APOIO", "Texto para as questoes de 1 a 1",
            "Passagem compartilhada suficientemente longa para servir de contexto.",
            "Ela permanece completa no original para conferencia.",
            "ITEM PARA JULGAMENTO", "1.",
            "Este item avalia uma afirmacao apresentada no texto de apoio.",
        ]
        answer_lines = common + ["GABARITO DEFINITIVO", "1 C"]
        expected_profile = "certo_errado_contexto_v1"
        expected_parts = {"conteudo", "contexto", "gabarito"}

    book = _write_text_pdf(tmp_path / f"{family}-book.pdf", book_lines)
    answer = _write_text_pdf(tmp_path / f"{family}-answer.pdf", answer_lines)
    choices = iter((str(book), str(answer)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (next(choices), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    page = ImportacaoPage()

    def wait_idle():
        if not page.task.running:
            return
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        page.task.idle.connect(loop.quit)
        timer.timeout.connect(loop.quit)
        timer.start(30000)
        loop.exec()
        page.task.idle.disconnect(loop.quit)
        assert not page.task.running, page.feedback.text()

    page.selecionar_arquivo()
    wait_idle()
    assert len(page.session.questoes) == 1, page.feedback.text()
    assert page.session.questoes[0]["perfil_importacao"] == expected_profile
    page.cargo_gabarito_input.setText("ANALISTA DE SISTEMAS")
    page.codigo_gabarito_input.setText("A123")
    page.selecionar_gabarito()
    wait_idle()
    page.steps.setCurrentIndex(2)
    page.salvar_todas()
    wait_idle()

    assert len(page.session.salvas) == 1, page.feedback.text()
    question_id = next(iter(page.session.salvas.values()))
    version = repo.ultima_versao(question_id)
    assert version_is_eligible(version), assess_version(version.id)
    parts = {row.parte for row in EvidenciaQuestao.select().where(
        EvidenciaQuestao.questao_versao == version.id
    )}
    assert parts >= expected_parts
    proof = repo.listar_provas_cadastradas()[0]
    assert proof["qtd_questoes"] == 1
    original_id = repo.criar_prova_a_partir_de_cadastrada(
        f"Original {family}", proof["id"], 0
    )
    assert [item["numero_oficial"] for item in repo.buscar_questoes_da_prova(original_id)] == [1]
    expected_answer = "Certo" if family == "ce_context" else "A"
    original_attempt = repo.iniciar_tentativa(original_id)
    assert repo.finalizar_tentativa(original_attempt, {question_id: expected_answer}, 4)["acertos"] == 1
    random_id = repo.criar_prova(f"Simulado {family}", {}, 1, 0)
    random_attempt = repo.iniciar_tentativa(random_id)
    assert repo.finalizar_tentativa(random_attempt, {question_id: expected_answer}, 3)["acertos"] == 1


@pytest.mark.parametrize("decision", ["definitivo_confirmado", "conflitante"])
def test_ui_revisao_humana_aplica_decisao_com_evidencias_reais(tmp_path, monkeypatch, decision):
    init_db(str(tmp_path / "human-review.sqlite"))
    book = _write_text_pdf(tmp_path / "human-review-book.pdf", [
        "Prova Externa", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        "QUESTAO 1", "Complete statement for official question one.",
        "A) Alpha option", "B) Bravo option", "C) Charlie option",
        "D) Delta option", "E) Echo option",
    ])
    answer = _write_text_pdf(tmp_path / "human-review-answer.pdf", [
        "Prova Externa", "Cargo: ANALISTA DE SISTEMAS", "Codigo A123", "Tipo I",
        "GABARITO DEFINITIVO", "1 A",
    ])
    choices = iter((str(book), str(answer)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (next(choices), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2] if len(args) > 2 else "warning"))
    page = ImportacaoPage()

    def wait_idle():
        if not page.task.running:
            return
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        page.task.idle.connect(loop.quit)
        timer.timeout.connect(loop.quit)
        timer.start(30000)
        loop.exec()
        page.task.idle.disconnect(loop.quit)
        assert not page.task.running, page.feedback.text()

    page.selecionar_arquivo()
    wait_idle()
    page.cargo_gabarito_input.setText("ANALISTA DE SISTEMAS")
    page.codigo_gabarito_input.setText("A123")
    page.selecionar_gabarito()
    wait_idle()
    page.editor.enunciado_input.setPlainText("Changed text that does not match the source anchor.")
    page.steps.setCurrentIndex(2)
    page.salvar_todas()
    wait_idle()
    question_id = next(iter(page.session.salvas.values()))
    assert not version_is_eligible(repo.ultima_versao(question_id))

    from src.ui.components.imported_exam_preview import ImportedExamPreviewDialog
    from src.ui.components.question_source_review import QuestionSourceReviewDialog
    proof = repo.listar_provas_cadastradas()[0]
    proof_questions = repo.consultar_questoes_importadas(proof["id"])
    dialog = ImportedExamPreviewDialog(proof, proof_questions)
    opened = []
    monkeypatch.setattr(QuestionSourceReviewDialog, "exec", lambda self: opened.append(self))
    dialog.review_question()
    review = opened[0]
    assert review.question_pdf.source_path == str(book.resolve())
    review.proof_identity.setPlainText("Prova Externa")
    review.scope_cargo.setPlainText("ANALISTA DE SISTEMAS")
    review.scope_code.setPlainText("A123")
    review.scope_version.setPlainText("Tipo I")
    review.reviewer.setPlainText("Revisora de teste")
    review.rationale.setPlainText("Conferi conteudo e resposta na fonte original.")
    review._record_content_evidence()
    review.answer_pdf.load_path(str(answer))
    status = "definitivo" if decision == "definitivo_confirmado" else "conflitante"
    review.answer_status.setCurrentIndex(review.answer_status.findData(status))
    review._record_answer_evidence()
    review.content_decision.setCurrentIndex(review.content_decision.findData("conferido"))
    review._review_content()
    review.answer_decision.setCurrentIndex(review.answer_decision.findData(decision))
    review._review_answer()
    assert not warnings, warnings
    assessment = assess_version(review.version_id)
    if decision == "definitivo_confirmado":
        assert version_is_eligible(QuestaoVersao.get_by_id(review.version_id)), assessment
    else:
        assert not assessment["liberada"]
        assert any(item["codigo"] == "gabarito_conflitante" for item in assessment["pendencias"])
