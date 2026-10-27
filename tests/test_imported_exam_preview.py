from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QPushButton

from src.db.database import db, init_db
from src.db.models import ProvaCadastradaQuestao
from src.models import questoes_repo as repo
from src.ui.components.imported_exam_preview import ImportedExamPreviewDialog
from src.ui.pages.provas_importadas import ProvasImportadasPage


def test_gabarito_salvo_pendente_nao_aparece_como_sem_gabarito(tmp_path):
    init_db(str(tmp_path / "answers.db"))
    source_id = repo.criar_prova_cadastrada("Com resposta, ainda não revisada", [
        {"enunciado": "Uma afirmação com resposta salva.", "tipo": "certo_errado", "gabarito": "Certo"},
    ])
    proof = repo.listar_provas_cadastradas()[0]
    assert proof["id"] == source_id
    assert proof["qtd_com_gabarito"] == 1
    assert proof["qtd_sem_gabarito"] == 0
    assert proof["qtd_avaliaveis"] == 0
    assert proof["pronta"] is False
    page = ProvasImportadasPage()
    status = page.tabela.item(0, 2)
    assert "Revisão pendente" in status.text()
    assert "sem gabarito" not in status.text()
    assert "1/1 com gabarito salvo" in status.toolTip()
    assert page.tabela.cellWidget(0, 3).findChild(QPushButton).text() == "Ver questões"


def test_consulta_na_ordem_importada_preserva_banco_e_nao_inventa_numero(tmp_path):
    app = QApplication.instance()
    init_db(str(tmp_path / "preview.db"))
    image_path = tmp_path / "figure.png"
    image = QImage(20, 20, QImage.Format_RGB32)
    image.fill(Qt.red)
    image.save(str(image_path))
    source_id = repo.criar_prova_cadastrada("Consulta de conteúdo", [
        {"numero_oficial": 17, "enunciado": "Questão com resposta armazenada.",
         "tipo": "certo_errado", "gabarito": "Certo"},
        {"enunciado": "Enunciado <não é HTML>.", "texto_apoio": "Texto compartilhado completo.",
         "tipo": "multipla_escolha", "gabarito": None, "imagem_path": str(image_path),
         "alternativas": [{"letra": "A", "texto": "Alternativa integral, sem corte."},
                          {"letra": "B", "texto": "Outra alternativa."}]},
    ])
    links = list(ProvaCadastradaQuestao.select().order_by(ProvaCadastradaQuestao.ordem))
    links[0].ordem = 2
    links[0].save()
    links[1].ordem = 1
    links[1].save()
    proof = repo.listar_provas_cadastradas()[0]
    assert proof["qtd_com_gabarito"] == 1
    assert proof["qtd_sem_gabarito"] == 1
    before = list(db.connection().iterdump())
    db.execute_sql("PRAGMA query_only=ON")
    try:
        questions = repo.consultar_questoes_importadas(source_id)
        assert [q["id"] for q in questions] == [links[1].questao_id, links[0].questao_id]
        legacy = repo.consultar_questoes_importadas(questao_ids=[questions[1]["id"], questions[0]["id"]])
        assert [q["id"] for q in legacy] == [questions[1]["id"], questions[0]["id"]]
        dialog = ImportedExamPreviewDialog(proof, questions)
        dialog.show()
        app.processEvents()
        assert "ainda não identificado" in dialog.official_number.text()
        assert "Texto compartilhado completo." in dialog.content.toPlainText()
        assert "<não é HTML>" in dialog.content.toPlainText()
        assert "Alternativa integral, sem corte." in dialog.content.toPlainText()
        assert not dialog.start.isEnabled()
        assert dialog.content.isReadOnly()
        dialog.next.click()
        app.processEvents()
        assert dialog.official_number.text() == "Número oficial: 17"
        assert "Gabarito salvo: Certo" in dialog.content.toPlainText()
        dialog.previous.click()
        dialog.reject()
    finally:
        db.execute_sql("PRAGMA query_only=OFF")
    assert list(db.connection().iterdump()) == before


def test_parcial_preserva_ordem_snapshots_e_revalida_fonte_ao_iniciar(tmp_path):
    import json
    import pytest
    from helpers import approve_with_evidence
    from src.db.models import ProvaQuestao, Tentativa
    init_db(str(tmp_path / "parcial.db"))
    source_id = repo.criar_prova_cadastrada("Prova de origem", [
        {"numero_oficial": n, "enunciado": f"Afirmação completa número {n}.", "tipo": "certo_errado", "gabarito": "Certo"}
        for n in (7, 8, 9)
    ])
    links = list(ProvaCadastradaQuestao.select().where(ProvaCadastradaQuestao.prova_cadastrada == source_id).order_by(ProvaCadastradaQuestao.ordem))
    first, pending, last = [link.questao_id for link in links]
    source_first = tmp_path / "primeira.pdf"
    version_first = approve_with_evidence(first, source_first, "Certo")
    import helpers
    from unittest.mock import patch
    original_writer = helpers.write_test_pdf
    def distinct_document(path, *args, **kwargs):
        original_writer(path, *args, **kwargs)
        path.write_bytes(path.read_bytes() + b"\n% documento distinto\n")
        return path
    with patch.object(helpers, "write_test_pdf", side_effect=distinct_document):
        version_last = approve_with_evidence(last, tmp_path / "ultima.pdf", "Certo")
    for order, link in enumerate(reversed(links), 1):
        link.ordem = order
        link.save()
    with pytest.raises(ValueError):
        repo.criar_prova("Completa bloqueada", {}, 3, None, prova_cadastrada_id=source_id)
    attempts_before = Tentativa.select().count()
    partial = repo.criar_prova_parcial_importada("Prova de origem", prova_cadastrada_id=source_id)
    assert repo.obter_prova(partial)["nome"].startswith("2 de 3 verificadas")
    composition = list(ProvaQuestao.select().where(ProvaQuestao.prova == partial).order_by(ProvaQuestao.ordem))
    assert [(link.questao_id, link.questao_versao_id) for link in composition] == [(last, version_last), (first, version_first)]
    from src.db.models import Prova
    config = json.loads(Prova.get_by_id(partial).filtros)
    assert config["modo"] == "prova_importada_parcial"
    assert config["questao_ids_originais"] == [last, pending, first]
    assert config["questao_ids_excluidas"] == [pending]
    assert Tentativa.select().count() == attempts_before
    # A contagem exibida anteriormente não pode liberar uma fonte alterada.
    source_first.write_bytes(b"fonte alterada")
    newer = repo.criar_prova_parcial_importada("Prova de origem", prova_cadastrada_id=source_id)
    assert repo.obter_prova(newer)["nome"].startswith("1 de 3 verificadas")
    assert [link.questao_id for link in ProvaQuestao.select().where(ProvaQuestao.prova == newer)] == [last]


def test_consulta_parcial_oferece_apenas_o_treino_verificado():
    question = {"id": 1, "numero_oficial": 7, "enunciado": "Texto completo.", "tipo": "certo_errado", "gabarito": "Certo"}
    proof = {"nome": "Parcial", "pronta": False, "qtd_questoes": 3, "qtd_avaliaveis": 2}
    dialog = ImportedExamPreviewDialog(proof, [question])
    assert dialog.start.isEnabled()
    assert dialog.start.text() == "Resolver 2 verificadas"
