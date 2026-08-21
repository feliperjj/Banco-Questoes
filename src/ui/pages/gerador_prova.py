import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QHeaderView, QLabel, QListWidget, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHBoxLayout

import src.models.questoes_repo as repo

logger = logging.getLogger(__name__)


class GeradorProvaPage(QWidget):
    def __init__(self):
        super().__init__(); layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); group = QGroupBox("Criar Nova Prova"); form = QFormLayout(group)
        from PySide6.QtWidgets import QLineEdit
        self.nome_input = QLineEdit(); form.addRow("Nome da Prova:", self.nome_input)
        self.disciplina_input = QComboBox(); self.disciplina_input.addItem("Todas as disciplinas"); self.disciplina_input.addItems(repo.listar_disciplinas()); self.disciplina_input.setCurrentIndex(0); form.addRow("Filtro - Disciplina:", self.disciplina_input)
        self.topico_input = QComboBox(); self.topico_input.addItem("Todas as categorias"); self.topico_input.addItems(repo.listar_topicos()); self.topico_input.setCurrentIndex(0); form.addRow("Filtro - Categoria:", self.topico_input)
        self.tipo_input = QComboBox(); self.tipo_input.addItem("Todos os tipos", ""); self.tipo_input.addItem("Múltipla escolha", "multipla_escolha"); self.tipo_input.addItem("Certo ou errado", "certo_errado"); form.addRow("Tipo de questão:", self.tipo_input)
        self.lbl_disponiveis = QLabel(); self.lbl_disponiveis.setObjectName("generator-availability"); form.addRow("Disponibilidade:", self.lbl_disponiveis)
        self.qtd_input = QSpinBox(); self.qtd_input.setRange(1, 200); self.qtd_input.setValue(10); form.addRow("Quantidade de Questões:", self.qtd_input)
        self.tempo_input = QSpinBox(); self.tempo_input.setRange(0, 600); self.tempo_input.setSpecialValueText("Sem limite"); form.addRow("Tempo Limite (min):", self.tempo_input)
        btn = QPushButton("Gerar Prova"); btn.clicked.connect(self.gerar_prova); form.addRow(btn); layout.addWidget(group)
        self.disciplina_input.currentTextChanged.connect(self._atualizar_disponibilidade)
        self.topico_input.currentTextChanged.connect(self._atualizar_disponibilidade)
        self.tipo_input.currentIndexChanged.connect(self._atualizar_disponibilidade)
        self.tabela = QTableWidget(); self.tabela.setColumnCount(4); self.tabela.setHorizontalHeaderLabels(["ID", "Nome da Prova", "Qtd Questões", "Ação"]); self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents); self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); self.tabela.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents); self.tabela.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed); self.tabela.setColumnWidth(3, 146); self.tabela.horizontalHeaderItem(3).setTextAlignment(Qt.AlignCenter); layout.addWidget(self.tabela); self.carregar_provas(); self._atualizar_disponibilidade()

    def gerar_prova(self):
        nome = self.nome_input.text().strip()
        if not nome: QMessageBox.warning(self, "Aviso", "Digite um nome para a prova."); return
        filtros = {}
        disciplina = self.disciplina_input.currentText().strip()
        tipo = self.tipo_input.currentData()
        if disciplina and disciplina != "Todas as disciplinas": filtros["disciplina"] = disciplina
        topico = self.topico_input.currentText().strip()
        if topico and topico != "Todas as categorias": filtros["topico"] = topico
        if tipo: filtros["tipo"] = tipo
        prova_id = repo.criar_prova(nome, filtros, self.qtd_input.value(), self.tempo_input.value() or None)
        if prova_id == 0: QMessageBox.warning(self, "Aviso", "Nenhuma questão encontrada com estes filtros. A prova não foi criada.")
        else: logger.info("Prova %s criada", prova_id); QMessageBox.information(self, "Sucesso", "Prova gerada com sucesso!"); self.nome_input.clear(); self.carregar_provas()

    def _atualizar_disponibilidade(self):
        disciplina = self.disciplina_input.currentText().strip()
        filtros = {}
        if disciplina and disciplina != "Todas as disciplinas":
            filtros["disciplina"] = disciplina
        topico = self.topico_input.currentText().strip()
        if topico and topico != "Todas as categorias":
            filtros["topico"] = topico
        if self.tipo_input.currentData():
            filtros["tipo"] = self.tipo_input.currentData()
        total = len(repo.buscar_questoes(filtros))
        self.lbl_disponiveis.setText(f"{total} questão(ões) disponíveis para este filtro")
        self.lbl_disponiveis.setProperty("empty", total == 0)
        self.lbl_disponiveis.style().unpolish(self.lbl_disponiveis)
        self.lbl_disponiveis.style().polish(self.lbl_disponiveis)

    def carregar_provas(self):
        provas = repo.listar_provas(); self.tabela.setRowCount(len(provas)); self.tabela.verticalHeader().setDefaultSectionSize(48)
        for row, p in enumerate(provas):
            self.tabela.setItem(row, 0, QTableWidgetItem(str(p["id"]))); self.tabela.setItem(row, 1, QTableWidgetItem(p["nome"])); self.tabela.setItem(row, 2, QTableWidgetItem(str(p["qtd_questoes"])))
            btn = QPushButton("Iniciar prova"); btn.setObjectName("table-action-button"); btn.setFixedSize(124, 32); btn.setToolTip("Iniciar prova"); btn.setCursor(Qt.PointingHandCursor); btn.clicked.connect(lambda checked, pid=p["id"], linha=row: self.iniciar_prova(pid, linha))
            container = QWidget(); container_layout = QHBoxLayout(container); container_layout.setContentsMargins(6, 4, 6, 4); container_layout.setAlignment(btn, Qt.AlignCenter); container_layout.addWidget(btn); self.tabela.setCellWidget(row, 3, container)

    def iniciar_prova(self, prova_id, row=None):
        stacked = self.parentWidget(); pagina = next((stacked.widget(i) for i in range(stacked.count()) if type(stacked.widget(i)).__name__ == "ExecucaoProvaPage"), None)
        if pagina:
            indice = stacked.indexOf(pagina); row = self.tabela.currentRow() if row is None else row; nome = self.tabela.item(row, 1).text() if row >= 0 else "Prova"; pagina.iniciar(prova_id, nome); stacked.setCurrentIndex(indice)
            janela = self.window()
            menu = getattr(janela, "menu", None)
            if menu: menu.setCurrentRow(indice)
        else: QMessageBox.critical(self, "Erro", "Tela de execução de prova não encontrada!")
