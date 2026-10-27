"""Exibição rolável de recortes documentais preservando a notação original."""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from src.config import ROOT_DIR


class SourceFacsimile(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.surface = QWidget()
        self.rows = QVBoxLayout(self.surface)
        self.rows.setContentsMargins(4, 4, 4, 4)
        self.rows.setSpacing(12)
        self.setWidget(self.surface)
        self.images = []

    def set_assets(self, assets):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.images = []
        for asset in assets:
            path = Path(asset["path"])
            if not path.is_absolute():
                path = ROOT_DIR / path
            pixmap = QPixmap(str(path))
            label = QLabel()
            label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            if pixmap.isNull():
                label.setText("Recorte original indisponível. Retorne à conferência da fonte.")
            else:
                self.images.append((label, pixmap))
            self.rows.addWidget(label)
        self.rows.addStretch(1)
        QTimer.singleShot(0, self._fit)
        self.verticalScrollBar().setValue(0)

    def _fit(self):
        from shiboken6 import isValid
        if not isValid(self):
            return
        width = max(100, self.viewport().width() - 16)
        for label, pixmap in self.images:
            scaled = pixmap.scaledToWidth(width, Qt.SmoothTransformation)
            label.setPixmap(scaled)
            label.setFixedHeight(scaled.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit)
