import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import src.models.questoes_repo as repo


logger = logging.getLogger(__name__)


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(28, 24, 28, 24)
        self.layout.setSpacing(16)
        cabecalho = QGridLayout()
        titulo = QLabel("Visão geral")
        titulo.setObjectName("dashboard-title")
        subtitulo = QLabel("Acompanhe seu banco de questões e seu desempenho.")
        subtitulo.setObjectName("dashboard-subtitle")
        self.btn_atualizar = QPushButton("Atualizar")
        self.btn_atualizar.clicked.connect(self.carregar_dados)
        cabecalho.addWidget(titulo, 0, 0)
        cabecalho.addWidget(subtitulo, 1, 0)
        cabecalho.addWidget(self.btn_atualizar, 0, 1, 2, 1, Qt.AlignRight | Qt.AlignVCenter)
        self.layout.addLayout(cabecalho)

        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(12)
        self.cards = {}
        for coluna, (chave, titulo_card) in enumerate([
            ("total_questoes", "Questões ativas"),
            ("provas_realizadas", "Provas realizadas"),
            ("taxa_acerto", "Taxa de acerto"),
            ("revisoes_hoje", "Revisões para hoje"),
        ]):
            card, valor = self._criar_card(titulo_card)
            self.cards[chave] = valor
            self.cards_layout.addWidget(card, 0, coluna)
        self.layout.addLayout(self.cards_layout)

        self.lbl_detalhes = QLabel()
        self.lbl_detalhes.setObjectName("dashboard-details")
        self.lbl_detalhes.setWordWrap(True)
        self.layout.addWidget(self.lbl_detalhes)

        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("dashboard-status")
        self.layout.addWidget(self.lbl_status)
        self.layout.addStretch()
        self.carregar_dados()

    def _criar_card(self, titulo):
        card = QFrame()
        card.setObjectName("dashboard-card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        label = QLabel(titulo)
        label.setObjectName("dashboard-card-title")
        valor = QLabel("—")
        valor.setObjectName("dashboard-card-value")
        card_layout.addWidget(label)
        card_layout.addWidget(valor)
        return card, valor

    def carregar_dados(self):
        try:
            resumo = repo.resumo_dashboard()
            self.cards["total_questoes"].setText(str(resumo["total_questoes"]))
            self.cards["provas_realizadas"].setText(str(resumo["provas_realizadas"]))
            self.cards["taxa_acerto"].setText(f"{resumo['taxa_acerto']:.1f}%")
            self.cards["revisoes_hoje"].setText(str(resumo["revisoes_hoje"]))
            self.lbl_detalhes.setText(
                f"Seu banco tem {resumo['total_provas']} provas criadas e "
                f"{resumo['total_respostas']} respostas registradas, "
                f"das quais {resumo['total_acertos']} estão corretas."
            )
            self.lbl_status.setText("Dados atualizados agora.")
            logger.info("Dashboard atualizado: %s", resumo)
        except Exception:
            logger.exception("Erro ao carregar dashboard")
            self.lbl_status.setText("Não foi possível carregar os indicadores. Consulte data/app.log.")
