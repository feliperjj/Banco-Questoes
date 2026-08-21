from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
import src.models.questoes_repo as repo
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class EstatisticasPage(QWidget):
    def __init__(self):
        super().__init__(); layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); graficos = QHBoxLayout(); self.fig_barras = Figure(figsize=(5, 4), facecolor="#f4f7fb"); self.canvas_barras = FigureCanvasQTAgg(self.fig_barras); graficos.addWidget(self.canvas_barras); self.fig_linhas = Figure(figsize=(5, 4), facecolor="#f4f7fb"); self.canvas_linhas = FigureCanvasQTAgg(self.fig_linhas); graficos.addWidget(self.canvas_linhas); layout.addLayout(graficos); layout.addWidget(QLabel("<b>Top Questões Mais Erradas:</b>")); self.tabela_erros = QTableWidget(); self.tabela_erros.setColumnCount(3); self.tabela_erros.setHorizontalHeaderLabels(["ID", "Enunciado", "Nº de Erros"]); self.tabela_erros.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); layout.addWidget(self.tabela_erros); self.carregar_dados()

    def carregar_dados(self):
        ax1 = self.fig_barras.add_subplot(111); ax1.clear(); ax1.set_facecolor("#ffffff"); dados = repo.desempenho_por_disciplina()
        if dados: ax1.bar([d["disciplina"] for d in dados], [d["percentual"] for d in dados], color="skyblue"); ax1.set_ylim(0, 100)
        else: ax1.text(0.5, 0.5, "Sem dados suficientes", ha="center", va="center")
        ax1.set_title("% de Acerto por Disciplina"); ax1.set_ylabel("Percentual (%)"); ax1.tick_params(axis="x", rotation=45); self.fig_barras.tight_layout(); self.canvas_barras.draw()
        ax2 = self.fig_linhas.add_subplot(111); ax2.clear(); ax2.set_facecolor("#ffffff"); notas = repo.evolucao_notas()
        if notas: ax2.plot([n["iniciada_em"][5:16] for n in notas], [n["nota"] for n in notas], marker="o", linestyle="-", color="green"); ax2.set_ylim(0, 105)
        else: ax2.text(0.5, 0.5, "Sem dados suficientes", ha="center", va="center")
        ax2.set_title("Evolução das Notas"); ax2.set_ylabel("Nota final"); ax2.tick_params(axis="x", rotation=45); self.fig_linhas.tight_layout(); self.canvas_linhas.draw()
        erros = repo.questoes_mais_erradas(); self.tabela_erros.setRowCount(len(erros))
        for row, q in enumerate(erros):
            self.tabela_erros.setItem(row, 0, QTableWidgetItem(str(q["id"]))); texto = q["enunciado"]; self.tabela_erros.setItem(row, 1, QTableWidgetItem(texto[:80] + "..." if len(texto) > 80 else texto)); self.tabela_erros.setItem(row, 2, QTableWidgetItem(str(q["erros"])))
