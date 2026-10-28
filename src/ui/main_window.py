from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget, QVBoxLayout, QWidget, QSizePolicy, QMessageBox

from src.ui.pages.dashboard import DashboardPage
from src.ui.pages.execucao_prova import ExecucaoProvaPage
from src.ui.pages.estatisticas import EstatisticasPage
from src.ui.pages.gerador_prova import GeradorProvaPage
from src.ui.pages.importacao import ImportacaoPage
from src.ui.pages.provas_importadas import ProvasImportadasPage
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
        self.menu.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.menu.setTextElideMode(Qt.ElideRight)
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
            "Provas importadas": ProvasImportadasPage(),
            "Modo prova": ExecucaoProvaPage(),
            "Estatísticas": EstatisticasPage(),
            "Revisão": RevisaoPage(),
        }
        for nome, widget in paginas.items():
            widget.setMinimumSize(0, 0)
            self.menu.addItem(nome)
            self.pages.addWidget(widget)
        paginas["Importar"].abrir_gerador.connect(lambda: self.menu.setCurrentRow(3))
        paginas["Importar"].abrir_prova.connect(self._abrir_prova_importada)
        self.menu.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.pages.currentChanged.connect(self.menu.setCurrentRow)
        self.menu.setCurrentRow(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.pages)
        self.setCentralWidget(main_widget)

    def _abrir_prova_importada(self, proof_id):
        from src.models import questoes_repo as repo
        from src.ui.database_task import DatabaseTask
        if not hasattr(self, "_proof_open_task"):
            self._proof_open_task = DatabaseTask(self)
        self._proof_open_task.submit(lambda: next((item for item in repo.listar_provas_cadastradas() if item["id"] == proof_id), None), self._prova_importada_recebida, lambda error: QMessageBox.warning(self, "Prova indisponível", error))

    def _prova_importada_recebida(self, proof):
        if proof is None:
            QMessageBox.warning(self, "Prova indisponível", "O cadastro desta prova não está mais disponível.")
            return
        self.menu.setCurrentRow(4)
        self.pages.widget(4).ver_questoes(proof)

    def closeEvent(self, event):
        importacao = self.pages.widget(2)
        if importacao.ocupada:
            QMessageBox.information(self, "Leitura em andamento", "Aguarde o término da leitura antes de fechar o aplicativo.")
            event.ignore()
            return
        if (importacao.session.pendentes or importacao.session.caminho and not importacao.session.questoes) and not importacao._salvar_rascunho():
            if QMessageBox.question(self, "Rascunho não salvo",
                    "Não foi possível salvar o rascunho. Fechar e descartar a revisão atual?",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                event.ignore()
                return
        super().closeEvent(event)
