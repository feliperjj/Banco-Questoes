"""Conferência explícita de uma versão lado a lado com os PDFs originais."""

from pathlib import Path
import json
import pdfplumber

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox,
    QComboBox, QDoubleSpinBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from src.db.models import (
    DocumentoFonte, EvidenciaQuestao, QuestaoVersao,
    RevisaoConteudo, RevisaoGabarito,
)
from src.models.provenance_service import (
    add_evidence, create_question_version, create_source, review_answer,
    review_content, resolve_diagnostic, verify_source,
)
from src.models import questoes_repo as repo
from src.models.review_workflow import diagnostic_target, render_source_region, STAGE_LABELS
from src.ui.components.field_correction import FieldCorrectionDialog
from src.ui.components.evidence_crop import EvidenceCrop
from src.ui.database_task import DatabaseTask


class _PdfEvidencePane(QWidget):
    def __init__(self, label: str, source_type: str, parent=None):
        super().__init__(parent)
        self.source_type = source_type
        self.parent_dialog = None
        self.source_id = None
        self.source_path = None
        self.document = QPdfDocument(self)
        self.crop_task = DatabaseTask(self)
        self.crop_timer = QTimer(self)
        self.crop_timer.setSingleShot(True)
        self.crop_timer.setInterval(150)
        self.crop_timer.timeout.connect(self._render_crop)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel(label), 1)
        self.open_button = QPushButton("Abrir PDF original")
        self.open_button.clicked.connect(self.open_pdf)
        header.addWidget(self.open_button)
        layout.addLayout(header)
        self.path_label = QLabel("Nenhum documento selecionado. PDF original obrigatório; DOCX não tem paginação estável nesta versão.")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setPrefix("Página ")
        self.page_spin.valueChanged.connect(self._navigate)
        page_row = QHBoxLayout()
        page_row.addWidget(self.page_spin)
        self.zoom_out = QPushButton("−")
        self.zoom_in = QPushButton("+")
        self.zoom_out.clicked.connect(lambda: self._change_zoom(0.85))
        self.zoom_in.clicked.connect(lambda: self._change_zoom(1.18))
        page_row.addWidget(self.zoom_out)
        page_row.addWidget(self.zoom_in)
        self.bounds_toggle = QToolButton()
        self.bounds_toggle.setText('Ajustar recorte')
        self.bounds_toggle.setCheckable(True)
        self.bounds_toggle.setObjectName('exam-context-toggle')
        page_row.addWidget(self.bounds_toggle)
        page_row.addStretch()
        layout.addLayout(page_row)
        self.bounds_panel = QWidget()
        bounds = QHBoxLayout(self.bounds_panel)
        bounds.setContentsMargins(0, 0, 0, 0)
        bounds.addWidget(QLabel("Recorte (pontos PDF):"))
        self.bounds = {}
        for name, label in (("x0", "x₀"), ("y0", "y₀"), ("x1", "x₁"), ("y1", "y₁")):
            bounds.addWidget(QLabel(label))
            control = QDoubleSpinBox()
            control.setRange(0, 5000)
            control.setDecimals(1)
            control.setSingleStep(10)
            control.setMaximumWidth(92)
            bounds.addWidget(control)
            self.bounds[name] = control
            control.valueChanged.connect(self._schedule_crop)
        self.bounds_panel.hide()
        self.bounds_toggle.toggled.connect(self.bounds_panel.setVisible)
        layout.addWidget(self.bounds_panel)
        self.viewer = QPdfView()
        self.viewer.setDocument(self.document)
        self.viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.crop_view = EvidenceCrop()
        self.view_tabs = QTabWidget()
        self.view_tabs.addTab(self.crop_view, 'Recorte selecionado')
        self.view_tabs.addTab(self.viewer, 'Página completa')
        layout.addWidget(self.view_tabs, 1)

    def _schedule_crop(self):
        self.crop_task.invalidate()
        self.crop_timer.start()

    def clear_source(self):
        self.crop_timer.stop()
        self.crop_task.invalidate()
        self.document.close()
        self.source_id = None
        self.source_path = None
        self.crop_view.show_message('Selecione o PDF original para conferir o recorte.')

    def _render_crop(self):
        if self.source_id is None:
            return
        source, page = self.source_id, self.page_spin.value()
        bounds = tuple(self.bounds[n].value() for n in ('x0', 'y0', 'x1', 'y1'))
        self.crop_view.show_message('Preparando o recorte original…')
        self.crop_task.submit(lambda: render_source_region(source, page, bounds),
                              self.crop_view.load_image, self.crop_view.show_message)

    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar documento-fonte", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            self.load_path(path)
        except Exception as error:
            QMessageBox.warning(self, "PDF indisponível", str(error))

    def load_path(self, path: str):
        if Path(path).suffix.lower() != ".pdf":
            raise ValueError("A primeira versão da conferência de páginas aceita somente PDF.")
        self.clear_source()
        self.document.load(path)
        if self.document.status() != QPdfDocument.Status.Ready:
            raise ValueError("Não foi possível abrir o PDF selecionado.")
        self.source_id = create_source(path, tipo="pdf")
        self.source_path = str(Path(path).resolve())
        self.path_label.setText(f"{Path(path).name} · {self.document.pageCount()} páginas · fonte identificada por SHA-256")
        self.page_spin.setRange(1, max(1, self.document.pageCount()))
        self.page_spin.setValue(1)
        self._set_page_bounds(0)
        self._navigate(1)

    def _navigate(self, page: int):
        if self.document.status() == QPdfDocument.Status.Ready:
            self.viewer.pageNavigator().jump(page - 1, QPointF(0, 0), 0)
            self._set_page_bounds(page - 1)

    def _set_page_bounds(self, page_index: int):
        width, height, _ = self._page_geometry(page_index)
        values = {"x0": 0, "y0": 0, "x1": width, "y1": height}
        for name, control in self.bounds.items():
            control.setMaximum(max(0.0, values["x1" if name in {"x0", "x1"} else "y1"]))
            control.setValue(values[name])

    def _change_zoom(self, multiplier: float):
        if self.view_tabs.currentIndex() == 0:
            self.crop_view.change_zoom(multiplier)
            return
        self.viewer.setZoomMode(QPdfView.ZoomMode.Custom)
        self.viewer.setZoomFactor(max(0.5, min(3.0, self.viewer.zoomFactor() * multiplier)))

    def _page_geometry(self, page_index: int):
        if not self.source_path:
            raise ValueError("A fonte PDF não está carregada.")
        with pdfplumber.open(self.source_path) as pdf:
            page = pdf.pages[page_index]
            return float(page.width), float(page.height), int(page.rotation or 0) % 360

    def add_page_evidence(self, version_id: int, part: str) -> int:
        if self.source_id is None or self.document.status() != QPdfDocument.Status.Ready:
            raise ValueError("Selecione e abra o PDF original antes de registrar a evidência.")
        page_index = self.page_spin.value() - 1
        width, height, rotation = self._page_geometry(page_index)
        bounds = tuple(self.bounds[name].value() for name in ("x0", "y0", "x1", "y1"))
        if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            raise ValueError("O recorte precisa ter largura e altura maiores que zero.")
        return add_evidence(
            version_id,
            self.source_id,
            part=part,
            page=page_index + 1,
            bounds=bounds,
            coordinate_system="pdf-point; origem superior esquerda",
            page_size=(width, height),
            rotation=rotation,
            scope=self.parent_dialog.scope_for(part),
            excerpt=f"Recorte manual da página {page_index + 1}: {bounds} pontos PDF.",
        )


class QuestionSourceReviewDialog(QDialog):
    def __init__(self, question_id: int, parent=None, *, question_ids=None):
        super().__init__(parent)
        self.question_id = question_id
        self.version_id = None
        self.content_evidence_ids = []
        self.answer_evidence_ids = []
        self.setWindowTitle("Conferir questão com a fonte")
        self.resize(960, 640)
        layout = QVBoxLayout(self)
        self.queue_ids = list(dict.fromkeys(question_ids or [question_id]))
        if question_id not in self.queue_ids:
            self.queue_ids.insert(0, question_id)
        queue_row = QHBoxLayout()
        self.queue_selector = QComboBox()
        for position, ident in enumerate(self.queue_ids, 1):
            self.queue_selector.addItem(f"{position} de {len(self.queue_ids)} · Questão ID {ident}", ident)
        self.queue_selector.setCurrentIndex(self.queue_ids.index(question_id))
        self.queue_previous = QPushButton('‹ Anterior')
        self.queue_next = QPushButton('Próxima pendência ›')
        for button in (self.queue_previous, self.queue_next):
            button.setObjectName('secondary-button')
        self.queue_previous.clicked.connect(lambda: self.queue_selector.setCurrentIndex(self.queue_selector.currentIndex() - 1))
        self.queue_next.clicked.connect(lambda: self.queue_selector.setCurrentIndex(self.queue_selector.currentIndex() + 1))
        queue_row.addWidget(self.queue_previous)
        queue_row.addWidget(self.queue_selector, 1)
        queue_row.addWidget(self.queue_next)
        layout.addLayout(queue_row)
        self.version_label = QLabel()
        self.version_label.setWordWrap(True)
        self.version_label.setObjectName("section-hint")
        layout.addWidget(self.version_label)
        self.version_selector = QComboBox()
        self.version_selector.currentIndexChanged.connect(self._load_selected_version)
        layout.addWidget(self.version_selector)
        self.pending_selector = QComboBox()
        self.pending_selector.setMinimumWidth(0)
        self.pending_selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.pending_selector.setMinimumContentsLength(20)
        self.pending_selector.currentIndexChanged.connect(self._select_pending)
        layout.addWidget(self.pending_selector)
        self.pending_action = QLabel()
        self.pending_action.setObjectName('review-next-action')
        self.pending_action.setWordWrap(True)
        layout.addWidget(self.pending_action)
        guided_actions = QHBoxLayout()
        self.guide_button = QPushButton('Conferir esta pendência')
        self.guide_button.setObjectName('secondary-button')
        self.guide_button.clicked.connect(self._focus_pending)
        self.correct_button = QPushButton('Corrigir somente este campo')
        self.correct_button.setObjectName('secondary-button')
        self.correct_button.clicked.connect(self._correct_field)
        guided_actions.addWidget(self.guide_button)
        guided_actions.addWidget(self.correct_button)
        guided_actions.addStretch()
        layout.addLayout(guided_actions)

        self.sources = QTabWidget()
        self.question_pdf = _PdfEvidencePane("Conteúdo da questão", "caderno_questoes", self.sources)
        self.answer_pdf = _PdfEvidencePane("Gabarito oficial", "documento_gabarito", self.sources)
        self.question_pdf.parent_dialog = self
        self.answer_pdf.parent_dialog = self
        self.sources.addTab(self.question_pdf, "Questão e contexto")
        self.sources.addTab(self.answer_pdf, "Gabarito (somente conferência)")
        self.work_tabs = QTabWidget()
        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_layout.setContentsMargins(0, 0, 0, 0)
        comparison = QSplitter(Qt.Horizontal)
        comparison.setChildrenCollapsible(False)
        comparison.addWidget(self.sources)
        self.comparison_text = QPlainTextEdit()
        self.comparison_text.setReadOnly(True)
        self.comparison_text.setMinimumWidth(0)
        self.comparison_text.setPlaceholderText('Conteúdo salvo para comparar com o original')
        comparison.addWidget(self.comparison_text)
        comparison.setStretchFactor(0, 3)
        comparison.setStretchFactor(1, 2)
        source_layout.addWidget(comparison)
        self.comparison = comparison
        self.work_tabs.addTab(source_page, "Originais")

        self.extracted = QPlainTextEdit()
        self.extracted.setReadOnly(True)
        self.answer_label = QLabel()
        self.review_history_label = QLabel()
        self.review_history_label.setWordWrap(True)
        self.diagnostic_label = QLabel()
        self.diagnostic_label.setWordWrap(True)
        self.extracted.setMinimumHeight(150)

        form = QFormLayout()
        self.reviewer = QPlainTextEdit()
        self.reviewer.setMaximumHeight(52)
        self.reviewer.setPlaceholderText("Nome declarado de quem conferiu")
        self.rationale = QPlainTextEdit()
        self.rationale.setMaximumHeight(72)
        self.rationale.setPlaceholderText("Justificativa curta da decisão")
        form.addRow("Responsável", self.reviewer)
        form.addRow("Justificativa", self.rationale)
        self.proof_identity = QPlainTextEdit()
        self.proof_identity.setMaximumHeight(48)
        self.proof_identity.setPlaceholderText("Identificação da prova exibida na fonte")
        self.scope_cargo = QPlainTextEdit()
        self.scope_cargo.setMaximumHeight(48)
        self.scope_cargo.setPlaceholderText("Cargo/área deste trecho")
        self.scope_code = QPlainTextEdit()
        self.scope_code.setMaximumHeight(48)
        self.scope_code.setPlaceholderText("Código/tipo de prova deste trecho")
        self.scope_version = QPlainTextEdit()
        self.scope_version.setMaximumHeight(48)
        self.scope_version.setPlaceholderText("Versão/edição identificada na fonte")
        self.answer_status = QComboBox()
        self.answer_status.addItem("Preliminar", "preliminar")
        self.answer_status.addItem("Definitivo", "definitivo")
        self.answer_status.addItem("Anulado", "anulado")
        self.answer_status.addItem("Conflitante", "conflitante")
        form.addRow("Prova identificada", self.proof_identity)
        form.addRow("Cargo/área", self.scope_cargo)
        form.addRow("Código/tipo", self.scope_code)
        form.addRow("Versão/edição", self.scope_version)
        form.addRow("Situação do gabarito", self.answer_status)
        self.content_decision = QComboBox()
        self.content_decision.addItem("Manter pendente", "pendente")
        self.content_decision.addItem("Conferido com evidência", "conferido")
        self.content_decision.addItem("Rejeitado", "rejeitado")
        form.addRow("Decisão do conteúdo", self.content_decision)
        self.answer_decision = QComboBox()
        self.answer_decision.addItem("Manter pendente", "desconhecido")
        self.answer_decision.addItem("Registrar preliminar", "preliminar")
        self.answer_decision.addItem("Confirmar definitivo", "definitivo_confirmado")
        self.answer_decision.addItem("Registrar anulado", "anulado")
        self.answer_decision.addItem("Registrar conflito", "conflitante")
        self.answer_decision.currentIndexChanged.connect(self._sync_answer_status)
        form.addRow("Decisão do gabarito", self.answer_decision)
        review_page = QWidget()
        review_layout = QVBoxLayout(review_page)
        review_layout.addWidget(QLabel("Conteúdo estruturado que está sendo conferido"))
        review_layout.addWidget(self.extracted)
        review_layout.addWidget(self.answer_label)
        review_layout.addWidget(self.review_history_label)
        review_layout.addLayout(form)

        evidence_buttons = QHBoxLayout()
        self.add_content_evidence = QPushButton("Registrar página para o conteúdo")
        self.add_answer_evidence = QPushButton("Registrar página para o gabarito")
        self.add_content_evidence.clicked.connect(self._record_content_evidence)
        self.add_answer_evidence.clicked.connect(self._record_answer_evidence)
        evidence_buttons.addWidget(self.add_content_evidence)
        evidence_buttons.addWidget(self.add_answer_evidence)
        review_layout.addLayout(evidence_buttons)
        review_layout.addStretch()
        review_scroll = QScrollArea()
        review_scroll.setWidgetResizable(True)
        review_scroll.setWidget(review_page)
        self.work_tabs.addTab(review_scroll, "Conteúdo e decisões")
        layout.addWidget(self.diagnostic_label)
        layout.addWidget(self.work_tabs, 1)

        footer = QHBoxLayout()
        self.content_button = QPushButton("Registrar decisão de conteúdo")
        self.answer_button = QPushButton("Registrar decisão de gabarito")
        self.resolve_alert_button = QPushButton("Resolver alerta selecionado")
        self.alert_code = QComboBox()
        self.alert_decision = QComboBox()
        self.alert_decision.addItem("Suspeita descartada com evidência", "alerta_descartado")
        self.alert_decision.addItem("Erro confirmado", "erro_confirmado")
        close = QPushButton("Fechar")
        self.content_button.clicked.connect(self._review_content)
        self.answer_button.clicked.connect(self._review_answer)
        self.resolve_alert_button.clicked.connect(self._resolve_alert)
        alert_row = QHBoxLayout()
        alert_row.addWidget(self.alert_code, 1)
        alert_row.addWidget(self.alert_decision)
        alert_row.addWidget(self.resolve_alert_button)
        action_row = QHBoxLayout()
        action_row.addWidget(self.content_button)
        action_row.addWidget(self.answer_button)
        close.clicked.connect(self.accept)
        action_row.addStretch()
        action_row.addWidget(close)
        self.alert_controls = QWidget()
        self.alert_controls.setLayout(alert_row)
        alert_row.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.alert_controls)
        layout.addLayout(action_row)
        self.queue_selector.currentIndexChanged.connect(self._select_queue_question)
        self._load_current_question()

    def _select_queue_question(self):
        ident = self.queue_selector.currentData()
        if ident is None:
            return
        self.question_id = ident
        self.rationale.clear()
        self._load_current_question()

    def _select_pending(self):
        item = self.pending_selector.currentData()
        guidance = {
            'conteudo_nao_conferido': 'Compare o enunciado, o contexto e as alternativas com o original. Registre a decisão em Conteúdo e decisões.',
            'gabarito_nao_confirmado': 'Abra o gabarito definitivo, confira o número e a resposta e registre a decisão em Conteúdo e decisões.',
            'numeracao_ausente': 'Localize o número impresso no original e use Corrigir somente este campo para registrá-lo.',
        }
        self.pending_action.setText(
            guidance.get(item['codigo'], item.get('acao_necessaria') or item['mensagem'])
            if item else 'Conferência concluída para esta versão. Você pode continuar pela fila.')
        self.guide_button.setEnabled(item is not None)

    def _focus_pending(self):
        item = self.pending_selector.currentData()
        if not item:
            return
        part = 'gabarito' if diagnostic_target(item) == 'gabarito' else 'conteudo'
        self.work_tabs.setCurrentIndex(0)
        self.sources.setCurrentIndex(1 if part == 'gabarito' else 0)
        evidence = (EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == self.version_id))
        ref = next((r for r in evidence if r.id in item.get('evidencia_disponivel', [])), None)
        if ref is None:
            ref = next((r for r in evidence if r.parte == part), None)
        if ref:
            pane = self.answer_pdf if ref.parte == 'gabarito' else self.question_pdf
            self.sources.setCurrentWidget(pane)
            self._load_evidence(pane, ref)
        index = self.alert_code.findData(item['codigo'])
        if index >= 0:
            self.alert_code.setCurrentIndex(index)

    def _correct_field(self):
        item = self.pending_selector.currentData()
        field = diagnostic_target(item) if item else 'enunciado'
        pane = self.answer_pdf if field == 'gabarito' else self.question_pdf
        dialog = FieldCorrectionDialog(self.version_id, field, pane, self)
        if dialog.exec():
            self._load_current_question()

    def _load_evidence(self, pane, evidence):
        pane.clear_source()
        source = DocumentoFonte.get_by_id(evidence.documento_fonte_id)
        if not source.localizacao or not Path(source.localizacao).is_file():
            pane.path_label.setText('Fonte indisponível. Localize o PDF original íntegro.')
            return
        if not verify_source(source.id)['integro']:
            pane.path_label.setText('A fonte foi alterada. Localize o PDF original íntegro para conferir esta evidência.')
            return
        try:
            pane.load_path(source.localizacao)
            pane.page_spin.setValue(evidence.pagina or 1)
            for name in ('x0', 'y0', 'x1', 'y1'):
                value = getattr(evidence, name)
                if value is not None:
                    pane.bounds[name].setValue(value)
            pane.viewer.pageNavigator().jump(pane.page_spin.value() - 1,
                                             QPointF(evidence.x0 or 0, evidence.y0 or 0), 0)
        except ValueError as error:
            pane.path_label.setText(str(error))

    def _load_current_question(self):
        self.queue_previous.setEnabled(self.queue_selector.currentIndex() > 0)
        self.queue_next.setEnabled(self.queue_selector.currentIndex() < len(self.queue_ids) - 1)
        versions = list(QuestaoVersao.select().where(
            QuestaoVersao.questao == self.question_id
        ).order_by(QuestaoVersao.numero_versao))
        if not versions:
            raise ValueError("A questão não existe mais no acervo.")
        self.version_selector.blockSignals(True)
        self.version_selector.clear()
        for version in versions:
            self.version_selector.addItem(
                f"Versão {version.numero_versao} · {version.revisao_conteudo} / {version.revisao_gabarito}",
                version.id,
            )
        self.version_selector.setCurrentIndex(self.version_selector.count() - 1)
        self.version_selector.blockSignals(False)
        self._load_selected_version()

    def _load_selected_version(self, *_):
        version_id = self.version_selector.currentData()
        version = QuestaoVersao.get_or_none(QuestaoVersao.id == version_id) if version_id else None
        if version is None:
            return
        self.version_id = version.id
        current = repo.ultima_versao(self.question_id)
        editable = bool(current and current.id == version.id)
        self.add_content_evidence.setEnabled(editable)
        self.add_answer_evidence.setEnabled(editable)
        self.content_button.setEnabled(editable)
        self.answer_button.setEnabled(editable)
        self.correct_button.setEnabled(editable)
        self.version_label.setText(
            f"Questão ID {self.question_id} · versão {version.numero_versao} · "
            f"conteúdo: {version.revisao_conteudo} · gabarito: {version.revisao_gabarito}"
            + (" · somente leitura (versão histórica)" if not editable else "")
        )
        for pane in (self.question_pdf, self.answer_pdf):
            pane.clear_source()
            pane.path_label.setText("Nenhum documento selecionado.")
            pane.page_spin.setRange(1, 1)
            for control in pane.bounds.values():
                control.setValue(0)
        questao = json.loads(version.conteudo_json)
        fields = ["texto_apoio", "enunciado"]
        rendered = []
        for field in fields:
            text = questao.get(field) or ""
            if text:
                rendered.append(f"{field.replace('_', ' ').title()}\n{text}")
        rendered.extend(f"Alternativa {a['letra']}\n{a['texto']}" for a in questao.get("alternativas", []))
        self.extracted.setPlainText("\n\n".join(rendered))
        self.comparison_text.setPlainText(
            f"Número oficial: {questao.get('numero_oficial') or 'não identificado'}\n\n"
            + '\n\n'.join(rendered)
            + f"\n\nGabarito salvo: {questao.get('gabarito') or 'não cadastrado'}")
        self.answer_label.setText(f"Gabarito estruturado (conferência): {questao.get('gabarito') or 'desconhecido'}")
        content_review = (RevisaoConteudo.select().where(RevisaoConteudo.questao_versao == version.id)
                          .order_by(RevisaoConteudo.id.desc()).first())
        answer_review = (RevisaoGabarito.select().where(RevisaoGabarito.questao_versao == version.id)
                         .order_by(RevisaoGabarito.id.desc()).first())
        self.content_decision.setCurrentIndex(0)
        self.answer_decision.setCurrentIndex(0)
        self.answer_status.setCurrentIndex(0)
        self._load_scope({})
        if content_review:
            content_index = self.content_decision.findData(content_review.decisao)
            if content_index >= 0:
                self.content_decision.setCurrentIndex(content_index)
        if answer_review:
            answer_index = self.answer_decision.findData(answer_review.decisao)
            if answer_index >= 0:
                self.answer_decision.setCurrentIndex(answer_index)
        history = []
        if content_review:
            history.append(f"Conteúdo: {content_review.decisao} · {content_review.responsavel_declarado or 'sem responsável'} · {content_review.justificativa}")
        if answer_review:
            history.append(f"Gabarito: {answer_review.decisao} · {answer_review.responsavel_declarado or 'sem responsável'} · {answer_review.justificativa}")
        self.review_history_label.setText("\n".join(history) or "Ainda não há decisões registradas para esta versão.")
        self._refresh_assessment(version.id)
        evidence = list(EvidenciaQuestao.select().where(EvidenciaQuestao.questao_versao == version.id))
        self.content_evidence_ids = [item.id for item in evidence if item.parte in {"conteudo", "contexto", "recurso_visual"}]
        self.answer_evidence_ids = [item.id for item in evidence if item.parte == "gabarito"]
        if evidence:
            first_content = next((item for item in evidence if item.parte in {"conteudo", "contexto", "recurso_visual"}), None)
            first_answer = next((item for item in evidence if item.parte == "gabarito"), None)
            if first_content:
                scope = json.loads(first_content.escopo_json or "{}")
                self._load_scope(scope)
                self._load_evidence(self.question_pdf, first_content)
            if first_answer:
                self._load_scope(json.loads(first_answer.escopo_json or "{}"))
                self._load_evidence(self.answer_pdf, first_answer)
        elif version.documento_fonte_id:
            source = DocumentoFonte.get_by_id(version.documento_fonte_id)
            if source.localizacao and Path(source.localizacao).is_file() and verify_source(source.id)['integro']:
                try:
                    self.question_pdf.load_path(source.localizacao)
                except ValueError as error:
                    self.question_pdf.path_label.setText(str(error))
        self._focus_pending()

    def _refresh_assessment(self, version_id: int):
        from src.models.provenance_service import assess_version
        assessment = assess_version(version_id)
        self.diagnostic_label.setText(
            f"{STAGE_LABELS.get(assessment['etapa_principal'], 'Conferência pendente')} · "
            + ("Liberada" if assessment["liberada"] else "Pendente")
            + f" · {sum(p['severidade'] != 'informativo' for p in assessment['pendencias'])} pendências"
        )
        self.diagnostic_label.setToolTip('\n'.join(f"{p['codigo']}: {p['mensagem']}" for p in assessment['pendencias']))
        selected = (self.pending_selector.currentData() or {}).get('codigo')
        self.pending_selector.blockSignals(True)
        self.pending_selector.clear()
        for item in assessment['pendencias']:
            if item['severidade'] != 'informativo':
                self.pending_selector.addItem(item['mensagem'], item)
                if item['codigo'] == selected:
                    self.pending_selector.setCurrentIndex(self.pending_selector.count() - 1)
        self.pending_selector.blockSignals(False)
        self._select_pending()
        self.alert_code.clear()
        for alert in assessment["alertas"]:
            if alert["natureza"] == "suspeita" and "resolucao" not in alert:
                self.alert_code.addItem(f"{alert['codigo']} — {alert['mensagem']}", alert["codigo"])
        latest = repo.ultima_versao(self.question_id)
        self.resolve_alert_button.setEnabled(self.alert_code.count() > 0 and latest.id == version_id)
        self.alert_controls.setVisible(self.alert_code.count() > 0)

    def done(self, result):
        for pane in (self.question_pdf, self.answer_pdf):
            pane.clear_source()
        super().done(result)
    def _load_scope(self, scope: dict):
        self.proof_identity.setPlainText(str(scope.get("prova") or ""))
        self.scope_cargo.setPlainText(str(scope.get("cargo") or ""))
        self.scope_code.setPlainText(str(scope.get("codigo") or ""))
        self.scope_version.setPlainText(str(scope.get("versao") or ""))
        status = scope.get("situacao_gabarito")
        index = self.answer_status.findData(status)
        if index >= 0:
            self.answer_status.setCurrentIndex(index)

    def _sync_answer_status(self):
        status = {
            "preliminar": "preliminar", "definitivo_confirmado": "definitivo",
            "anulado": "anulado", "conflitante": "conflitante",
        }.get(self.answer_decision.currentData())
        if status:
            index = self.answer_status.findData(status)
            if index >= 0:
                self.answer_status.setCurrentIndex(index)

    def scope_for(self, part: str) -> dict:
        scope = {
            "prova": self.proof_identity.toPlainText().strip(),
            "cargo": self.scope_cargo.toPlainText().strip(),
            "codigo": self.scope_code.toPlainText().strip(),
            "versao": self.scope_version.toPlainText().strip(),
        }
        if part == "gabarito":
            scope["situacao_gabarito"] = self.answer_status.currentData()
        return scope

    def _ensure_identity_and_rationale(self):
        reviewer = self.reviewer.toPlainText().strip()
        rationale = self.rationale.toPlainText().strip()
        if not reviewer or not rationale:
            raise ValueError("Informe a pessoa responsável e a justificativa; decisões não podem ser presumidas.")
        return reviewer, rationale

    def _record_content_evidence(self):
        try:
            if self.question_pdf.source_id is None:
                raise ValueError("Abra o PDF original da questão primeiro.")
            if not self.content_evidence_ids:
                self.version_id = create_question_version(self.question_id, source_id=self.question_pdf.source_id)
            evidence_id = self.question_pdf.add_page_evidence(self.version_id, "conteudo")
            if evidence_id not in self.content_evidence_ids:
                self.content_evidence_ids.append(evidence_id)
            self._load_current_question_version_only()
            QMessageBox.information(self, "Evidência registrada", "A página foi vinculada a esta versão. Adicione outras páginas se o conteúdo continuar nelas.")
        except Exception as error:
            QMessageBox.warning(self, "Evidência pendente", str(error))

    def _record_answer_evidence(self):
        try:
            if not self.content_evidence_ids:
                raise ValueError("Registre primeiro a página da questão que ancora esta versão.")
            if self.answer_pdf.source_id is None:
                raise ValueError("Abra o PDF original do gabarito primeiro.")
            if not self.version_id:
                raise ValueError("A versão da questão não foi carregada.")
            evidence_id = self.answer_pdf.add_page_evidence(self.version_id, "gabarito")
            if evidence_id not in self.answer_evidence_ids:
                self.answer_evidence_ids.append(evidence_id)
            self._load_current_question_version_only()
            QMessageBox.information(self, "Evidência registrada", "A página do gabarito foi vinculada à versão selecionada.")
        except Exception as error:
            QMessageBox.warning(self, "Evidência pendente", str(error))

    def _load_current_question_version_only(self):
        self._load_current_question()

    def _review_content(self):
        try:
            reviewer, rationale = self._ensure_identity_and_rationale()
            review_content(
                self.version_id,
                decision=self.content_decision.currentData(),
                reviewer=reviewer,
                rationale=rationale,
                evidence_ids=self.content_evidence_ids,
            )
            self._load_current_question_version_only()
            QMessageBox.information(self, "Conteúdo conferido", "A decisão ficou registrada para esta versão específica.")
        except Exception as error:
            QMessageBox.warning(self, "Conferência não liberada", str(error))

    def _review_answer(self):
        try:
            reviewer, rationale = self._ensure_identity_and_rationale()
            version = QuestaoVersao.get_by_id(self.version_id)
            questao = json.loads(version.conteudo_json)
            decision = self.answer_decision.currentData()
            if decision == "desconhecido":
                QMessageBox.information(self, "Gabarito pendente", "Nenhuma decisão foi registrada; a questão continua pendente.")
                return
            review_answer(
                self.version_id,
                answer=questao.get("gabarito"),
                decision=decision,
                reviewer=reviewer,
                rationale=rationale,
                evidence_ids=self.answer_evidence_ids,
            )
            self._load_current_question_version_only()
            QMessageBox.information(self, "Decisão registrada", "A decisão ficou registrada para esta versão específica.")
        except Exception as error:
            QMessageBox.warning(self, "Gabarito não liberado", str(error))

    def _resolve_alert(self):
        try:
            reviewer, rationale = self._ensure_identity_and_rationale()
            code = self.alert_code.currentData()
            if not code:
                raise ValueError("Não há alerta ativo para resolver nesta versão.")
            evidence = self.content_evidence_ids + self.answer_evidence_ids
            resolve_diagnostic(
                self.version_id, code=code, decision=self.alert_decision.currentData(),
                reviewer=reviewer, rationale=rationale, evidence_ids=evidence,
            )
            self._load_current_question_version_only()
            QMessageBox.information(self, "Alerta registrado", "A decisão e a evidência foram vinculadas ao diagnóstico desta versão.")
        except Exception as error:
            QMessageBox.warning(self, "Alerta não resolvido", str(error))
