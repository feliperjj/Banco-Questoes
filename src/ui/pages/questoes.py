import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

import src.models.questoes_repo as repo


logger = logging.getLogger(__name__)


class QuestaoDialog(QDialog):
    def __init__(self, questao_dados=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nova Questão" if not questao_dados else "Editar Questão")
        self.resize(500, 600)
        self.questao_id = questao_dados.get("id") if questao_dados else None
        layout = QFormLayout(self)

        self.enunciado_input = QTextEdit()
        if questao_dados: self.enunciado_input.setText(questao_dados.get("enunciado", ""))
        layout.addRow("Enunciado:", self.enunciado_input)
        self.tipo_combo = QComboBox(); self.tipo_combo.addItems(["multipla_escolha", "certo_errado"])
        if questao_dados: self.tipo_combo.setCurrentText(questao_dados.get("tipo", "multipla_escolha"))
        layout.addRow("Tipo:", self.tipo_combo)
        self.disciplina_input = QComboBox(); self.disciplina_input.setEditable(True)
        if questao_dados: self.disciplina_input.setCurrentText(questao_dados.get("disciplina", ""))
        layout.addRow("Disciplina:", self.disciplina_input)
        self.topico_input = QComboBox(); self.topico_input.setEditable(True)
        if questao_dados: self.topico_input.setCurrentText(questao_dados.get("topico", ""))
        layout.addRow("Tópico:", self.topico_input)
        self.banca_input = QComboBox(); self.banca_input.setEditable(True)
        if questao_dados: self.banca_input.setCurrentText(questao_dados.get("banca", ""))
        layout.addRow("Banca:", self.banca_input)
        self.ano_input = QLineEdit()
        if questao_dados and questao_dados.get("ano"): self.ano_input.setText(str(questao_dados["ano"]))
        layout.addRow("Ano:", self.ano_input)
        self.dificuldade_combo = QComboBox(); self.dificuldade_combo.addItems(["facil", "media", "dificil"])
        if questao_dados: self.dificuldade_combo.setCurrentText(questao_dados.get("dificuldade", "media"))
        layout.addRow("Dificuldade:", self.dificuldade_combo)
        self.gabarito_input = QComboBox(); self.gabarito_input.addItems(["A", "B", "C", "D", "E", "Certo", "Errado"])
        if questao_dados: self.gabarito_input.setCurrentText(questao_dados.get("gabarito", "A"))
        layout.addRow("Gabarito:", self.gabarito_input)
        buttons = QHBoxLayout(); salvar_btn = QPushButton("Salvar"); salvar_btn.clicked.connect(self.salvar); buttons.addWidget(salvar_btn)
        if self.questao_id:
            excluir_btn = QPushButton("Excluir"); excluir_btn.setObjectName("danger-button"); excluir_btn.clicked.connect(self.excluir); buttons.addWidget(excluir_btn)
        layout.addRow(buttons)

    def salvar(self):
        dados = {
            "enunciado": self.enunciado_input.toPlainText(), "tipo": self.tipo_combo.currentText(),
            "disciplina": self.disciplina_input.currentText(), "topico": self.topico_input.currentText(),
            "banca": self.banca_input.currentText(), "ano": int(self.ano_input.text()) if self.ano_input.text().isdigit() else None,
            "dificuldade": self.dificuldade_combo.currentText(), "gabarito": self.gabarito_input.currentText(),
        }
        if self.questao_id: repo.atualizar_questao(self.questao_id, dados)
        else: repo.criar_questao(dados)
        logger.info("Questão %s salva", self.questao_id or "nova")
        self.accept()

    def excluir(self):
        if QMessageBox.question(self, "Confirmar", "Deseja excluir esta questão?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            repo.excluir_questao(self.questao_id)
            logger.info("Questão %s excluída logicamente", self.questao_id)
            self.accept()


class QuestoesPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); top = QHBoxLayout()
        self.busca_input = QLineEdit(); self.busca_input.setPlaceholderText("Buscar por enunciado..."); self.busca_input.textChanged.connect(self.carregar_dados)
        btn_nova = QPushButton("Nova Questão"); btn_nova.clicked.connect(self.abrir_nova_questao)
        top.addWidget(self.busca_input); top.addWidget(btn_nova); layout.addLayout(top)
        self.tabela = QTableWidget(); self.tabela.setColumnCount(6); self.tabela.setHorizontalHeaderLabels(["ID", "Enunciado", "Disciplina", "Banca", "Ano", "Dificuldade"])
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); self.tabela.setSelectionBehavior(QTableWidget.SelectRows); self.tabela.setEditTriggers(QTableWidget.NoEditTriggers); self.tabela.doubleClicked.connect(self.abrir_edicao_questao)
        layout.addWidget(self.tabela); self.carregar_dados()

    def carregar_dados(self):
        questoes = repo.buscar_questoes(texto=self.busca_input.text()); self.tabela.setRowCount(len(questoes))
        for row, q in enumerate(questoes):
            valores = [q["id"], q["enunciado"][:50] + "..." if len(q["enunciado"]) > 50 else q["enunciado"], q["disciplina"] or "", q["banca"] or "", str(q["ano"]) if q["ano"] else "", q["dificuldade"] or ""]
            for col, valor in enumerate(valores): self.tabela.setItem(row, col, QTableWidgetItem(str(valor)))
            self.tabela.item(row, 0).setData(Qt.UserRole, q)

    def abrir_nova_questao(self):
        if QuestaoDialog(parent=self).exec(): self.carregar_dados()

    def abrir_edicao_questao(self, index):
        dados = self.tabela.item(index.row(), 0).data(Qt.UserRole)
        if QuestaoDialog(questao_dados=dados, parent=self).exec(): self.carregar_dados()
