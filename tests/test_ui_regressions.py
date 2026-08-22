import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QStackedWidget, QWidget

from src.db.database import db, init_db
from src.models.questoes_repo import criar_questao, criar_prova
from src.ui.pages.execucao_prova import ExecucaoProvaPage
import src.ui.pages.execucao_prova as execucao_mod
from src.ui.main_window import MainWindow


def _qapp():
    return QApplication.instance() or QApplication([])


def test_execucao_limpa_estado_apos_finalizar_prova(tmp_path, monkeypatch):
    _qapp()
    init_db(str(tmp_path / "ui.db"))
    q1 = criar_questao({"enunciado": "Primeira questão do teste", "tipo": "certo_errado", "gabarito": "Certo"})
    criar_questao({"enunciado": "Segunda questão do teste", "tipo": "certo_errado", "gabarito": "Errado"})
    prova_id = criar_prova("Ciclo de regressão", {}, 2, None)

    stack = QStackedWidget()
    for _ in range(4):
        stack.addWidget(QWidget())
    pagina = ExecucaoProvaPage()
    stack.addWidget(pagina)
    pagina.iniciar(prova_id, "Ciclo de regressão")
    pagina.respostas_memoria = {q1: "Certo"}
    monkeypatch.setattr(execucao_mod.QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(execucao_mod.QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    pagina.confirmar_finalizacao()

    assert pagina.em_andamento is False
    assert pagina.timer.isActive() is False
    assert pagina.btn_finalizar.isEnabled() is False
    assert pagina.lbl_enunciado.toPlainText().startswith("Suas questões")
    assert stack.currentIndex() == 3
    db.close()


def test_main_window_inicia_com_dashboard_selecionado():
    _qapp()
    janela = MainWindow()

    assert janela.menu.currentRow() == 0
    assert janela.pages.currentIndex() == 0


def test_execucao_finaliza_automaticamente_ao_atingir_limite(tmp_path, monkeypatch):
    _qapp()
    init_db(str(tmp_path / "limite.db"))
    criar_questao({"enunciado": "Questão com tempo limitado", "tipo": "certo_errado", "gabarito": "Certo"})
    prova_id = criar_prova("Limite", {}, 1, 1)
    stack = QStackedWidget()
    for _ in range(4):
        stack.addWidget(QWidget())
    pagina = ExecucaoProvaPage()
    stack.addWidget(pagina)
    monkeypatch.setattr(execucao_mod.QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    pagina.iniciar(prova_id, "Limite")
    pagina.tempo_limite_seg = 1
    pagina.atualizar_tempo()

    assert pagina.em_andamento is False
    assert pagina.timer.isActive() is False
    db.close()
