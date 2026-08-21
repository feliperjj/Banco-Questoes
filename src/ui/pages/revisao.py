from PySide6.QtWidgets import QButtonGroup, QLabel, QMessageBox, QPushButton, QRadioButton, QTextEdit, QVBoxLayout, QWidget
import src.models.revisao_service as revisao_svc


class RevisaoPage(QWidget):
    def __init__(self):
        super().__init__(); self.layout = QVBoxLayout(self); self.layout.setContentsMargins(28, 24, 28, 24); self.lbl_titulo = QLabel("Fila de Revisão de Hoje"); self.lbl_titulo.setObjectName("page-title"); self.layout.addWidget(self.lbl_titulo); self.area_conteudo = QWidget(); self.conteudo_layout = QVBoxLayout(self.area_conteudo); self.layout.addWidget(self.area_conteudo); self.btn_iniciar = QPushButton("Carregar Fila"); self.btn_iniciar.clicked.connect(self.carregar_revisao); self.layout.addWidget(self.btn_iniciar); self.questoes = []; self.idx_atual = 0

    def carregar_revisao(self):
        self.questoes = revisao_svc.questoes_para_revisar_hoje()
        if not self.questoes: self.limpar_area(); self.conteudo_layout.addWidget(QLabel("Não há questões para revisar hoje. Bom trabalho!")); return
        self.idx_atual = 0; self.btn_iniciar.hide(); self.mostrar_questao()

    def limpar_area(self):
        while self.conteudo_layout.count():
            widget = self.conteudo_layout.takeAt(0).widget()
            if widget: widget.deleteLater()

    def mostrar_questao(self):
        self.limpar_area(); q = self.questoes[self.idx_atual]; self.conteudo_layout.addWidget(QLabel(f"Revisão {self.idx_atual + 1} de {len(self.questoes)}")); enunciado = QTextEdit(q["enunciado"]); enunciado.setReadOnly(True); self.conteudo_layout.addWidget(enunciado); opcoes = [(a["letra"], f"{a['letra']}) {a['texto']}") for a in q.get("alternativas", [])] if q["tipo"] == "multipla_escolha" else [("Certo", "Certo"), ("Errado", "Errado")]; self.grupo = QButtonGroup(self)
        for valor, rotulo in opcoes:
            rb = QRadioButton(rotulo); rb.setProperty("valor_gabarito", valor); self.grupo.addButton(rb); self.conteudo_layout.addWidget(rb)
        btn = QPushButton("Responder"); btn.clicked.connect(lambda: self.avaliar_resposta(q)); self.conteudo_layout.addWidget(btn)

    def avaliar_resposta(self, q):
        selecionado = self.grupo.checkedButton()
        if not selecionado: QMessageBox.warning(self, "Aviso", "Selecione uma resposta!"); return
        acertou = selecionado.property("valor_gabarito") == q["gabarito"]; revisao_svc.processar_revisao(q["id"], acertou)
        QMessageBox.information(self, "Correto", "Resposta correta! Agendado para mais tarde.") if acertou else QMessageBox.critical(self, "Incorreto", f"Você errou. O gabarito era {q['gabarito']}.\nVoltando para a fila diária.")
        if self.idx_atual < len(self.questoes) - 1: self.idx_atual += 1; self.mostrar_questao()
        else: self.limpar_area(); self.conteudo_layout.addWidget(QLabel("Revisões do dia concluídas!")); self.btn_iniciar.show()
