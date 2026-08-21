from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QMessageBox, QProgressBar, QPushButton, QRadioButton, QTextEdit, QVBoxLayout, QWidget

import src.models.revisao_service as revisao_svc


class RevisaoPage(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(34, 28, 34, 28)
        self.layout.setSpacing(14)
        self.lbl_titulo = QLabel("Revisão espaçada")
        self.lbl_titulo.setObjectName("page-title")
        self.layout.addWidget(self.lbl_titulo)
        self.lbl_subtitulo = QLabel("Revise um pouco por dia para consolidar o conteúdo.")
        self.lbl_subtitulo.setObjectName("page-subtitle")
        self.layout.addWidget(self.lbl_subtitulo)
        self.lbl_progresso = QLabel("Sua fila está pronta quando você estiver.")
        self.lbl_progresso.setObjectName("review-progress-label")
        self.layout.addWidget(self.lbl_progresso)
        self.barra_progresso = QProgressBar()
        self.barra_progresso.setObjectName("review-progress")
        self.barra_progresso.setTextVisible(False)
        self.barra_progresso.setRange(0, 1)
        self.barra_progresso.setValue(0)
        self.layout.addWidget(self.barra_progresso)
        self.cartao = QFrame()
        self.cartao.setObjectName("review-card")
        self.conteudo_layout = QVBoxLayout(self.cartao)
        self.conteudo_layout.setContentsMargins(24, 22, 24, 24)
        self.conteudo_layout.setSpacing(14)
        self.layout.addWidget(self.cartao, 1)
        self.btn_iniciar = QPushButton("Começar revisão")
        self.btn_iniciar.clicked.connect(self.carregar_revisao)
        self.layout.addWidget(self.btn_iniciar)
        self.questoes = []
        self.idx_atual = 0

    def carregar_revisao(self):
        self.questoes = revisao_svc.questoes_para_revisar_hoje()
        if not self.questoes:
            self.limpar_area()
            vazio = QLabel("Sua fila está em dia.\nVolte mais tarde para revisar novos conteúdos.")
            vazio.setObjectName("empty-state")
            vazio.setAlignment(Qt.AlignCenter)
            self.conteudo_layout.addWidget(vazio)
            self.btn_iniciar.setText("Atualizar fila")
            return
        self.idx_atual = 0
        self.btn_iniciar.hide()
        self.barra_progresso.setRange(0, len(self.questoes))
        self.mostrar_questao()

    def limpar_area(self):
        while self.conteudo_layout.count():
            item = self.conteudo_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def mostrar_questao(self):
        self.limpar_area()
        q = self.questoes[self.idx_atual]
        numero = self.idx_atual + 1
        self.lbl_progresso.setText(f"Questão {numero} de {len(self.questoes)}")
        self.barra_progresso.setValue(numero)
        kicker = QLabel((q.get("disciplina") or "REVISÃO").upper())
        kicker.setObjectName("review-kicker")
        self.conteudo_layout.addWidget(kicker)
        enunciado = QTextEdit(q["enunciado"])
        enunciado.setObjectName("review-statement")
        enunciado.setReadOnly(True)
        self.conteudo_layout.addWidget(enunciado)
        opcoes = [(a["letra"], f"{a['letra']})  {a['texto']}") for a in q.get("alternativas", [])] if q["tipo"] == "multipla_escolha" else [("Certo", "Certo"), ("Errado", "Errado")]
        self.grupo = QButtonGroup(self)
        opcoes_frame = QFrame()
        opcoes_frame.setObjectName("review-options-card")
        opcoes_layout = QVBoxLayout(opcoes_frame)
        opcoes_layout.setContentsMargins(10, 8, 10, 8)
        opcoes_layout.setSpacing(7)
        for valor, rotulo in opcoes:
            rb = QRadioButton(rotulo)
            rb.setObjectName("review-option")
            rb.setProperty("valor_gabarito", valor)
            self.grupo.addButton(rb)
            opcoes_layout.addWidget(rb)
        self.conteudo_layout.addWidget(opcoes_frame)
        btn = QPushButton("Confirmar resposta")
        btn.clicked.connect(lambda: self.avaliar_resposta(q))
        self.conteudo_layout.addWidget(btn)

    def avaliar_resposta(self, q):
        selecionado = self.grupo.checkedButton()
        if not selecionado:
            QMessageBox.warning(self, "Resposta pendente", "Selecione uma alternativa para continuar.")
            return
        acertou = selecionado.property("valor_gabarito") == q["gabarito"]
        revisao_svc.processar_revisao(q["id"], acertou)
        if acertou:
            QMessageBox.information(self, "Muito bem", "Resposta correta. Esta questão foi reagendada.")
        else:
            QMessageBox.critical(self, "Vamos reforçar", f"O gabarito era {q['gabarito']}. A questão voltará para sua fila.")
        if self.idx_atual < len(self.questoes) - 1:
            self.idx_atual += 1
            self.mostrar_questao()
        else:
            self.limpar_area()
            concluido = QLabel("Revisão concluída!\nVocê fechou a fila de hoje.")
            concluido.setObjectName("empty-state")
            concluido.setAlignment(Qt.AlignCenter)
            self.conteudo_layout.addWidget(concluido)
            self.lbl_progresso.setText(f"{len(self.questoes)} questões revisadas")
            self.btn_iniciar.setText("Carregar nova fila")
            self.btn_iniciar.show()
