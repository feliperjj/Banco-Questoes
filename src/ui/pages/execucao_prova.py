import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QMessageBox, QPushButton, QRadioButton, QTextEdit, QVBoxLayout, QWidget

import src.models.questoes_repo as repo
import src.models.revisao_service as revisao_svc

logger = logging.getLogger(__name__)


class ExecucaoProvaPage(QWidget):
    def __init__(self):
        super().__init__(); self.layout = QVBoxLayout(self); self.layout.setContentsMargins(28, 24, 28, 24); header = QHBoxLayout(); self.lbl_info = QLabel("Prova não iniciada"); self.lbl_info.setObjectName("exam-info"); self.lbl_tempo = QLabel("00:00"); self.lbl_tempo.setObjectName("timer-label"); header.addWidget(self.lbl_info); header.addStretch(); header.addWidget(self.lbl_tempo); self.layout.addLayout(header)
        self.lbl_enunciado = QTextEdit(); self.lbl_enunciado.setReadOnly(True); self.layout.addWidget(self.lbl_enunciado); self.alternativas_layout = QVBoxLayout(); self.grupo_botoes = QButtonGroup(self); self.layout.addLayout(self.alternativas_layout)
        nav = QHBoxLayout(); self.btn_anterior = QPushButton("‹  Anterior"); self.btn_anterior.setObjectName("secondary-button"); self.btn_anterior.clicked.connect(self.questao_anterior); self.btn_proxima = QPushButton("Próxima  ›"); self.btn_proxima.setObjectName("secondary-button"); self.btn_proxima.clicked.connect(self.proxima_questao); self.btn_finalizar = QPushButton("Finalizar Prova"); self.btn_finalizar.setObjectName("danger-button"); self.btn_finalizar.clicked.connect(self.confirmar_finalizacao); nav.addWidget(self.btn_anterior); nav.addWidget(self.btn_proxima); nav.addStretch(); nav.addWidget(self.btn_finalizar); self.layout.addLayout(nav)
        self.timer = QTimer(self); self.timer.timeout.connect(self.atualizar_tempo); self.prova_id = None; self.tentativa_id = None; self.questoes = []; self.idx_atual = 0; self.respostas_memoria = {}; self.tempo_gasto = 0

    def iniciar(self, prova_id, nome_prova):
        self.prova_id = prova_id; self.questoes = repo.buscar_questoes_da_prova(prova_id)
        if not self.questoes: QMessageBox.critical(self, "Erro", "Esta prova não possui questões."); return
        self.tentativa_id = repo.iniciar_tentativa(prova_id); self.lbl_info.setText(f"Executando: {nome_prova} | {len(self.questoes)} questões"); self.idx_atual = 0; self.respostas_memoria = {}; self.tempo_gasto = 0; self.lbl_tempo.setText("00:00"); self.timer.start(1000); self.mostrar_questao_atual(); logger.info("Tentativa %s iniciada para prova %s", self.tentativa_id, prova_id)

    def atualizar_tempo(self):
        self.tempo_gasto += 1; self.lbl_tempo.setText(f"{self.tempo_gasto // 60:02d}:{self.tempo_gasto % 60:02d}")

    def limpar_alternativas(self):
        for button in self.grupo_botoes.buttons(): self.grupo_botoes.removeButton(button)
        while self.alternativas_layout.count():
            widget = self.alternativas_layout.takeAt(0).widget()
            if widget: widget.deleteLater()

    def mostrar_questao_atual(self):
        q = self.questoes[self.idx_atual]; self.lbl_enunciado.setText(f"Questão {self.idx_atual + 1}:\n\n{q['enunciado']}"); self.limpar_alternativas()
        opcoes = [(a["letra"], f"{a['letra']}) {a['texto']}") for a in q.get("alternativas", [])] if q["tipo"] == "multipla_escolha" else [("Certo", "Certo"), ("Errado", "Errado")]
        if not opcoes: opcoes = [(letra, letra) for letra in "ABCDE"]
        for valor, rotulo in opcoes:
            rb = QRadioButton(rotulo); self.alternativas_layout.addWidget(rb); self.grupo_botoes.addButton(rb)
            if self.respostas_memoria.get(q["id"]) == valor: rb.setChecked(True)
            rb.toggled.connect(lambda checked, o=valor, qid=q["id"]: self.salvar_resposta_temp(checked, qid, o))
        self.btn_anterior.setEnabled(self.idx_atual > 0); self.btn_proxima.setEnabled(self.idx_atual < len(self.questoes) - 1)

    def salvar_resposta_temp(self, checked, q_id, opcao):
        if checked: self.respostas_memoria[q_id] = opcao

    def questao_anterior(self):
        if self.idx_atual > 0: self.idx_atual -= 1; self.mostrar_questao_atual()

    def proxima_questao(self):
        if self.idx_atual < len(self.questoes) - 1: self.idx_atual += 1; self.mostrar_questao_atual()

    def confirmar_finalizacao(self):
        if len(self.respostas_memoria) < len(self.questoes) and QMessageBox.question(self, "Aviso", "Existem questões sem resposta! Deseja finalizar mesmo assim?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.No: return
        self.timer.stop(); resultado = repo.finalizar_tentativa(self.tentativa_id, self.respostas_memoria, self.tempo_gasto)
        for errada in resultado["erradas"]: revisao_svc.registrar_erro(errada["id"])
        logger.info("Tentativa %s finalizada: nota %.1f", self.tentativa_id, resultado["nota"]); self.mostrar_resultado(resultado)

    def mostrar_resultado(self, resultado):
        msg = f"Prova finalizada!\n\nNota: {resultado['nota']:.1f} / 100\nAcertos: {resultado['acertos']} de {resultado['total']}\nTempo: {self.lbl_tempo.text()}"
        if resultado["erradas"]:
            msg += "\n\nQuestões erradas:" + "".join(f"\n- Q_ID {e['id']} (Marcou: {e['marcada']} | Correto: {e['correta']})" for e in resultado["erradas"][:5])
        QMessageBox.information(self, "Resultado", msg)
        if self.parentWidget() and hasattr(self.parentWidget(), "setCurrentIndex"): self.parentWidget().setCurrentIndex(3)
