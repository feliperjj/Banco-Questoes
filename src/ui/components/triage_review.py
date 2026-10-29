"""Diálogo de revisão da triagem assistida por IA.

Este módulo é deliberadamente um adaptador de UI: a análise é fornecida por
``src.models.ia_triage`` e nenhuma proposta é persistida sem um gesto humano
que passe pelo fluxo normal de correção.
"""
from difflib import SequenceMatcher
from html import escape
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget, QSpinBox,
)

from src.ui.database_task import DatabaseTask


class _Progress(QObject):
    changed = Signal(object)


def _text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(f"{item.get('letra', '')}) {item.get('texto', '')}" if isinstance(item, dict) else str(item)
                         for item in value)
    return str(value)


def _diff_html(before, after):
    """Gera HTML escapado, destacando somente trechos alterados."""
    before, after = _text(before), _text(after)
    matcher = SequenceMatcher(None, before, after, autojunk=False)
    left, right = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old, new = escape(before[i1:i2]), escape(after[j1:j2])
        if tag == 'equal':
            left.append(old); right.append(new)
        elif tag == 'delete':
            left.append(f'<span style="background-color:#ffd6d6;text-decoration:line-through">{old}</span>')
        elif tag == 'insert':
            right.append(f'<span style="background-color:#fff0a8">{new}</span>')
        else:
            left.append(f'<span style="background-color:#ffd6d6;text-decoration:line-through">{old}</span>')
            right.append(f'<span style="background-color:#fff0a8">{new}</span>')
    return ''.join(left), ''.join(right)


class _SourcePane(QWidget):
    """Pequeno adaptador compatível com FieldCorrectionDialog."""
    def __init__(self, source_id, page, bounds, parent=None):
        super().__init__(parent)
        self.source_id = source_id
        self.page_spin = QSpinBox(self)
        self.page_spin.setRange(1, 100000)
        self.page_spin.setValue(max(1, int(page or 1)))
        self.bounds = {}
        for name, value in zip(('x0', 'y0', 'x1', 'y1'), bounds or (0, 0, 0, 0)):
            spin = QDoubleSpinBox(self)
            spin.setRange(0, 100000)
            spin.setValue(float(value or 0))
            self.bounds[name] = spin
        self.hide()


class TriageReviewDialog(QDialog):
    """Analisa uma lista e permite conferir cada exceção individualmente."""
    def __init__(self, question_ids, parent=None):
        super().__init__(parent)
        self.question_ids = list(dict.fromkeys(question_ids or []))
        self.rows = []
        self._cancel = Event()
        self._closed = False
        self._run_token = 0
        self._cancel_requested = False
        self._progress = _Progress(self)
        self._progress.changed.connect(self._on_progress)
        self.task = DatabaseTask(self)
        self.setWindowTitle('Triagem assistida · revisão humana')
        self.resize(900, 620)
        layout = QVBoxLayout(self)
        self.status_label = QLabel('Análise ainda não iniciada.')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        actions = QHBoxLayout()
        self.start_button = QPushButton('Analisar lista')
        self.start_button.clicked.connect(self.start_analysis)
        self.cancel_button = QPushButton('Cancelar')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        self.filter = QComboBox()
        self.filter.addItems(['Exceções e propostas', 'Todas', 'Propostas', 'Divergências', 'Bloqueios', 'Sem diferenças'])
        self.filter.currentIndexChanged.connect(self._refresh_table)
        actions.addWidget(self.start_button); actions.addWidget(self.cancel_button)
        actions.addStretch(); actions.addWidget(QLabel('Filtro:')); actions.addWidget(self.filter)
        layout.addLayout(actions)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Questão', 'Campo', 'Estado', 'Atual', 'Proposta', 'Motivo'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.currentCellChanged.connect(lambda *_: self._show_selected())
        layout.addWidget(self.table, 2)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.setPlaceholderText('Selecione uma linha para comparar a leitura.')
        layout.addWidget(self.preview, 1)
        from src.ui.components.evidence_crop import EvidenceCrop
        self.crop = EvidenceCrop(self)
        self.crop.setMaximumHeight(120)
        self.crop.hide()
        layout.addWidget(self.crop)
        footer = QHBoxLayout()
        self.review_button = QPushButton('Conferir campo')
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._review_selected)
        close = QPushButton('Fechar'); close.clicked.connect(self.close)
        footer.addWidget(self.review_button); footer.addStretch(); footer.addWidget(close)
        layout.addLayout(footer)

    def start_analysis(self):
        if self.task.running:
            return
        self._cancel = Event()
        self._cancel_requested = False
        self._run_token += 1
        run_token = self._run_token
        self.rows = []
        self._refresh_table()
        self.start_button.setEnabled(False); self.cancel_button.setEnabled(True)
        self.status_label.setText('Analisando lista…')
        try:
            from src.models.ia_triage import triage_questions
        except ImportError as error:
            self._analysis_error(str(error)); return
        cancel = self._cancel
        def progress(*values):
            if run_token != self._run_token or self._closed or self._cancel_requested:
                return
            self._progress.changed.emit(values if len(values) != 1 else values[0])
        self.task.submit(lambda: triage_questions(self.question_ids, cancel_event=cancel, progress=progress),
                         self._analysis_done, self._analysis_error)

    def cancel_analysis(self):
        self._cancel.set()
        self._cancel_requested = True
        self.cancel_button.setEnabled(False)
        self.status_label.setText('Cancelamento solicitado; concluindo a leitura atual…')

    @Slot(object)
    def _on_progress(self, value):
        if self._closed or self._cancel_requested:
            return
        if isinstance(value, tuple) and len(value) == 2:
            value = {'done': value[0], 'total': value[1]}
        if isinstance(value, dict):
            done, total = value.get('done', value.get('current', '')), value.get('total', '')
            self.status_label.setText(f'Analisando lista… {done}/{total}' if total else f'Analisando lista… {done}')
        else:
            self.status_label.setText(f'Analisando lista… {value}')

    def _analysis_done(self, result):
        if self._closed:
            return
        result = result or {}
        self.rows = list(result.get('rows') or [])
        cancelled = bool(result.get('cancelled')) or self._cancel_requested
        counts = result.get('counts') or {}
        labels = {'liberada': 'Já liberadas', 'bloqueada': 'Bloqueios', 'conferir': 'Sem diferenças',
                  'proposta': 'Propostas', 'revisao': 'Revisão', 'erro': 'Erros'}
        summary = ' · '.join(f'{labels.get(key, key)}: {value}' for key, value in counts.items())
        self.status_label.setText(('Análise cancelada.' if cancelled else 'Análise concluída.')
                                  + (f' · {summary}' if summary else '')
                                  + ' · Leituras sem diferenças não liberam questões pendentes.')
        self.start_button.setEnabled(True); self.cancel_button.setEnabled(False)
        self._refresh_table()

    def _analysis_error(self, error):
        if self._closed:
            return
        self.start_button.setEnabled(True); self.cancel_button.setEnabled(False)
        self.status_label.setText(f'Não foi possível analisar a lista: {error}')

    @staticmethod
    def _matches(row, selected):
        status = str(row.get('categoria') or row.get('category') or row.get('status') or '').lower()
        if selected == 'Todas': return True
        if selected == 'Propostas': return status in {'proposta', 'propostas'}
        if selected == 'Divergências': return status in {'divergencia', 'divergência', 'divergências', 'divergente', 'revisao'}
        if selected == 'Bloqueios': return status in {'bloqueada', 'bloqueio', 'bloqueios'}
        if selected == 'Sem diferenças': return status in {'liberada', 'conferir', 'manter', 'sem_diferencas'}
        return status not in {'liberada', 'conferir'}

    def _refresh_table(self):
        selected = self.filter.currentText()
        visible = [row for row in self.rows if self._matches(row, selected)]
        self.table.setRowCount(0)
        for row in visible:
            index = self.table.rowCount(); self.table.insertRow(index)
            field_labels = {'enunciado': 'Enunciado', 'texto_apoio': 'Texto de apoio', 'gabarito': 'Gabarito',
                            'recurso_visual': 'Imagem', 'numero_oficial': 'Número oficial'}
            field = ('Alternativa ' + str(row.get('letter') or '') if row.get('field') == 'alternativas'
                     else field_labels.get(row.get('field'), 'Fonte e identidade'))
            statuses = {'proposta': 'Proposta', 'manter': 'Sem diferenças', 'revisao': 'Revisar',
                        'abster': 'Revisar', 'divergencia': 'Divergência', 'bloqueada': 'Bloqueada', 'liberada': 'Liberada'}
            values = [row.get('questao_id', ''), field, statuses.get(row.get('status'), 'Revisar'),
                      _text(row.get('current')), _text(row.get('proposal')), row.get('reason', '')]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value)); item.setData(32, row)
                item.setToolTip(str(value))
                self.table.setItem(index, column, item)
        self.table.setWordWrap(True)
        for column, width in enumerate((72, 100, 100, 180, 180, 220)):
            self.table.setColumnWidth(column, width)
        self.review_button.setEnabled(self.table.currentRow() >= 0)
        self._show_selected()

    def _selected_row(self):
        item = self.table.item(self.table.currentRow(), 0) if self.table.currentRow() >= 0 else None
        return item.data(32) if item else None

    def _show_selected(self):
        row = self._selected_row()
        self.review_button.setEnabled(row is not None)
        if not row:
            self.preview.clear(); self.crop.hide(); return
        left, right = _diff_html(row.get('current'), row.get('proposal'))
        readings = row.get('readings') or {}
        reading_html = '<br>'.join(f'<b>{escape(str(k))}:</b> {escape(_text(v))}' for k, v in readings.items())
        self.preview.setHtml(f'<b>Atual</b><br>{left or "(vazio)"}<hr><b>Proposta</b><br>{right or "(sem proposta)"}<hr><b>Leituras</b><br>{reading_html or "indisponíveis"}')
        evidence = row.get('evidence') or {}
        image_bytes = evidence.get('image_bytes') if isinstance(evidence, dict) else None
        if image_bytes:
            self.crop.load_image(image_bytes)
            self.crop.show()
        else:
            self.crop.hide()

    def _review_selected(self):
        row = self._selected_row()
        if not row: return
        source = row.get('source') or row.get('region') or {}
        source_id = source.get('source_id') if isinstance(source, dict) else None
        bounds = source.get('bounds') if isinstance(source, dict) else None
        if not source_id or not bounds or len(bounds) != 4:
            from src.ui.components.question_source_review import QuestionSourceReviewDialog
            QuestionSourceReviewDialog(row.get('questao_id'), self).exec()
            self._reanalyze_question(row.get('questao_id')); return
        try:
            from src.models.ia_triage import validate_triage_row
            # The service validates the frozen version/source and returns a
            # boolean; never replace the displayed snapshot with a history
            # object returned by a future implementation.
            if validate_triage_row(row) is False:
                raise ValueError('A versão ou a fonte desta proposta mudou. Analise a lista novamente.')
        except (ValueError, KeyError) as error:
            QMessageBox.warning(self, 'Triagem desatualizada', str(error))
            self.start_analysis(); return
        try:
            from src.ui.components.field_correction import FieldCorrectionDialog
            pane = _SourcePane(source_id, source.get('page', 1), bounds, self)
            dialog = FieldCorrectionDialog(row.get('version_id'), row.get('field', 'enunciado'), pane, self)
            proposal = _text(row.get('proposal'))
            analysis = row.get('analysis')
            if analysis:
                # Let FieldCorrectionDialog merge an alternative proposal
                # into the complete current alternatives list.  Assigning a
                # scalar here would silently erase the other alternatives.
                if row.get('field') == 'alternativas' and row.get('letter'):
                    dialog.ai_letter.setCurrentText(str(row['letter']))
                dialog._ai_done(dict(analysis))
            elif proposal:
                dialog.proposal.setPlainText(proposal)
            if dialog.exec():
                version_id = row.get('version_id')
                new_version = getattr(dialog, 'result_version_id', version_id) or version_id
                if new_version == version_id:
                    self.status_label.setText('Nenhuma alteração foi aplicada; a triagem permanece na fila.')
                else:
                    self.status_label.setText('Correção salva como nova versão pendente de conferência.')
                    self._reanalyze_question(row.get('questao_id'))
        except (ValueError, KeyError, TypeError) as error:
            QMessageBox.warning(self, 'Conferência indisponível', str(error))

    def _reanalyze_question(self, question_id):
        """Atualiza somente a questão editada, preservando as demais linhas."""
        if question_id is None or self.task.running:
            return
        try:
            from src.models.ia_triage import triage_questions
        except ImportError as error:
            self._analysis_error(str(error)); return
        cancel = Event()
        self._cancel = cancel
        self._cancel_requested = False
        self.cancel_button.setEnabled(True)
        self.start_button.setEnabled(False)
        def done(result):
            fresh = list((result or {}).get('rows') or [])
            self.rows = [item for item in self.rows if item.get('questao_id') != question_id]
            self.rows.extend(fresh or [{'questao_id': question_id, 'categoria': 'revisao',
                                        'status': 'revisao', 'reason': 'Nova versão pendente de conferência.'}])
            self.start_button.setEnabled(True); self.cancel_button.setEnabled(False)
            self._refresh_table()
        self.task.submit(lambda: triage_questions([question_id], cancel_event=cancel), done, self._analysis_error)

    def closeEvent(self, event):
        self._closed = True
        self._cancel.set(); self.task.invalidate()
        super().closeEvent(event)

    def done(self, result):
        self._closed = True
        self._cancel.set(); self.task.invalidate()
        super().done(result)


__all__ = ['TriageReviewDialog']
