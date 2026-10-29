"""Prévia de recorte em memória; o PDF é renderizado fora do processo da UI."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea


class EvidenceCrop(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('source-facsimile')
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.label = QLabel('Selecione o PDF original para conferir o recorte.')
        self.label.setObjectName('review-region-image')
        self.label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(0)
        self.setWidget(self.label)
        self.original = QPixmap()
        self.zoom = 1.0

    def show_message(self, message):
        self.original = QPixmap()
        self.zoom = 1.0
        self.label.setMinimumWidth(0)
        self.label.setMinimumHeight(0)
        self.label.clear()
        self.label.setText(message)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def load_image(self, data):
        if not self.original.loadFromData(data, 'PNG'):
            self.show_message('Não foi possível exibir o recorte. Confira a aba Página completa.')
            return
        self._fit()
        self.verticalScrollBar().setValue(0)

    def change_zoom(self, multiplier):
        self.zoom = max(1.0, min(3.0, self.zoom * multiplier))
        self._fit()

    def _fit(self):
        if not self.original.isNull():
            width = round(min(self.original.width(), max(1, self.viewport().width() - 12)) * self.zoom)
            pixmap = self.original.scaledToWidth(width, Qt.SmoothTransformation)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded if self.zoom > 1 else Qt.ScrollBarAlwaysOff)
            self.label.setPixmap(pixmap)
            self.label.setMinimumWidth(pixmap.width() + 8 if self.zoom > 1 else 0)
            self.label.setMinimumHeight(pixmap.height() + 8)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()
