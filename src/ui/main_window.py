from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

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
        self.resize(1000, 700)
        main_widget = QWidget()
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(236)
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
        footer = QLabel("ESTUDE • PRATIQUE • EVOLUA")
        footer.setObjectName("sidebar-footer")
        sidebar_layout.addWidget(footer)

        self.pages = QStackedWidget()
        self.pages.setObjectName("content-pages")
        paginas = {
            "Dashboard": DashboardPage(),
            "Questões": QuestoesPage(),
            "Importar": ImportacaoPage(),
            "Gerar Prova": GeradorProvaPage(),
            "Provas / Modo Prova": ExecucaoProvaPage(),
            "Estatísticas": EstatisticasPage(),
            "Revisão": RevisaoPage(),
        }
        for nome, widget in paginas.items():
            self.menu.addItem(nome)
            self.pages.addWidget(widget)
        self.menu.currentRowChanged.connect(self.pages.setCurrentIndex)
        layout.addWidget(sidebar)
        layout.addWidget(self.pages)
        self.setCentralWidget(main_widget)
