import logging

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QProgressBar, QRadioButton, QTextEdit, QVBoxLayout, QWidget

import src.models.questoes_repo as repo
import src.models.revisao_service as revisao_svc

logger = logging.getLogger(__name__)


class ExecucaoProvaPage(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(34, 28, 34, 28)
        self.layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(14)
        self.lbl_info = QLabel("Prova não iniciada")
        self.lbl_info.setObjectName("exam-info")
        header.addWidget(self.lbl_info)
        header.addStretch()
        self.lbl_tempo = QLabel("00:00")
        self.lbl_tempo.setObjectName("timer-label")
        header.addWidget(self.lbl_tempo)
        self.layout.addLayout(header)

        self.lbl_progresso = QLabel("Questão 0 de 0")
        self.lbl_progresso.setObjectName("exam-progress-label")
        self.layout.addWidget(self.lbl_progresso)
        self.barra_progresso = QProgressBar()
        self.barra_progresso.setObjectName("exam-progress")
        self.barra_progresso.setTextVisible(False)
        self.barra_progresso.setRange(0, 1)
        self.barra_progresso.setValue(0)
        self.layout.addWidget(self.barra_progresso)

        self.cartao_questao = QFrame()
        self.cartao_questao.setObjectName("exam-question-card")
        cartao_layout = QVBoxLayout(self.cartao_questao)
        cartao_layout.setContentsMargins(24, 22, 24, 24)
        cartao_layout.setSpacing(14)
        self.lbl_tipo_questao = QLabel("ENUNCIADO")
        self.lbl_tipo_questao.setObjectName("exam-question-kicker")
        cartao_layout.addWidget(self.lbl_tipo_questao)
        self.lbl_enunciado = QTextEdit()
        self.lbl_enunciado.setObjectName("exam-statement")
        self.lbl_enunciado.setReadOnly(True)
        cartao_layout.addWidget(self.lbl_enunciado)
        self.alternativas_frame = QFrame()
        self.alternativas_frame.setObjectName("exam-options-card")
        self.alternativas_layout = QVBoxLayout(self.alternativas_frame)
        self.alternativas_layout.setContentsMargins(12, 10, 12, 10)
        self.alternativas_layout.setSpacing(8)
        cartao_layout.addWidget(self.alternativas_frame)
        self.layout.addWidget(self.cartao_questao, 1)

        nav = QHBoxLayout()
        nav.setSpacing(10)
        self.btn_anterior = QPushButton("‹  Anterior")
        self.btn_anterior.setObjectName("secondary-button")
        self.btn_anterior.clicked.connect(self.questao_anterior)
        self.btn_proxima = QPushButton("Próxima  ›")
        self.btn_proxima.clicked.connect(self.proxima_questao)
        self.btn_finalizar = QPushButton("Finalizar prova")
        self.btn_finalizar.setObjectName("danger-button")
        self.btn_finalizar.clicked.connect(self.confirmar_finalizacao)
        nav.addWidget(self.btn_anterior)
        nav.addWidget(self.btn_proxima)
        nav.addStretch()
        nav.addWidget(self.btn_finalizar)
        self.layout.addLayout(nav)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.atualizar_tempo)
        self.prova_id = None
        self.tentativa_id = None
        self.questoes = []
        self.idx_atual = 0
        self.respostas_memoria = {}
        self.tempo_gasto = 0

    def iniciar(self, prova_id, nome_prova):
        self.prova_id = prova_id
        self.questoes = repo.buscar_questoes_da_prova(prova_id)
        if not self.questoes:
            QMessageBox.critical(self, "Erro", "Esta prova não possui questões.")
            return
        self.tentativa_id = repo.iniciar_tentativa(prova_id)
        self.lbl_info.setText(f"{nome_prova}  ·  {len(self.questoes)} questões")
        self.idx_atual = 0
        self.respostas_memoria = {}
        self.tempo_gasto = 0
        self.lbl_tempo.setText("00:00")
        self.barra_progresso.setRange(0, len(self.questoes))
        self.timer.start(1000)
        self.mostrar_questao_atual()
        logger.info("Tentativa %s iniciada para prova %s", self.tentativa_id, prova_id)

    def atualizar_tempo(self):
        self.tempo_gasto += 1
        self.lbl_tempo.setText(f"{self.tempo_gasto // 60:02d}:{self.tempo_gasto % 60:02d}")

    def limpar_alternativas(self):
        for button in self.grupo_botoes.buttons():
            self.grupo_botoes.removeButton(button)
            button.deleteLater()
        while self.alternativas_layout.count():
            item = self.alternativas_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def mostrar_questao_atual(self):
        q = self.questoes[self.idx_atual]
        numero = self.idx_atual + 1
        self.lbl_progresso.setText(f"Questão {numero} de {len(self.questoes)}")
        self.barra_progresso.setValue(numero)
        self.lbl_tipo_questao.setText((q.get("disciplina") or "QUESTÃO").upper())
        self.lbl_enunciado.setText(q["enunciado"])
        self.limpar_alternativas()
        opcoes = [(a["letra"], f"{a['letra']})  {a['texto']}") for a in q.get("alternativas", [])] if q["tipo"] == "multipla_escolha" else [("Certo", "Certo"), ("Errado", "Errado")]
        if not opcoes:
            opcoes = [(letra, letra) for letra in "ABCDE"]
        for valor, rotulo in opcoes:
            rb = QRadioButton(rotulo)
            rb.setObjectName("exam-option")
            self.alternativas_layout.addWidget(rb)
            if self.respostas_memoria.get(q["id"]) == valor:
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, o=valor, qid=q["id"]: self.salvar_resposta_temp(checked, qid, o))
        self.btn_anterior.setEnabled(self.idx_atual > 0)
        self.btn_proxima.setEnabled(self.idx_atual < len(self.questoes) - 1)

    def salvar_resposta_temp(self, checked, q_id, opcao):
        if checked:
            self.respostas_memoria[q_id] = opcao

    def questao_anterior(self):
        if self.idx_atual > 0:
            self.idx_atual -= 1
            self.mostrar_questao_atual()

    def proxima_questao(self):
        if self.idx_atual < len(self.questoes) - 1:
            self.idx_atual += 1
            self.mostrar_questao_atual()

    def confirmar_finalizacao(self):
        if len(self.respostas_memoria) < len(self.questoes) and QMessageBox.question(self, "Aviso", "Existem questões sem resposta. Deseja finalizar mesmo assim?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
            return
        self.timer.stop()
        resultado = repo.finalizar_tentativa(self.tentativa_id, self.respostas_memoria, self.tempo_gasto)
        for errada in resultado["erradas"]:
            revisao_svc.registrar_erro(errada["id"])
        logger.info("Tentativa %s finalizada: nota %.1f", self.tentativa_id, resultado["nota"])
        self.mostrar_resultado(resultado)

    def mostrar_resultado(self, resultado):
        msg = f"Prova finalizada!\n\nNota: {resultado['nota']:.1f} / 100\nAcertos: {resultado['acertos']} de {resultado['total']}\nTempo: {self.lbl_tempo.text()}"
        if resultado["erradas"]:
            msg += "\n\nQuestões erradas:" + "".join(f"\n- Q_ID {e['id']} (Marcada: {e['marcada']} | Correta: {e['correta']})" for e in resultado["erradas"][:5])
        QMessageBox.information(self, "Resultado", msg)
        if self.parentWidget() and hasattr(self.parentWidget(), "setCurrentIndex"):
            self.parentWidget().setCurrentIndex(3)
