"""Correção de um campo com releitura opcional do recorte atual."""
import json
import re
import logging
import time
from threading import Event

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)
from src.db.models import QuestaoVersao
from src.models.review_workflow import (
    FIELD_LABELS, apply_field_correction, read_source_region,
    remember_local_example, suggest_source_region,
)
from src.ui.database_task import DatabaseTask


class FieldCorrectionDialog(QDialog):
    def __init__(self, version_id, field, source_pane, parent=None):
        super().__init__(parent)
        self.version_id = version_id
        self.source_pane = source_pane
        self.region = None
        self.ai_result = None
        self.ai_cancel = Event()
        self._opened_at = time.monotonic()
        self._ai_started_at = None
        self._waiting_seconds = 0
        self._assisted = False
        self._metrics_recorded = False
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
        proposal_label = QLabel('Correção proposta · alternativas no formato A) texto, uma por linha')
        proposal_label.setWordWrap(True)
        layout.addWidget(proposal_label)
        self.proposal = QPlainTextEdit()
        layout.addWidget(self.proposal, 1)
        self.read_button = QPushButton('Reler recorte do PDF')
        self.read_button.setToolTip('Reler somente a página e os limites selecionados no PDF original.')
        self.read_button.setObjectName('secondary-button')
        self.read_button.setEnabled(source_pane.source_id is not None)
        self.read_button.clicked.connect(self._read_region)
        actions = QHBoxLayout()
        actions.addWidget(self.read_button, 1)
        self.ai_letter = QComboBox()
        self.ai_letter.setAccessibleName('Alternativa para conferir com IA local')
        self.ai_letter.addItems(list('ABCDE'))
        actions.addWidget(self.ai_letter)
        self.ai_button = QPushButton('Conferir com IA local')
        self.ai_button.setObjectName('secondary-button')
        self.ai_button.clicked.connect(self._read_ai)
        actions.addWidget(self.ai_button)
        layout.addLayout(actions)
        self.feedback = QLabel('Para ajustar o recorte, volte ao original e selecione a página e os limites.')
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.source_text = QPlainTextEdit()
        self.source_text.setReadOnly(True)
        self.source_text.setMaximumHeight(110)
        self.source_text.hide()
        layout.addWidget(self.source_text)
        self.example_button = QPushButton('Guardar exemplo conferido')
        self.example_button.setToolTip('Guardar a transcrição conferida para avaliar uma futura especialização local.')
        self.example_button.setObjectName('secondary-button')
        self.example_button.setEnabled(False)
        self.example_button.clicked.connect(self._remember_example)
        layout.addWidget(self.example_button)
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
        self.ai_letter.currentIndexChanged.connect(self._target_changed)
        self._load_field()

    def _load_field(self):
        # Uma proposta relida para outro campo não é reaproveitada silenciosamente.
        self.task.invalidate()
        self.ai_cancel.set()
        self._finish_wait()
        self.ai_result = None
        self.example_button.setEnabled(False)
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
        self.proposal.setEnabled(True)
        self.read_button.setEnabled(self.source_pane.source_id is not None)
        self.ai_button.setEnabled(self.source_pane.source_id is not None and self.field.currentData() in {'enunciado', 'texto_apoio', 'alternativas'})
        self.ai_letter.setVisible(self.field.currentData() == 'alternativas')

    def _target_changed(self):
        self.ai_cancel.set()
        self._finish_wait()
        self.task.invalidate()
        self.ai_result = None
        self.region = None
        self.example_button.setEnabled(False)
        self.save_button.setEnabled(True)
        self.proposal.setEnabled(True)
        self.ai_button.setEnabled(self.source_pane.source_id is not None and self.field.currentData() in {'enunciado', 'texto_apoio', 'alternativas'})
        self.read_button.setEnabled(self.source_pane.source_id is not None)

    def _read_ai(self):
        pane = self.source_pane
        self.ai_cancel.set()
        self.ai_cancel = Event()
        self._finish_wait()
        self._ai_started_at = time.monotonic()
        self._assisted = True
        cancel = self.ai_cancel
        source_id, page = pane.source_id, pane.page_spin.value()
        bounds = tuple(pane.bounds[n].value() for n in ('x0', 'y0', 'x1', 'y1'))
        field, version_id = self.field.currentData(), self.version_id
        letter = self.ai_letter.currentText() if field == 'alternativas' else None
        self.region = None
        self.ai_result = None
        self.example_button.setEnabled(False)
        self.read_button.setEnabled(False)
        self.ai_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.proposal.setEnabled(False)
        self.feedback.setText('Localizando o trecho e comparando PDF, OCR e IA local…')
        self.task.submit(lambda: suggest_source_region(version_id, field, source_id, page, bounds,
            letter=letter, cancel_event=cancel), self._ai_done, self._read_error)

    def _ai_done(self, result):
        self._finish_wait()
        self.ai_result = result
        self.region = result['region']
        self.proposal.setEnabled(True)
        self.read_button.setEnabled(True)
        self.ai_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.source_text.setPlainText('\n\n'.join(f'{name.upper()}: {text or "Leitura indisponível"}'
            for name, text in result['readings'].items()))
        self.source_text.show()
        self.feedback.setText(result['reason'] + ' A análise não aprova a questão.')
        if result['status'] == 'proposta':
            if result['field'] == 'alternativas':
                value = self.proposal.toPlainText()
                letter = result['letter']
                expression = r'(?ms)^' + letter + r'[).]\s*.*?(?=^[A-E][).]\s*|\Z)'
                value, count = re.subn(expression, lambda _: f"{letter}) {result['proposal']}\n", value, count=1)
                if count:
                    self.proposal.setPlainText(value.rstrip())
                else:
                    self.feedback.setText('A leitura está disponível. Ajuste manualmente a alternativa no formulário.')
            else:
                self.proposal.setPlainText(result['proposal'])
        self.example_button.setEnabled(bool(result['evidence'].get('image_bytes')))

    def _remember_example(self):
        if not self.ai_result:
            return
        evidence = dict(self.ai_result['evidence'], source_id=self.region['source_id'])
        dialog = QDialog(self)
        dialog.setWindowTitle('Exemplo conferido para treino local')
        dialog.resize(560, 460)
        layout = QVBoxLayout(dialog)
        from src.ui.components.evidence_crop import EvidenceCrop
        preview = EvidenceCrop()
        preview.setMinimumHeight(90)
        preview.load_image(evidence['image_bytes'])
        layout.addWidget(preview, 1)
        description = QLabel('Transcreva exatamente o recorte, incluindo o rótulo da alternativa.')
        description.setWordWrap(True)
        layout.addWidget(description)
        text = QPlainTextEdit()
        text.setPlainText(evidence.get('pdf') or evidence.get('ocr') or '')
        text.setMaximumHeight(100)
        layout.addWidget(text)
        reviewer = QLineEdit()
        reviewer.setPlaceholderText('Seu nome como responsável pela conferência')
        layout.addWidget(reviewer)
        illegible = QCheckBox('Recorte ilegível: registrar um exemplo de abstenção.')
        layout.addWidget(illegible)
        confirmed = QCheckBox('Conferi a transcrição inteira com a imagem original.')
        layout.addWidget(confirmed)
        save = QPushButton('Guardar exemplo local')
        save.setEnabled(False)
        def update():
            save.setEnabled(confirmed.isChecked() and bool(reviewer.text().strip())
                            and (illegible.isChecked() or bool(text.toPlainText().strip())))
        def change_legibility():
            text.setEnabled(not illegible.isChecked())
            confirmed.setChecked(False)
            confirmed.setText('Conferi a imagem e confirmei a falta de uma leitura confiável.' if illegible.isChecked()
                              else 'Conferi a transcrição inteira com a imagem original.')
            update()
        illegible.toggled.connect(change_legibility)
        confirmed.toggled.connect(update)
        reviewer.textChanged.connect(update)
        text.textChanged.connect(update)
        def store():
            try:
                remember_local_example(self.version_id, evidence, '' if illegible.isChecked() else text.toPlainText(),
                    reviewer.text(), confirmed.isChecked(), found=not illegible.isChecked())
            except (ValueError, OSError) as error:
                QMessageBox.warning(dialog, 'Exemplo não guardado', str(error))
                return
            dialog.accept()
            self.feedback.setText('Exemplo conferido guardado localmente. Nenhum treinamento foi iniciado.')
        save.clicked.connect(store)
        layout.addWidget(save)
        dialog.exec()

    def _read_region(self):
        self.ai_cancel.set()
        self.ai_result = None
        self.example_button.setEnabled(False)
        pane = self.source_pane
        self.region = None
        self.source_text.clear()
        self.source_text.hide()
        source_id, page = pane.source_id, pane.page_spin.value()
        bounds = tuple(pane.bounds[n].value() for n in ('x0', 'y0', 'x1', 'y1'))
        self.read_button.setEnabled(False)
        self.ai_button.setEnabled(False)
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
        self.ai_button.setEnabled(self.field.currentData() in {'enunciado', 'texto_apoio', 'alternativas'})

    def _read_error(self, error):
        self._finish_wait()
        self.feedback.setText(error)
        self.save_button.setEnabled(True)
        self.read_button.setEnabled(True)
        self.proposal.setEnabled(True)
        self.ai_button.setEnabled(self.source_pane.source_id is not None and self.field.currentData() in {'enunciado', 'texto_apoio', 'alternativas'})

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

    def _finish_wait(self):
        if self._ai_started_at is not None:
            self._waiting_seconds += time.monotonic() - self._ai_started_at
            self._ai_started_at = None

    def done(self, result):
        self.ai_cancel.set()
        self._finish_wait()
        self.task.invalidate()
        if not self._metrics_recorded:
            self._metrics_recorded = True
            try:
                from src.models.ia_metrics import record_session
                record_session(field=self.field.currentData(), assisted=self._assisted,
                    outcome='salvou' if result == QDialog.Accepted else 'cancelou',
                    elapsed_seconds=time.monotonic() - self._opened_at, waiting_seconds=self._waiting_seconds)
            except (OSError, ValueError):
                logging.getLogger(__name__).warning('Não foi possível registrar a duração local da conferência.')
        super().done(result)
