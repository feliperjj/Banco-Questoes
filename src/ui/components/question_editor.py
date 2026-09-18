from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHeaderView, QLabel, QLineEdit, QScrollArea,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from src.models.importacao_session import validar_questao
from src.importador.validacao import inicio_suspeito, problemas_estrutura


class ValueCombo(QComboBox):
    """Rótulos legíveis com valores de domínio estáveis."""
    def setCurrentText(self, texto):
        indice = self.findData(texto)
        if indice >= 0:
            self.setCurrentIndex(indice)
        else:
            super().setCurrentText(texto)


class QuestionEditor(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("question-editor")
        self._loading = False
        self._base = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.aviso_inicio = QLabel("Início em minúscula: confira no arquivo original se o enunciado está completo e se as colunas foram separadas corretamente.")
        self.aviso_inicio.setObjectName("import-feedback")
        self.aviso_inicio.setProperty("error", True)
        self.aviso_inicio.setWordWrap(True)
        outer.addWidget(self.aviso_inicio)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("editor-tabs")
        outer.addWidget(self.tabs)
        self.content_form = self._form("Questão")
        self.enunciado_input = QTextEdit()
        self.enunciado_input.setAcceptRichText(False)
        self.enunciado_input.setPlaceholderText("Escreva ou revise o enunciado completo…")
        self.enunciado_input.setMinimumHeight(115)
        self.enunciado_input.setMaximumHeight(170)
        self.content_form.addRow("Enunciado", self.enunciado_input)
        self.tipo_combo = ValueCombo()
        self.tipo_combo.addItem("Múltipla escolha", "multipla_escolha")
        self.tipo_combo.addItem("Certo ou errado", "certo_errado")
        self.content_form.addRow("Tipo de questão", self.tipo_combo)
        self.gabarito_input = ValueCombo()
        self.content_form.addRow("Gabarito", self.gabarito_input)
        self.alternativas_input = QTableWidget(5, 1)
        self.alternativas_input.setObjectName("alternatives-editor")
        self.alternativas_input.setHorizontalHeaderLabels(["Texto da alternativa · clique para editar"])
        self.alternativas_input.setVerticalHeaderLabels(list("ABCDE"))
        self.alternativas_input.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.alternativas_input.verticalHeader().setDefaultSectionSize(44)
        self.alternativas_input.setMinimumHeight(220)
        self.alternativas_input.setWordWrap(True)
        self.content_form.addRow("Alternativas", self.alternativas_input)
        dados_form = self._form("Classificação")
        self.disciplina_input = QComboBox()
        self.disciplina_input.setEditable(True)
        self.disciplina_input.addItems(["", "Língua Portuguesa", "Matemática", "Informática", "Conhecimentos Específicos"])
        self.topico_input = QLineEdit()
        self.banca_input = QComboBox()
        self.banca_input.setEditable(True)
        self.ano_input = QLineEdit()
        self.ano_input.setPlaceholderText("Ex.: 2026")
        self.dificuldade_combo = ValueCombo()
        for rotulo, valor in [("Não informada", None), ("Fácil", "facil"), ("Média", "media"), ("Difícil", "dificil")]:
            self.dificuldade_combo.addItem(rotulo, valor)
        for rotulo, widget in [("Disciplina", self.disciplina_input), ("Assunto / categoria", self.topico_input),
                               ("Banca", self.banca_input), ("Ano", self.ano_input), ("Dificuldade", self.dificuldade_combo)]:
            dados_form.addRow(rotulo, widget)
        self.tipo_combo.currentIndexChanged.connect(self._atualizar_tipo)
        for widget in (self.disciplina_input, self.banca_input, self.dificuldade_combo, self.gabarito_input):
            widget.currentTextChanged.connect(self._changed)
        for widget in (self.enunciado_input, self.topico_input, self.ano_input):
            widget.textChanged.connect(self._changed)
        self.alternativas_input.itemChanged.connect(self._changed)
        self.load({})

    def _form(self, titulo):
        scroll = QScrollArea()
        scroll.setObjectName("editor-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setMinimumWidth(0)
        form = QFormLayout(content)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, titulo)
        return form

    def _changed(self, *args):
        if not self._loading:
            self._atualizar_aviso()
            self.changed.emit()

    def _atualizar_aviso(self):
        dados = self.data()
        problemas = problemas_estrutura(dados) if dados.get('enunciado') else []
        if inicio_suspeito(dados.get('enunciado')):
            problemas.insert(0, 'Início em minúscula: confira se o enunciado está completo')
        self.aviso_inicio.setText('Revisar no original: ' + '; '.join(problemas) + '.')
        self.aviso_inicio.setVisible(bool(problemas))

    def _atualizar_tipo(self):
        loading = self._loading
        self._loading = True
        anterior = self.gabarito_input.currentData()
        multipla = self.tipo_combo.currentData() == "multipla_escolha"
        self.alternativas_input.setEnabled(multipla)
        self.gabarito_input.clear()
        self.gabarito_input.addItem("Sem gabarito", None)
        for valor in (list("ABCDE") if multipla else ["Certo", "Errado"]):
            self.gabarito_input.addItem(valor, valor)
        self.gabarito_input.addItem("Anulada", "Anulada")
        self.gabarito_input.setCurrentIndex(max(0, self.gabarito_input.findData(anterior)))
        self._loading = loading
        self._changed()

    def load(self, dados):
        self._loading = True
        self._base = deepcopy(dados)
        self.enunciado_input.setPlainText(dados.get("enunciado") or "")
        self.tipo_combo.setCurrentText(dados.get("tipo") or "multipla_escolha")
        self._atualizar_tipo()
        resposta = dados.get("gabarito") or None
        indice = self.gabarito_input.findData(resposta)
        if indice < 0:
            self.gabarito_input.addItem(f"Revisar: {resposta}", resposta)
            indice = self.gabarito_input.count() - 1
        self.gabarito_input.setCurrentIndex(indice)
        for widget, chave in [(self.disciplina_input, "disciplina"), (self.banca_input, "banca")]:
            widget.setCurrentText(dados.get(chave) or "")
        self.topico_input.setText(dados.get("topico") or "")
        self.ano_input.setText(str(dados.get("ano") or ""))
        self.dificuldade_combo.setCurrentIndex(max(0, self.dificuldade_combo.findData(dados.get("dificuldade"))))
        alternativas = {a["letra"].upper(): a["texto"] for a in dados.get("alternativas") or []}
        for row, letra in enumerate("ABCDE"):
            self.alternativas_input.setItem(row, 0, QTableWidgetItem(alternativas.get(letra, "")))
        self._loading = False

        self._atualizar_aviso()

    def data(self, validate=False):
        dados = deepcopy(self._base)
        ano = self.ano_input.text().strip()
        dados.update(enunciado=self.enunciado_input.toPlainText().strip(), tipo=self.tipo_combo.currentData(),
                     gabarito=self.gabarito_input.currentData(), disciplina=self.disciplina_input.currentText().strip(),
                     topico=self.topico_input.text().strip(), banca=self.banca_input.currentText().strip(),
                     ano=int(ano) if ano.isdigit() else (ano or None), dificuldade=self.dificuldade_combo.currentData())
        dados["alternativas"] = []
        if dados["tipo"] == "multipla_escolha":
            for row, letra in enumerate("ABCDE"):
                item = self.alternativas_input.item(row, 0)
                if item and item.text().strip():
                    dados["alternativas"].append({"letra": letra, "texto": item.text().strip()})
        if validate:
            validar_questao(dados)
        return dados
