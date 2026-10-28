"""Escolhas documentais legíveis, sem transformar seleção em certificação."""
from PySide6.QtWidgets import QComboBox, QHeaderView, QTableWidget, QTableWidgetItem
from src.importador.perfis.registro import listar_perfis


class ScopeChoice(QComboBox):
    def __init__(self):
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.textChanged = self.lineEdit().textChanged

    def text(self):
        return self.currentText()

    def setText(self, value):
        self.setEditText(value)

    def setPlaceholderText(self, value):
        self.lineEdit().setPlaceholderText(value)

    def set_options(self, values):
        selected = self.text()
        self.blockSignals(True)
        self.clear()
        self.addItem("")
        self.addItems(sorted(set(values)))
        self.setText(selected)
        self.blockSignals(False)


class PageProfileChoices(QTableWidget):
    def __init__(self, pages, role, selections, parent=None):
        super().__init__(len(pages), 3, parent)
        self.setHorizontalHeaderLabels(["Página", "Leitura reconhecida", "Leitura a usar"])
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._choices = {}
        profiles = listar_perfis(role)
        names = {profile.id: profile.descricao for profile in profiles}
        for row, page in enumerate(pages):
            number, detected = page["pagina"], page["perfil"]
            self.setItem(row, 0, QTableWidgetItem(str(number)))
            self.setItem(row, 1, QTableWidgetItem(names.get(detected, "Sem texto — conferir OCR")))
            choice = QComboBox()
            choice.setMinimumWidth(200)
            choice.addItem("Usar reconhecimento", "")
            for profile in profiles:
                choice.addItem(profile.descricao, profile.id)
            choice.setCurrentIndex(max(0, choice.findData(selections.get(number, ""))))
            choice.setEnabled(detected != "sem_texto")
            self.setCellWidget(row, 2, choice)
            self._choices[number] = choice

    def selections(self):
        return {number: choice.currentData() for number, choice in self._choices.items()
                if choice.isEnabled() and choice.currentData()}
