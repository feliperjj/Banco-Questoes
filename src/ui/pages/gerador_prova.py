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

        self.modo_input = QComboBox()
        self.modo_input.addItem("Questões aleatórias", "aleatoria")
        self.modo_input.addItem("Prova cadastrada/anexada", "cadastrada")
        form.addWidget(self._label("Origem"), 2, 0)
        form.addWidget(self.modo_input, 2, 1)

        self.prova_cadastrada_input = QComboBox()
        self.prova_cadastrada_input.setMinimumWidth(220)
        form.addWidget(self._label("Prova de origem"), 2, 2)
        form.addWidget(self.prova_cadastrada_input, 2, 3)

        self.disciplina_input = QComboBox()
        self.disciplina_input.addItem("Todas as disciplinas")
        self.disciplina_input.addItems(repo.listar_disciplinas())
        form.addWidget(self._label("Disciplina"), 3, 0)
        form.addWidget(self.disciplina_input, 3, 1)

        self.banca_input = QComboBox()
        self.banca_input.addItem("Todas as bancas")
        self.banca_input.addItems(repo.listar_bancas())
        form.addWidget(self._label("Banca"), 3, 2)
        form.addWidget(self.banca_input, 3, 3)

        self.topico_input = QComboBox()
        self.topico_input.addItem("Todas as categorias")
        self.topico_input.addItems(repo.listar_topicos())
        form.addWidget(self._label("Categoria"), 4, 0)
        form.addWidget(self.topico_input, 4, 1)

        self.tipo_input = QComboBox()
        self.tipo_input.addItem("Todos os tipos", "")
        self.tipo_input.addItem("Múltipla escolha", "multipla_escolha")
        self.tipo_input.addItem("Certo ou errado", "certo_errado")
        form.addWidget(self._label("Tipo de questão"), 4, 2)
        form.addWidget(self.tipo_input, 4, 3)

        self.qtd_input = QSpinBox()
        self.qtd_input.setRange(1, 200)
        self.qtd_input.setValue(10)
        self.qtd_input.setSuffix(" questões")
        form.addWidget(self._label("Quantidade"), 5, 0)
        form.addWidget(self.qtd_input, 5, 1)

        self.tempo_input = QSpinBox()
        self.tempo_input.setRange(0, 600)
        self.tempo_input.setSpecialValueText("Sem limite")
        self.tempo_input.setSuffix(" min")
        form.addWidget(self._label("Tempo limite"), 5, 2)
        form.addWidget(self.tempo_input, 5, 3)

        self.lbl_disponiveis = QLabel()
        self.lbl_disponiveis.setWordWrap(True)
        self.lbl_disponiveis.setObjectName("generator-availability")
        form.addWidget(self.lbl_disponiveis, 6, 0, 1, 3)

        gerar_btn = QPushButton("Gerar prova")
        gerar_btn.setObjectName("primary-action")
        gerar_btn.setCursor(Qt.PointingHandCursor)
        gerar_btn.setMinimumWidth(150)
        gerar_btn.clicked.connect(self.gerar_prova)
        form.addWidget(gerar_btn, 6, 3, alignment=Qt.AlignRight)
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
        self.banca_input.currentTextChanged.connect(self._atualizar_disponibilidade)
        self.topico_input.currentTextChanged.connect(self._atualizar_disponibilidade)
        self.tipo_input.currentIndexChanged.connect(self._atualizar_disponibilidade)
        self.modo_input.currentIndexChanged.connect(self._atualizar_modo)
        self.prova_cadastrada_input.currentIndexChanged.connect(self._atualizar_disponibilidade)
        self._carregar_provas_cadastradas()
        self._atualizar_modo()
        self.qtd_input.valueChanged.connect(self._atualizar_disponibilidade)
        self.carregar_provas()
        self._atualizar_disponibilidade()

    @staticmethod
    def _label(texto):
        label = QLabel(texto)
        label.setObjectName("field-label")
        return label

    def showEvent(self, event):
        super().showEvent(event)
        self._carregar_provas_cadastradas()
        self.carregar_provas()
        self._atualizar_disponibilidade()

    def gerar_prova(self):
        nome = self.nome_input.text().strip()
        if not nome:
            QMessageBox.warning(self, "Aviso", "Digite um nome para a prova.")
            return
        filtros = {}
        prova_cadastrada_id = None
        prova_existente_id = None
        if self.modo_input.currentData() == "cadastrada":
            origem = self.prova_cadastrada_input.currentData()
            if not origem:
                QMessageBox.warning(self, "Prova de origem", "Selecione uma prova cadastrada ou anexada.")
                return
            if origem[0] == "cadastrada":
                prova_cadastrada_id = origem[1]
            else:
                prova_existente_id = origem[1]
        else:
            disciplina = self.disciplina_input.currentText().strip()
            tipo = self.tipo_input.currentData()
            if disciplina and disciplina != "Todas as disciplinas":
                filtros["disciplina"] = disciplina
            banca = self.banca_input.currentText().strip()
            if banca and banca != "Todas as bancas":
                filtros["banca"] = banca
            topico = self.topico_input.currentText().strip()
            if topico and topico != "Todas as categorias":
                filtros["topico"] = topico
            if tipo:
                filtros["tipo"] = tipo
        try:
            prova_id = repo.criar_prova(
                nome,
                filtros,
                self.qtd_input.value(),
                self.tempo_input.value() or None,
                prova_cadastrada_id=prova_cadastrada_id,
                prova_existente_id=prova_existente_id,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Prova não criada", str(exc))
            return
        if prova_id == 0:
            QMessageBox.warning(self, "Aviso", "Nenhuma questão encontrada com estes filtros. A prova não foi criada.")
        else:
            logger.info("Prova %s criada", prova_id)
            quantidade = len(repo.buscar_questoes_da_prova(prova_id))
            mensagem = f"Prova gerada com {quantidade} questão(ões)."
            if quantidade < self.qtd_input.value():
                mensagem += f" Foram solicitadas {self.qtd_input.value()}, mas apenas {quantidade} estavam aptas com estes filtros."
            QMessageBox.information(self, "Sucesso", mensagem)
            self.nome_input.clear()
            self.carregar_provas()

    def _carregar_provas_cadastradas(self):
        selecionada = self.prova_cadastrada_input.currentData()
        self.prova_cadastrada_input.blockSignals(True)
        self.prova_cadastrada_input.clear()
        self.prova_cadastrada_input.addItem("Selecione uma prova", None)
        for prova in repo.listar_fontes_de_prova():
            estado = "pronta" if prova.get("pronta") else "incompleta"
            origem_tipo = "cadastrada/anexada" if prova["origem_tipo"] == "cadastrada" else "prova existente"
            self.prova_cadastrada_input.addItem(
                f"{prova['nome']} · {prova['qtd_questoes']} questões ({origem_tipo}; {estado})",
                (prova["origem_tipo"], prova["origem_id"]),
            )
        if selecionada:
            indice = self.prova_cadastrada_input.findData(selecionada)
            if indice >= 0:
                self.prova_cadastrada_input.setCurrentIndex(indice)
        self.prova_cadastrada_input.blockSignals(False)

    def _atualizar_modo(self):
        cadastrada = self.modo_input.currentData() == "cadastrada"
        self.prova_cadastrada_input.setEnabled(cadastrada)
        for campo in (self.disciplina_input, self.banca_input, self.topico_input, self.tipo_input, self.qtd_input):
            campo.setEnabled(not cadastrada)
        self._atualizar_disponibilidade()

    def _atualizar_disponibilidade(self):
        if self.modo_input.currentData() == "cadastrada":
            origem = self.prova_cadastrada_input.currentData()
            prova = next(
                (
                    item
                    for item in repo.listar_fontes_de_prova()
                    if (item["origem_tipo"], item["origem_id"]) == origem
                ),
                None,
            )
            if prova is None:
                texto = "Selecione uma prova cadastrada para reutilizar"
                vazio = True
            elif prova.get("pronta"):
                texto = f"{prova['qtd_questoes']} questão(ões) da prova original"
                vazio = False
            else:
                faltantes = prova["qtd_questoes"] - prova["qtd_avaliaveis"]
                texto = f"{faltantes} questão(ões) sem gabarito avaliável"
                vazio = True
            self.lbl_disponiveis.setText(texto)
            self.lbl_disponiveis.setProperty("empty", vazio)
            self.lbl_disponiveis.style().unpolish(self.lbl_disponiveis)
            self.lbl_disponiveis.style().polish(self.lbl_disponiveis)
            return
        filtros = {}
        disciplina = self.disciplina_input.currentText().strip()
        if disciplina and disciplina != "Todas as disciplinas":
            filtros["disciplina"] = disciplina
        banca = self.banca_input.currentText().strip()
        if banca and banca != "Todas as bancas":
            filtros["banca"] = banca
        topico = self.topico_input.currentText().strip()
        if topico and topico != "Todas as categorias":
            filtros["topico"] = topico
        if self.tipo_input.currentData():
            filtros["tipo"] = self.tipo_input.currentData()
        total = repo.contar_questoes_elegiveis(filtros)
        disponibilidade = f"{total} questão(ões) disponíveis"
        if 0 < total < self.qtd_input.value():
            disponibilidade += f". A prova terá {total} das {self.qtd_input.value()} solicitadas."
        self.lbl_disponiveis.setText(disponibilidade)
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
            status = QTableWidgetItem("Concluída" if concluida else ("Em andamento" if prova.get("em_andamento") else "Pendente"))
            status.setTextAlignment(Qt.AlignCenter)
            status.setData(Qt.UserRole, concluida)
            self.tabela.setItem(row, 3, status)
            if concluida:
                label = QLabel("✓ Concluída")
                label.setObjectName("table-completed-label")
                label.setAlignment(Qt.AlignCenter)
                self.tabela.setCellWidget(row, 4, label)
                continue

            botao = QPushButton("Retomar prova" if prova.get("em_andamento") else "Iniciar prova")
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
