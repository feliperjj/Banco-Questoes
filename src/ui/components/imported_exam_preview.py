"""Consulta de prova importada que não cria tentativa ou altera respostas."""

from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QSpinBox, QTabWidget, QTextBrowser, QVBoxLayout,
)

from src.config import ROOT_DIR
from src.ui.components.question_source_review import QuestionSourceReviewDialog
from src.ui.components.source_facsimile import SourceFacsimile


def _text(value):
    return escape(str(value or "")).replace("\n", "<br>")


class ImportedExamPreviewDialog(QDialog):
    def __init__(self, prova, questoes, parent=None):
        super().__init__(parent)
        self.prova = prova
        self.questoes = questoes
        self.setWindowTitle(f"Consulta da prova — {prova['nome']}")
        self.resize(960, 720)
        self.setMinimumSize(720, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        title = QLabel(prova["nome"])
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        title.setObjectName("page-title")
        layout.addWidget(title)
        qtd_avaliaveis = int(prova.get("qtd_avaliaveis") or 0)
        qtd_total = int(prova.get("qtd_questoes") or len(questoes))
        parcial = 0 < qtd_avaliaveis < qtd_total
        self._partial_notice = f"Treino parcial: {qtd_avaliaveis} de {qtd_total} questões verificadas. " if parcial else ""
        self.notice = QLabel(
            "Consulta das questões. As respostas só serão registradas ao iniciar uma prova."
            if prova.get("pronta") else
            f"Consulta parcial: {qtd_avaliaveis} de {qtd_total} questões verificadas. "
            "Somente as verificadas serão incluídas na prova."
            if parcial else
            "Consulta disponível. Conteúdo, numeração e gabaritos ainda precisam de conferência "
            "antes de resolver esta prova com nota."
        )
        self.notice.setWordWrap(True)
        self.notice.setObjectName("section-hint")
        layout.addWidget(self.notice)
        navigation = QHBoxLayout()
        self.previous = QPushButton("‹ Anterior")
        self.previous.setObjectName("secondary-button")
        self.previous.clicked.connect(lambda: self.position.setValue(self.position.value() - 1))
        navigation.addWidget(self.previous)
        navigation.addWidget(QLabel("Posição na prova:"))
        self.position = QSpinBox()
        self.position.setRange(1, max(1, len(questoes)))
        self.position.setSuffix(f" de {len(questoes)}")
        self.position.valueChanged.connect(self.show_question)
        navigation.addWidget(self.position)
        self.next = QPushButton("Próxima ›")
        self.next.setObjectName("secondary-button")
        self.next.clicked.connect(lambda: self.position.setValue(self.position.value() + 1))
        navigation.addWidget(self.next)
        navigation.addStretch()
        self.official_number = QLabel()
        self.official_number.setWordWrap(True)
        navigation.addWidget(self.official_number)
        layout.addLayout(navigation)
        self.content = QTextBrowser()
        self.content.setObjectName("imported-exam-preview-content")
        self.content.setOpenLinks(False)
        self.content.setOpenExternalLinks(False)
        self.content.document().setDefaultStyleSheet(
            "body {font-size: 12pt; line-height: 145%;} h3 {font-size: 12pt;} "
            ".option {margin: 12px 0;} .answer {color: #475569;}"
        )
        layout.addWidget(self.content, 1)
        self.original_tabs = QTabWidget()
        self.original_question = SourceFacsimile()
        self.original_context = SourceFacsimile()
        self.original_tabs.addTab(self.original_question, "Questão original")
        self.original_tabs.addTab(self.original_context, "Texto de apoio original")
        self.original_tabs.hide()
        layout.addWidget(self.original_tabs, 1)
        footer = QHBoxLayout()
        self.review = QPushButton("Conferir esta questão com o original")
        self.review.setObjectName("secondary-button")
        self.review.clicked.connect(self.review_question)
        footer.addWidget(self.review)
        footer.addStretch()
        close = QPushButton("Fechar")
        close.setObjectName("secondary-button")
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        self.start = QPushButton(
            f"Resolver {qtd_avaliaveis} verificadas" if parcial else "Fazer prova"
        )
        self.start.setEnabled(bool(questoes and (prova.get("pronta") or parcial)))
        self.start.setToolTip(
            "Resolve somente as questões verificadas; as demais permanecem fora desta prova."
            if parcial else
            "Disponível quando todas as questões estiverem liberadas pela conferência."
        )
        self.start.clicked.connect(self.accept)
        footer.addWidget(self.start)
        layout.addLayout(footer)
        self.show_question()

    def show_question(self, *_):
        index = self.position.value() - 1
        self.previous.setEnabled(index > 0 and bool(self.questoes))
        self.next.setEnabled(index < len(self.questoes) - 1)
        self.review.setEnabled(bool(self.questoes))
        self.position.setEnabled(bool(self.questoes))
        if not self.questoes:
            self.content.setPlainText("Esta prova não possui questões para consulta.")
            self.official_number.clear()
            return
        question = self.questoes[index]
        presentation = question.get("apresentacao_fonte")
        original = bool(presentation and presentation.get("questao"))
        self.content.setVisible(not original)
        self.original_tabs.setVisible(original)
        if original:
            self.original_question.set_assets(presentation["questao"])
            self.original_context.set_assets(presentation.get("contexto", []))
            self.original_tabs.setTabVisible(1, bool(presentation.get("contexto")))
            self.original_tabs.setCurrentIndex(0)
            status = "Verificação automática contra o documento original" if presentation.get("verificacao") == "automatica" else "Conteúdo reparado; liberação ainda pendente"
            if presentation.get("contexto_caderno_completo"):
                self.original_tabs.setTabText(1, "Caderno completo (contexto)")
                status += " · Contexto preservado no caderno completo"
            else:
                self.original_tabs.setTabText(1, "Texto de apoio original")
            self.notice.setText(status + f" · Gabarito salvo: {question.get('gabarito') or 'não cadastrado'}")
        else:
            self.notice.setText("Consulta das questões. As respostas só serão registradas ao iniciar uma prova."
                                if self.prova.get("pronta") else
                                "Consulta disponível. Esta questão ainda depende de conferência com a fonte.")
        if self._partial_notice:
            self.notice.setText(self._partial_notice + self.notice.text())
        number = question.get("numero_oficial")
        self.official_number.setText(
            f"Número oficial: {number}" if number is not None
            else "Número oficial ainda não identificado"
        )
        parts = []
        for field, title in (("instrucoes_prova", "Instruções"), ("texto_apoio", "Texto de apoio")):
            if question.get(field):
                parts.append(f"<h3>{title}</h3><p>{_text(question[field])}</p>")
        parts.append(f"<h3>Enunciado</h3><p>{_text(question.get('enunciado'))}</p>")
        image_path = question.get("imagem_path")
        if image_path:
            path = Path(image_path)
            if not path.is_absolute():
                path = ROOT_DIR / path
            image = QImage(str(path))
            if image.isNull():
                parts.append("<p>Imagem referenciada não disponível. Confira o documento original.</p>")
            else:
                image = image.scaledToWidth(min(760, image.width()), Qt.SmoothTransformation)
                self.content.document().addResource(QTextDocument.ImageResource, QUrl("question-image"), image)
                parts.append('<p><img src="question-image"></p>')
        if question.get("tipo") == "multipla_escolha":
            alternatives = question.get("alternativas") or []
            parts.append("<h3>Alternativas</h3>")
            parts.extend(
                f'<p class="option"><b>{_text(option["letra"])})</b> {_text(option["texto"])}</p>'
                for option in alternatives
            )
            if not alternatives:
                parts.append("<p>Alternativas não cadastradas. Confira o original.</p>")
        else:
            parts.append("<h3>Tipo</h3><p>Certo ou errado</p>")
        answer = _text(question.get("gabarito")) or "Não cadastrado"
        suffix = "" if self.prova.get("pronta") else " · conferência pendente"
        parts.append(f'<p class="answer"><b>Gabarito salvo:</b> {answer}{suffix}</p>')
        self.content.setHtml("<html><body>" + "".join(parts) + "</body></html>")
        self.content.verticalScrollBar().setValue(0)

    def review_question(self):
        if self.questoes:
            question = self.questoes[self.position.value() - 1]
            QuestionSourceReviewDialog(question["id"], self).exec()
