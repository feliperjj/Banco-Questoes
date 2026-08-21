from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

import src.models.questoes_repo as repo


class EstatisticasPage(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(34, 28, 34, 28)
        self.layout.setSpacing(16)
        header = QHBoxLayout()
        titulo = QVBoxLayout()
        self.lbl_titulo = QLabel("Seu desempenho")
        self.lbl_titulo.setObjectName("page-title")
        titulo.addWidget(self.lbl_titulo)
        subtitulo = QLabel("Acompanhe sua evolução e descubra onde concentrar seus estudos.")
        subtitulo.setObjectName("page-subtitle")
        titulo.addWidget(subtitulo)
        header.addLayout(titulo)
        header.addStretch()
        self.btn_atualizar = QPushButton("Atualizar dados")
        self.btn_atualizar.setObjectName("secondary-button")
        self.btn_atualizar.clicked.connect(self.carregar_dados)
        header.addWidget(self.btn_atualizar, alignment=Qt.AlignBottom)
        self.layout.addLayout(header)

        self.metricas = QGridLayout()
        self.metricas.setHorizontalSpacing(12)
        self.metricas.setVerticalSpacing(12)
        self.metricas_widgets = []
        for coluna, (titulo_metrica, chave) in enumerate((("Questões respondidas", "total_respostas"), ("Taxa de acerto", "taxa_acerto"), ("Provas realizadas", "provas_realizadas"), ("Revisões pendentes", "revisoes_hoje"))):
            card = QFrame()
            card.setObjectName("stat-card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            label = QLabel(titulo_metrica)
            label.setObjectName("stat-card-title")
            valor = QLabel("—")
            valor.setObjectName("stat-card-value")
            card_layout.addWidget(label)
            card_layout.addWidget(valor)
            self.metricas.addWidget(card, 0, coluna)
            self.metricas_widgets.append((chave, valor))
        self.layout.addLayout(self.metricas)

        graficos = QHBoxLayout()
        graficos.setSpacing(14)
        self.fig_barras = Figure(figsize=(5, 3.2), facecolor="#ffffff")
        self.canvas_barras = FigureCanvasQTAgg(self.fig_barras)
        self.canvas_barras.setObjectName("chart-card")
        graficos.addWidget(self.canvas_barras)
        self.fig_linhas = Figure(figsize=(5, 3.2), facecolor="#ffffff")
        self.canvas_linhas = FigureCanvasQTAgg(self.fig_linhas)
        self.canvas_linhas.setObjectName("chart-card")
        graficos.addWidget(self.canvas_linhas)
        self.layout.addLayout(graficos)

        titulo_erros = QLabel("Questões que merecem atenção")
        titulo_erros.setObjectName("section-title")
        self.layout.addWidget(titulo_erros)
        self.tabela_erros = QTableWidget()
        self.tabela_erros.setColumnCount(3)
        self.tabela_erros.setHorizontalHeaderLabels(["ID", "Questão", "Erros"])
        self.tabela_erros.verticalHeader().setVisible(False)
        self.tabela_erros.setShowGrid(False)
        self.tabela_erros.setWordWrap(False)
        self.tabela_erros.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tabela_erros.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabela_erros.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tabela_erros.setAlternatingRowColors(True)
        self.tabela_erros.setSelectionBehavior(QTableWidget.SelectRows)
        self.layout.addWidget(self.tabela_erros, 1)
        self.carregar_dados()

    def carregar_dados(self):
        resumo = repo.resumo_dashboard()
        for chave, valor in self.metricas_widgets:
            numero = resumo.get(chave, 0)
            valor.setText(f"{numero:.1f}%" if chave == "taxa_acerto" else str(numero))

        dados = repo.desempenho_por_disciplina()
        self.fig_barras.clear()
        ax1 = self.fig_barras.add_subplot(111)
        ax1.set_facecolor("#ffffff")
        if dados:
            nomes = [d["disciplina"] or "Sem disciplina" for d in dados]
            valores = [d["percentual"] for d in dados]
            ax1.barh(nomes, valores, color="#4f7cff", height=0.58)
            ax1.set_xlim(0, 100)
            ax1.invert_yaxis()
            ax1.set_xlabel("Acerto (%)", color="#71809a")
        else:
            ax1.text(0.5, 0.5, "Ainda não há dados suficientes", ha="center", va="center", color="#71809a")
        self._estilizar_eixo(ax1, "Acerto por disciplina")
        self.fig_barras.tight_layout(pad=2)
        self.canvas_barras.draw()

        notas = repo.evolucao_notas()
        self.fig_linhas.clear()
        ax2 = self.fig_linhas.add_subplot(111)
        ax2.set_facecolor("#ffffff")
        if notas:
            eixo_x = list(range(1, len(notas) + 1))
            ax2.plot(eixo_x, [n["nota"] for n in notas], marker="o", linewidth=2.5, color="#36a269", markerfacecolor="#ffffff", markeredgewidth=2)
            ax2.set_ylim(0, 105)
            ax2.set_xlabel("Tentativa", color="#71809a")
            ax2.set_ylabel("Nota", color="#71809a")
        else:
            ax2.text(0.5, 0.5, "Faça uma prova para ver sua evolução", ha="center", va="center", color="#71809a")
        self._estilizar_eixo(ax2, "Evolução das notas")
        self.fig_linhas.tight_layout(pad=2)
        self.canvas_linhas.draw()

        erros = repo.questoes_mais_erradas()
        self.tabela_erros.setRowCount(len(erros))
        for row, q in enumerate(erros):
            self.tabela_erros.setItem(row, 0, QTableWidgetItem(str(q["id"])))
            texto = q["enunciado"]
            self.tabela_erros.setItem(row, 1, QTableWidgetItem(texto[:110] + "..." if len(texto) > 110 else texto))
            self.tabela_erros.setItem(row, 2, QTableWidgetItem(str(q["erros"])))
            self.tabela_erros.setRowHeight(row, 42)

    @staticmethod
    def _estilizar_eixo(ax, titulo):
        ax.set_title(titulo, loc="left", color="#24324a", fontsize=12, fontweight="bold", pad=12)
        ax.tick_params(colors="#71809a", labelsize=8)
        for borda in ax.spines.values():
            borda.set_visible(False)
        ax.grid(axis="x", color="#edf1f7", linewidth=0.8)
        ax.set_axisbelow(True)
