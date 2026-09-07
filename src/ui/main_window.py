from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget, QVBoxLayout, QWidget, QSizePolicy, QMessageBox

from src.ui.pages.dashboard import DashboardPage
from src.ui.pages.execucao_prova import ExecucaoProvaPage
from src.ui.pages.estatisticas import EstatisticasPage
from src.ui.pages.gerador_prova import GeradorProvaPage
from src.ui.pages.importacao import ImportacaoPage
from src.ui.pages.questoes import QuestoesPage
from src.ui.pages.revisao import RevisaoPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Banco de Questões")
        self.setMinimumSize(960, 640)
        self.resize(1240, 800)
        main_widget = QWidget()
        main_widget.setMinimumSize(0, 0)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 24, 18, 18)
        sidebar_layout.setSpacing(8)
        brand = QLabel("BANCO DE\nQUESTÕES")
        brand.setObjectName("brand-title")
        tagline = QLabel("Seu espaço de estudo")
        tagline.setObjectName("brand-subtitle")
        sidebar_layout.addWidget(brand)
        sidebar_layout.addWidget(tagline)
        sidebar_layout.addSpacing(22)
        self.menu = QListWidget()
        self.menu.setObjectName("main-menu")
        sidebar_layout.addWidget(self.menu)
        footer = QLabel("LOCAL · SEUS DADOS")
        footer.setObjectName("sidebar-footer")
        sidebar_layout.addWidget(footer)

        self.pages = QStackedWidget()
        self.pages.setObjectName("content-pages")
        self.pages.setMinimumSize(0, 0)
        self.pages.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        paginas = {
            "Dashboard": DashboardPage(),
            "Questões": QuestoesPage(),
            "Importar": ImportacaoPage(),
            "Gerar Prova": GeradorProvaPage(),
            "Modo prova": ExecucaoProvaPage(),
            "Estatísticas": EstatisticasPage(),
            "Revisão": RevisaoPage(),
        }
        for nome, widget in paginas.items():
            widget.setMinimumSize(0, 0)
            self.menu.addItem(nome)
            self.pages.addWidget(widget)
        self.menu.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.pages.currentChanged.connect(self.menu.setCurrentRow)
        self.menu.setCurrentRow(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.pages)
        self.setCentralWidget(main_widget)

    def closeEvent(self, event):
        importacao = self.pages.widget(2)
        if importacao.ocupada:
            QMessageBox.information(self, "Leitura em andamento", "Aguarde o término da leitura antes de fechar o aplicativo.")
            event.ignore()
            return
        if importacao.session.pendentes and QMessageBox.question(self, "Fechar sem salvar o lote?",
                "Há questões em revisão que ainda não foram salvas. Deseja fechar e descartar esses rascunhos?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            event.ignore()
            return
        super().closeEvent(event)
