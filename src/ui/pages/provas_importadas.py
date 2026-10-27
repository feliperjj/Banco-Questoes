from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import src.models.questoes_repo as repo
from src.ui.components.imported_exam_preview import ImportedExamPreviewDialog


class ProvasImportadasPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(16)

        titulo = QLabel("Provas importadas")
        titulo.setObjectName("page-title")
        subtitulo = QLabel("Consulte as questões de cada prova e acompanhe a liberação para resolver.")
        subtitulo.setObjectName("page-subtitle")
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)

        cartao = QFrame()
        cartao.setObjectName("generator-card")
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(20, 16, 20, 18)
        cartao_layout.setSpacing(12)

        cabecalho = QHBoxLayout()
        secao = QLabel("SEU ACERVO DE PROVAS")
        secao.setObjectName("section-kicker")
        cabecalho.addWidget(secao)
        cabecalho.addStretch()
        cartao_layout.addLayout(cabecalho)

        self.vazio = QLabel("As provas que você importar aparecerão aqui.")
        self.vazio.setObjectName("section-hint")
        self.vazio.setAlignment(Qt.AlignCenter)
        cartao_layout.addWidget(self.vazio)

        self.tabela = QTableWidget()
        self.tabela.setObjectName("imported-exam-table")
        self.tabela.setColumnCount(4)
        self.tabela.setHorizontalHeaderLabels(["Nome da prova", "Questões", "Status", "Ação"])
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setShowGrid(False)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.verticalHeader().setDefaultSectionSize(60)
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tabela.setColumnWidth(3, 174)
        self.tabela.horizontalHeaderItem(1).setTextAlignment(Qt.AlignCenter)
        self.tabela.horizontalHeaderItem(2).setTextAlignment(Qt.AlignCenter)
        self.tabela.horizontalHeaderItem(3).setTextAlignment(Qt.AlignCenter)
        cartao_layout.addWidget(self.tabela, 1)
        layout.addWidget(cartao, 1)

        self.carregar_provas()

    def showEvent(self, event):
        super().showEvent(event)
        self.carregar_provas()

    def carregar_provas(self):
        provas = repo.listar_provas_cadastradas()
        provas.extend(repo.listar_lotes_importados_sem_prova())
        self.vazio.setVisible(not provas)
        self.tabela.setVisible(bool(provas))
        self.tabela.clearContents()
        self.tabela.setRowCount(len(provas))

        for row, prova in enumerate(provas):
            self.tabela.setRowHeight(row, 60)
            self.tabela.setItem(row, 0, QTableWidgetItem(prova["nome"]))

            quantidade = QTableWidgetItem(str(prova["qtd_questoes"]))
            quantidade.setTextAlignment(Qt.AlignCenter)
            self.tabela.setItem(row, 1, quantidade)

            pronta = bool(prova.get("pronta"))
            if pronta:
                status_texto = "Pronta para resolver"
            else:
                status_texto = (
                    f"{prova['qtd_avaliaveis']}/{prova['qtd_questoes']} verificadas · treino parcial disponível"
                    if 0 < prova.get("qtd_avaliaveis", 0) < prova.get("qtd_questoes", 0) else
                    "Revisão pendente"
                    if prova["qtd_questoes"]
                    else "Sem questões importadas"
                )
                sem_gabarito = prova.get("qtd_sem_gabarito", 0)
                if sem_gabarito:
                    status_texto += f"\n{sem_gabarito} sem gabarito salvo"
            status = QTableWidgetItem(status_texto)
            status.setTextAlignment(Qt.AlignCenter)
            status.setToolTip(
                f"{prova.get('qtd_com_gabarito', 0)}/{prova['qtd_questoes']} com gabarito salvo. "
                f"{prova['qtd_avaliaveis']}/{prova['qtd_questoes']} liberadas após conferência. "
                "Um gabarito salvo pode ainda precisar de confirmação no original."
            )
            self.tabela.setItem(row, 2, status)

            botao = QPushButton("Ver questões")
            botao.setObjectName("table-action-button")
            botao.setMinimumWidth(132)
            botao.setMaximumWidth(154)
            botao.setFixedHeight(40)
            botao.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            botao.setToolTip("Consultar enunciados, alternativas e imagens sem iniciar uma tentativa")
            botao.setCursor(Qt.PointingHandCursor)
            botao.clicked.connect(
                lambda checked=False, item=dict(prova): self.ver_questoes(item)
            )
            container = QWidget()
            container.setObjectName("table-action-container")
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(6, 5, 6, 5)
            container_layout.setSpacing(0)
            container_layout.addStretch()
            container_layout.addWidget(botao, 0, Qt.AlignCenter)
            container_layout.addStretch()
            self.tabela.setCellWidget(row, 3, container)

    def ver_questoes(self, prova):
        try:
            if prova.get("origem_tipo") == "lote_importado":
                questoes = repo.consultar_questoes_importadas(questao_ids=prova["questao_ids"])
            else:
                questoes = repo.consultar_questoes_importadas(prova["id"])
        except ValueError as exc:
            QMessageBox.warning(self, "Não foi possível consultar a prova", str(exc))
            return
        dialog = ImportedExamPreviewDialog(prova, questoes, self)
        if dialog.exec() == QDialog.Accepted:
            self.fazer_prova(prova)
        self.carregar_provas()

    def fazer_prova(self, prova):
        nome = prova["nome"]
        stacked = self.parentWidget()
        execucao = next(
            (stacked.widget(i) for i in range(stacked.count())
             if type(stacked.widget(i)).__name__ == "ExecucaoProvaPage"),
            None,
        )
        if execucao is None:
            QMessageBox.critical(self, "Erro", "Tela de execução de prova não encontrada.")
            return
        if execucao.em_andamento:
            QMessageBox.information(
                self,
                "Prova em andamento",
                "Finalize a prova atual antes de iniciar outra.",
            )
            return

        try:
            if prova.get("origem_tipo") == "lote_importado":
                if 0 < prova.get("qtd_avaliaveis", 0) < prova.get("qtd_questoes", 0):
                    tentativa_prova_id = repo.criar_prova_parcial_importada(
                        nome, questao_ids=prova["questao_ids"]
                    )
                else:
                    tentativa_prova_id = repo.criar_prova_a_partir_de_questoes(
                        nome, prova["questao_ids"]
                    )
            elif 0 < prova.get("qtd_avaliaveis", 0) < prova.get("qtd_questoes", 0):
                tentativa_prova_id = repo.criar_prova_parcial_importada(
                    nome, prova_cadastrada_id=prova["id"]
                )
            else:
                tentativa_prova_id = repo.criar_prova(
                    nome,
                    {},
                    prova["qtd_questoes"],
                    None,
                    prova_cadastrada_id=prova["id"],
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Prova indisponível", str(exc))
            self.carregar_provas()
            return

        nome_execucao = repo.obter_prova(tentativa_prova_id)["nome"]
        execucao.iniciar(tentativa_prova_id, nome_execucao)
        indice = stacked.indexOf(execucao)
        stacked.setCurrentIndex(indice)
        menu = getattr(self.window(), "menu", None)
        if menu:
            menu.setCurrentRow(indice)
