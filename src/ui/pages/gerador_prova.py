import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSizePolicy,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import src.models.questoes_repo as repo

logger = logging.getLogger(__name__)


class GeradorProvaPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(16)

        titulo = QLabel("Gerar prova")
        titulo.setObjectName("page-title")
        subtitulo = QLabel("Monte uma prova personalizada e acompanhe as tentativas já criadas.")
        subtitulo.setObjectName("page-subtitle")
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)

        card = QFrame()
        card.setObjectName("generator-card")
        form = QGridLayout(card)
        form.setContentsMargins(22, 18, 22, 20)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        kicker = QLabel("CONFIGURAÇÃO DA PROVA")
        kicker.setObjectName("section-kicker")
        form.addWidget(kicker, 0, 0, 1, 4)

        self.nome_input = QLineEdit()
        self.nome_input.setPlaceholderText("Ex.: Simulado de Direito Administrativo")
        form.addWidget(self._label("Nome"), 1, 0)
        form.addWidget(self.nome_input, 1, 1, 1, 3)

        self.disciplina_input = QComboBox()
        self.disciplina_input.addItem("Todas as disciplinas")
        self.disciplina_input.addItems(repo.listar_disciplinas())
        form.addWidget(self._label("Disciplina"), 2, 0)
        form.addWidget(self.disciplina_input, 2, 1)

        self.topico_input = QComboBox()
        self.topico_input.addItem("Todas as categorias")
        self.topico_input.addItems(repo.listar_topicos())
        form.addWidget(self._label("Categoria"), 2, 2)
        form.addWidget(self.topico_input, 2, 3)

        self.tipo_input = QComboBox()
        self.tipo_input.addItem("Todos os tipos", "")
        self.tipo_input.addItem("Múltipla escolha", "multipla_escolha")
        self.tipo_input.addItem("Certo ou errado", "certo_errado")
        form.addWidget(self._label("Tipo de questão"), 3, 0)
        form.addWidget(self.tipo_input, 3, 1)

        self.qtd_input = QSpinBox()
        self.qtd_input.setRange(1, 200)
        self.qtd_input.setValue(10)
        self.qtd_input.setSuffix(" questões")
        form.addWidget(self._label("Quantidade"), 3, 2)
        form.addWidget(self.qtd_input, 3, 3)

        self.tempo_input = QSpinBox()
        self.tempo_input.setRange(0, 600)
        self.tempo_input.setSpecialValueText("Sem limite")
        self.tempo_input.setSuffix(" min")
        form.addWidget(self._label("Tempo limite"), 4, 0)
        form.addWidget(self.tempo_input, 4, 1)

        self.lbl_disponiveis = QLabel()
        self.lbl_disponiveis.setObjectName("generator-availability")
        form.addWidget(self.lbl_disponiveis, 4, 2, 1, 2)

        gerar_btn = QPushButton("Gerar prova")
        gerar_btn.setObjectName("primary-action")
        gerar_btn.setCursor(Qt.PointingHandCursor)
        gerar_btn.setMinimumWidth(150)
        gerar_btn.clicked.connect(self.gerar_prova)
        form.addWidget(gerar_btn, 5, 3, alignment=Qt.AlignRight)
        layout.addWidget(card)

        historico = QHBoxLayout()
        titulo_historico = QLabel("Suas provas")
        titulo_historico.setObjectName("section-title")
        historico.addWidget(titulo_historico)
        historico.addStretch()
        dica = QLabel("Clique em uma prova pendente para começar")
        dica.setObjectName("section-hint")
        historico.addWidget(dica)
        layout.addLayout(historico)

        self.tabela = QTableWidget()
        self.tabela.setObjectName("exam-table")
        self.tabela.setColumnCount(5)
        self.tabela.setHorizontalHeaderLabels(["ID", "Nome da prova", "Questões", "Status", "Ação"])
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setShowGrid(False)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.verticalHeader().setDefaultSectionSize(60)
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tabela.setColumnWidth(4, 174)
        self.tabela.horizontalHeaderItem(3).setTextAlignment(Qt.AlignCenter)
        self.tabela.horizontalHeaderItem(4).setTextAlignment(Qt.AlignCenter)
        layout.addWidget(self.tabela, 1)

        self.disciplina_input.currentTextChanged.connect(self._atualizar_disponibilidade)
        self.topico_input.currentTextChanged.connect(self._atualizar_disponibilidade)
        self.tipo_input.currentIndexChanged.connect(self._atualizar_disponibilidade)
        self.carregar_provas()
        self._atualizar_disponibilidade()

    @staticmethod
    def _label(texto):
        label = QLabel(texto)
        label.setObjectName("field-label")
        return label

    def showEvent(self, event):
        super().showEvent(event)
        self.carregar_provas()
        self._atualizar_disponibilidade()

    def gerar_prova(self):
        nome = self.nome_input.text().strip()
        if not nome:
            QMessageBox.warning(self, "Aviso", "Digite um nome para a prova.")
            return
        filtros = {}
        disciplina = self.disciplina_input.currentText().strip()
        tipo = self.tipo_input.currentData()
        if disciplina and disciplina != "Todas as disciplinas":
            filtros["disciplina"] = disciplina
        topico = self.topico_input.currentText().strip()
        if topico and topico != "Todas as categorias":
            filtros["topico"] = topico
        if tipo:
            filtros["tipo"] = tipo
        prova_id = repo.criar_prova(nome, filtros, self.qtd_input.value(), self.tempo_input.value() or None)
        if prova_id == 0:
            QMessageBox.warning(self, "Aviso", "Nenhuma questão encontrada com estes filtros. A prova não foi criada.")
        else:
            logger.info("Prova %s criada", prova_id)
            QMessageBox.information(self, "Sucesso", "Prova gerada com sucesso!")
            self.nome_input.clear()
            self.carregar_provas()

    def _atualizar_disponibilidade(self):
        filtros = {}
        disciplina = self.disciplina_input.currentText().strip()
        if disciplina and disciplina != "Todas as disciplinas":
            filtros["disciplina"] = disciplina
        topico = self.topico_input.currentText().strip()
        if topico and topico != "Todas as categorias":
            filtros["topico"] = topico
        if self.tipo_input.currentData():
            filtros["tipo"] = self.tipo_input.currentData()
        total = len(repo.buscar_questoes(filtros))
        self.lbl_disponiveis.setText(f"{total} questão(ões) disponíveis")
        self.lbl_disponiveis.setProperty("empty", total == 0)
        self.lbl_disponiveis.style().unpolish(self.lbl_disponiveis)
        self.lbl_disponiveis.style().polish(self.lbl_disponiveis)

    def carregar_provas(self):
        provas = repo.listar_provas(incluir_concluidas=True)
        self.tabela.clearContents()
        self.tabela.setRowCount(len(provas))
        for row, prova in enumerate(provas):
            self.tabela.setRowHeight(row, 60)
            self.tabela.setItem(row, 0, QTableWidgetItem(str(prova["id"])))
            self.tabela.setItem(row, 1, QTableWidgetItem(prova["nome"]))
            quantidade = QTableWidgetItem(str(prova["qtd_questoes"]))
            quantidade.setTextAlignment(Qt.AlignCenter)
            self.tabela.setItem(row, 2, quantidade)
            concluida = bool(prova.get("concluida"))
            status = QTableWidgetItem("Concluída" if concluida else "Pendente")
            status.setTextAlignment(Qt.AlignCenter)
            status.setData(Qt.UserRole, concluida)
            self.tabela.setItem(row, 3, status)
            if concluida:
                label = QLabel("✓ Concluída")
                label.setObjectName("table-completed-label")
                label.setAlignment(Qt.AlignCenter)
                self.tabela.setCellWidget(row, 4, label)
                continue

            botao = QPushButton("Iniciar prova")
            botao.setObjectName("table-action-button")
            botao.setMinimumWidth(132)
            botao.setMaximumWidth(154)
            # A altura é deliberadamente fixa: estilos e escala de DPI não
            # podem reduzir a área clicável dentro da célula da tabela.
            botao.setFixedHeight(40)
            botao.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            botao.setToolTip("Iniciar esta prova")
            botao.setCursor(Qt.PointingHandCursor)
            botao.clicked.connect(
                lambda checked=False, pid=prova["id"], linha=row: self.iniciar_prova(pid, linha)
            )
            container = QWidget()
            container.setObjectName("table-action-container")
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(6, 5, 6, 5)
            container_layout.setSpacing(0)
            container_layout.addStretch()
            container_layout.addWidget(botao, 0, Qt.AlignCenter)
            container_layout.addStretch()
            self.tabela.setCellWidget(row, 4, container)

    def iniciar_prova(self, prova_id, row=None):
        if prova_id not in {prova["id"] for prova in repo.listar_provas()}:
            QMessageBox.information(self, "Prova já finalizada", "Esta prova já foi finalizada e não está mais pendente.")
            self.carregar_provas()
            return
        stacked = self.parentWidget()
        pagina = next(
            (stacked.widget(i) for i in range(stacked.count())
             if type(stacked.widget(i)).__name__ == "ExecucaoProvaPage"),
            None,
        )
        if pagina:
            indice = stacked.indexOf(pagina)
            row = self.tabela.currentRow() if row is None else row
            nome = self.tabela.item(row, 1).text() if row >= 0 else "Prova"
            pagina.iniciar(prova_id, nome)
            stacked.setCurrentIndex(indice)
            menu = getattr(self.window(), "menu", None)
            if menu:
                menu.setCurrentRow(indice)
        else:
            QMessageBox.critical(self, "Erro", "Tela de execução de prova não encontrada!")
