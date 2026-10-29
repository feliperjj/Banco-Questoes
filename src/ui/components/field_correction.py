"""Correção de um campo com releitura opcional do recorte atual."""
import json
import re

from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)
from src.db.models import QuestaoVersao
from src.models.review_workflow import FIELD_LABELS, apply_field_correction, read_source_region
from src.ui.database_task import DatabaseTask


class FieldCorrectionDialog(QDialog):
    def __init__(self, version_id, field, source_pane, parent=None):
        super().__init__(parent)
        self.version_id = version_id
        self.source_pane = source_pane
        self.region = None
        self.content = json.loads(QuestaoVersao.get_by_id(version_id).conteudo_json)
        self.task = DatabaseTask(self)
        self.setWindowTitle('Corrigir somente um campo')
        self.resize(680, 560)
        layout = QVBoxLayout(self)
        hint = QLabel('Confira a proposta antes de salvar. A correção cria uma versão pendente de conferência.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.field = QComboBox()
        for key, label in FIELD_LABELS.items():
            if key != 'alternativas' or self.content['tipo'] == 'multipla_escolha':
                self.field.addItem(label, key)
        self.field.setCurrentIndex(max(0, self.field.findData(field)))
        layout.addWidget(self.field)
        layout.addWidget(QLabel('Valor atual'))
        self.before = QPlainTextEdit()
        self.before.setReadOnly(True)
        self.before.setMaximumHeight(100)
        layout.addWidget(self.before)
        layout.addWidget(QLabel('Correção proposta · alternativas no formato A) texto, uma por linha'))
        self.proposal = QPlainTextEdit()
        layout.addWidget(self.proposal, 1)
        self.read_button = QPushButton('Reler somente o recorte selecionado no PDF')
        self.read_button.setObjectName('secondary-button')
        self.read_button.setEnabled(source_pane.source_id is not None)
        self.read_button.clicked.connect(self._read_region)
        layout.addWidget(self.read_button)
        self.feedback = QLabel('Para ajustar o recorte, volte ao original e selecione a página e os limites.')
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.source_text = QPlainTextEdit()
        self.source_text.setReadOnly(True)
        self.source_text.setMaximumHeight(110)
        self.source_text.hide()
        layout.addWidget(self.source_text)
        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton('Cancelar')
        cancel.setObjectName('secondary-button')
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton('Salvar correção')
        self.save_button.clicked.connect(self._save)
        footer.addWidget(cancel)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)
        self.field.currentIndexChanged.connect(self._load_field)
        self._load_field()

    def _load_field(self):
        # Uma proposta relida para outro campo não é reaproveitada silenciosamente.
        self.task.invalidate()
        parent = self.parentWidget()
        if hasattr(parent, 'question_pdf'):
            self.source_pane = parent.answer_pdf if self.field.currentData() == 'gabarito' else parent.question_pdf
        self.region = None
        self.source_text.clear()
        self.source_text.hide()
        value = self.content.get(self.field.currentData())
        if isinstance(value, list):
            value = '\n'.join(f"{a['letra']}) {a['texto']}" for a in value)
        self.before.setPlainText(str(value or ''))
        self.proposal.setPlainText(str(value or ''))
        self.feedback.setText('Para ajustar o recorte, volte ao original e selecione a página e os limites.')
        self.save_button.setEnabled(True)
        self.read_button.setEnabled(self.source_pane.source_id is not None)

    def _read_region(self):
        pane = self.source_pane
        self.region = None
        self.source_text.clear()
        self.source_text.hide()
        source_id, page = pane.source_id, pane.page_spin.value()
        bounds = tuple(pane.bounds[n].value() for n in ('x0', 'y0', 'x1', 'y1'))
        self.read_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.feedback.setText('Relendo apenas o recorte selecionado…')
        self.task.submit(lambda: read_source_region(source_id, page, bounds), self._read_done, self._read_error)

    def _read_done(self, region):
        self.region = region
        self.source_text.setPlainText(region['text'])
        self.source_text.show()
        if self.field.currentData() in {'enunciado', 'texto_apoio'}:
            self.proposal.setPlainText(region['text'])
        self.feedback.setText('Recorte relido. Revise a proposta; número, alternativas e gabarito exigem preenchimento explícito.')
        self.save_button.setEnabled(True)
        self.read_button.setEnabled(True)

    def _read_error(self, error):
        self.feedback.setText(error)
        self.save_button.setEnabled(True)
        self.read_button.setEnabled(True)

    def _save(self):
        value = self.proposal.toPlainText().strip()
        field = self.field.currentData()
        try:
            if field == 'alternativas':
                matches = list(re.finditer(r'^([A-E])[).]\s*', value, re.MULTILINE))
                if not matches or value[:matches[0].start()].strip():
                    raise ValueError('Use A) texto, B) texto e assim por diante, uma alternativa por linha.')
                value = [{'letra': m.group(1), 'texto': value[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(value)].strip()}
                         for i, m in enumerate(matches)]
            self.result_version_id = apply_field_correction(self.version_id, field, value, region=self.region)
        except (ValueError, KeyError) as error:
            QMessageBox.warning(self, 'Correção pendente', str(error))
            return
        self.accept()

    def done(self, result):
        self.task.invalidate()
        super().done(result)
