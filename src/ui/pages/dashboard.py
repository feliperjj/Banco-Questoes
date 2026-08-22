import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import src.models.questoes_repo as repo


logger = logging.getLogger(__name__)


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(28, 24, 28, 24)
        self.layout.setSpacing(16)

        cabecalho = QGridLayout()
        cabecalho.setColumnStretch(0, 1)
        titulo = QLabel("Bom estudo!")
        titulo.setObjectName("dashboard-title")
        subtitulo = QLabel("Seu painel de preparação, em um só lugar.")
        subtitulo.setObjectName("dashboard-subtitle")
        self.btn_atualizar = QPushButton("Atualizar dados")
        self.btn_atualizar.setObjectName("secondary-button")
        self.btn_atualizar.clicked.connect(self.carregar_dados)
        cabecalho.addWidget(titulo, 0, 0)
        cabecalho.addWidget(subtitulo, 1, 0)
        cabecalho.addWidget(self.btn_atualizar, 0, 1, 2, 1, Qt.AlignRight | Qt.AlignVCenter)
        self.layout.addLayout(cabecalho)

        self.layout.addWidget(self._criar_hero())

        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(12)
        self.cards = {}
        cards = [
            ("total_questoes", "Questões no banco", "prontas para você praticar"),
            ("provas_realizadas", "Provas concluídas", "seu histórico de simulados"),
            ("taxa_acerto", "Taxa de acerto", "média das suas respostas"),
            ("revisoes_hoje", "Revisões para hoje", "questões que pedem atenção"),
        ]
        for coluna, (chave, titulo_card, legenda) in enumerate(cards):
            card, valor = self._criar_card(titulo_card, legenda)
            self.cards[chave] = valor
            self.cards_layout.addWidget(card, 0, coluna)
        self.layout.addLayout(self.cards_layout)

        resumo_card = QFrame()
        resumo_card.setObjectName("dashboard-summary-card")
        resumo_layout = QVBoxLayout(resumo_card)
        resumo_layout.setContentsMargins(18, 14, 18, 14)
        resumo_layout.setSpacing(5)
        resumo_titulo = QLabel("Resumo do seu ritmo")
        resumo_titulo.setObjectName("dashboard-section-title")
        self.lbl_detalhes = QLabel()
        self.lbl_detalhes.setObjectName("dashboard-details")
        self.lbl_detalhes.setWordWrap(True)
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("dashboard-status")
        resumo_layout.addWidget(resumo_titulo)
        resumo_layout.addWidget(self.lbl_detalhes)
        resumo_layout.addWidget(self.lbl_status)
        self.layout.addWidget(resumo_card)
        self.layout.addStretch()
        self.carregar_dados()

    def showEvent(self, event):
        super().showEvent(event)
        self.carregar_dados()

    def _criar_hero(self):
        hero = QFrame()
        hero.setObjectName("dashboard-hero")
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(18)

        textos = QVBoxLayout()
        textos.setSpacing(5)
        titulo = QLabel("Mantenha a constância")
        titulo.setObjectName("dashboard-hero-title")
        self.lbl_hero = QLabel("Importe questões, monte uma prova e acompanhe sua evolução.")
        self.lbl_hero.setObjectName("dashboard-hero-text")
        self.lbl_hero.setWordWrap(True)
        textos.addWidget(titulo)
        textos.addWidget(self.lbl_hero)
        layout.addLayout(textos, 1)

        acoes = QHBoxLayout()
        acoes.setSpacing(8)
        revisar = QPushButton("Começar revisão")
        revisar.setObjectName("dashboard-primary-action")
        revisar.clicked.connect(lambda: self._abrir_pagina(6))
        prova = QPushButton("Gerar prova")
        prova.setObjectName("dashboard-secondary-action")
        prova.clicked.connect(lambda: self._abrir_pagina(3))
        acoes.addWidget(revisar)
        acoes.addWidget(prova)
        layout.addLayout(acoes)
        return hero

    def _criar_card(self, titulo, legenda):
        card = QFrame()
        card.setObjectName("dashboard-card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 13)
        card_layout.setSpacing(2)
        label = QLabel(titulo)
        label.setObjectName("dashboard-card-title")
        valor = QLabel("—")
        valor.setObjectName("dashboard-card-value")
        caption = QLabel(legenda)
        caption.setObjectName("dashboard-card-caption")
        card_layout.addWidget(label)
        card_layout.addWidget(valor)
        card_layout.addWidget(caption)
        return card, valor

    def _abrir_pagina(self, indice):
        janela = self.window()
        menu = getattr(janela, "menu", None)
        if menu is not None:
            menu.setCurrentRow(indice)

    def carregar_dados(self):
        try:
            resumo = repo.resumo_dashboard()
            total_questoes = resumo["total_questoes"]
            self.cards["total_questoes"].setText(str(total_questoes))
            self.cards["provas_realizadas"].setText(str(resumo["provas_realizadas"]))
            self.cards["taxa_acerto"].setText(f"{resumo['taxa_acerto']:.1f}%")
            self.cards["revisoes_hoje"].setText(str(resumo["revisoes_hoje"]))
            self.lbl_hero.setText(
                f"Você tem {total_questoes} questão(ões) disponíveis. Escolha um próximo passo e continue avançando."
            )
            self.lbl_detalhes.setText(
                f"{resumo['total_provas']} prova(s) criada(s) · {resumo['total_respostas']} resposta(s) registrada(s) · "
                f"{resumo['total_acertos']} acerto(s) até agora."
            )
            self.lbl_status.setText("Dados atualizados agora.")
            logger.info("Dashboard atualizado: %s", resumo)
        except Exception:
            logger.exception("Erro ao carregar dashboard")
            self.lbl_status.setText("Não foi possível carregar os indicadores. Consulte data/app.log.")
