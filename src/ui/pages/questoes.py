import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from src.ui.components.question_editor import QuestionEditor

import src.models.questoes_repo as repo
from src.importador.validacao import problemas_estrutura


logger = logging.getLogger(__name__)


class QuestaoDialog(QDialog):
    def __init__(self, questao_dados=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar questão" if questao_dados else "Nova questão")
        self.resize(620, 660)
        self.questao_id = (questao_dados or {}).get("id")
        self._dirty = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        titulo = QLabel(self.windowTitle())
        titulo.setObjectName("page-title")
        layout.addWidget(titulo)
        self.editor = QuestionEditor()
        self.editor.load(questao_dados or {})
        self.editor.changed.connect(self._alterado)
        layout.addWidget(self.editor, 1)
        # Os consumidores existentes continuam usando os mesmos campos públicos.
        for nome in ("enunciado_input", "tipo_combo", "disciplina_input", "topico_input",
                     "banca_input", "ano_input", "dificuldade_combo", "gabarito_input", "alternativas_input"):
            setattr(self, nome, getattr(self.editor, nome))
        footer = QHBoxLayout()
        if self.questao_id:
            excluir = QPushButton("Excluir questão")
            excluir.setObjectName("danger-button")
            excluir.clicked.connect(self.excluir)
            footer.addWidget(excluir)
        footer.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setObjectName("secondary-button")
        cancelar.clicked.connect(self.reject)
        footer.addWidget(cancelar)
        self.salvar_btn = QPushButton("Salvar questão")
        self.salvar_btn.clicked.connect(self.salvar)
        footer.addWidget(self.salvar_btn)
        layout.addLayout(footer)

    def _alterado(self):
        self._dirty = True

    def reject(self):
        if self._dirty and QMessageBox.question(self, "Descartar alterações?",
                "Há alterações não salvas. Deseja descartá-las?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        super().reject()

    def salvar(self):
        try:
            dados = self.editor.data(validate=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Revise a questão", str(exc))
            return
        self.salvar_btn.setEnabled(False)
        try:
            if self.questao_id:
                repo.atualizar_questao(self.questao_id, dados)
            else:
                self.questao_id = repo.criar_questao(dados)
        except Exception:
            logger.exception("Falha ao salvar questão")
            QMessageBox.critical(self, "Não foi possível salvar", "Suas alterações continuam no formulário. Tente novamente.")
            self.salvar_btn.setEnabled(True)
            return
        self._dirty = False
        self.accept()

    def excluir(self):
        if QMessageBox.question(self, "Excluir questão?", "A questão será removida do acervo ativo. O histórico será preservado.",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            repo.excluir_questao(self.questao_id)
        except Exception:
            logger.exception("Falha ao excluir questão")
            QMessageBox.critical(self, "Não foi possível excluir", "Tente novamente.")
            return
        self._dirty = False
        self.accept()


class QuestoesPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(12)
        titulo = QLabel("Banco de questões")
        titulo.setObjectName("page-title")
        subtitulo = QLabel("Pesquise, revise e mantenha seu acervo organizado.")
        subtitulo.setObjectName("page-subtitle")
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        self.filtro_gabarito = QComboBox()
        self.filtro_gabarito.addItems(["Todas as questões", "Sem gabarito", "Com gabarito", "Anuladas", "Problemas de extração"])
        self.filtro_gabarito.currentIndexChanged.connect(self.carregar_dados)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.busca_input = QLineEdit()
        self.busca_input.setObjectName("search-input")
        self.busca_input.setPlaceholderText("Buscar no enunciado...")
        self.busca_input.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.carregar_dados)
        self.busca_input.textChanged.connect(lambda: self._search_timer.start())
        btn_nova = QPushButton("+ Nova questão")
        btn_nova.setObjectName("primary-action")
        btn_nova.clicked.connect(self.abrir_nova_questao)
        top.addWidget(self.busca_input); top.addWidget(btn_nova); layout.addLayout(top)
        linha = QHBoxLayout()
        self.contagem = QLabel()
        self.contagem.setObjectName("section-hint")
        linha.addWidget(self.contagem, 1)
        linha.addWidget(self.filtro_gabarito)
        layout.addLayout(linha)
        self.tabela = QTableWidget(); self.tabela.setColumnCount(6); self.tabela.setHorizontalHeaderLabels(["ID", "Enunciado", "Disciplina", "Banca", "Ano", "Gabarito"])
        self.tabela.setObjectName("question-bank-table"); self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); self.tabela.setSelectionBehavior(QTableWidget.SelectRows); self.tabela.setEditTriggers(QTableWidget.NoEditTriggers); self.tabela.setAlternatingRowColors(True); self.tabela.setShowGrid(False); self.tabela.verticalHeader().setVisible(False); self.tabela.verticalHeader().setDefaultSectionSize(48); self.tabela.doubleClicked.connect(self.abrir_edicao_questao)
        layout.addWidget(self.tabela)
        self.empty = QLabel("Nenhuma questão encontrada. Altere a busca ou importe um caderno.")
        self.empty.setObjectName("empty-state")
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.carregar_dados()

    def showEvent(self, event):
        super().showEvent(event)
        self.carregar_dados()

    def carregar_dados(self):
        questoes = repo.buscar_questoes(texto=self.busca_input.text())
        filtro = self.filtro_gabarito.currentIndex()
        if filtro == 1:
            questoes = [q for q in questoes if not q.get("gabarito")]
        elif filtro == 2:
            questoes = [q for q in questoes if q.get("gabarito") and q["gabarito"] != "Anulada"]
        elif filtro == 3:
            questoes = [q for q in questoes if q.get("gabarito") == "Anulada"]
        elif filtro == 4:
            questoes = [q for q in questoes if problemas_estrutura(q)]
        self.contagem.setText(f"{len(questoes)} questões · clique duas vezes para editar")
        self.empty.setVisible(not questoes)
        self.tabela.setRowCount(len(questoes))
        for row, q in enumerate(questoes):
            valores = [q["id"], q["enunciado"][:50] + "..." if len(q["enunciado"]) > 50 else q["enunciado"], q["disciplina"] or "", q["banca"] or "", str(q["ano"]) if q["ano"] else "", q.get("gabarito") or "Sem gabarito"]
            for col, valor in enumerate(valores): self.tabela.setItem(row, col, QTableWidgetItem(str(valor)))
            self.tabela.item(row, 0).setData(Qt.UserRole, q)
            self.tabela.item(row, 1).setToolTip(q["enunciado"])
        self.tabela.setColumnWidth(0, 48)
        self.tabela.setColumnWidth(4, 70)
        for col in (2, 3, 5):
            self.tabela.setColumnWidth(col, 100)

    def abrir_nova_questao(self):
        if QuestaoDialog(parent=self).exec(): self.carregar_dados()

    def abrir_edicao_questao(self, index):
        dados = self.tabela.item(index.row(), 0).data(Qt.UserRole)
        if QuestaoDialog(questao_dados=dados, parent=self).exec(): self.carregar_dados()
