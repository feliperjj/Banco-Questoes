import logging
from pathlib import Path
from src.ui.components.statement import formatar_enunciado

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QProgressBar, QRadioButton, QScrollArea, QSizePolicy, QTextEdit, QToolButton, QVBoxLayout, QWidget

import src.models.questoes_repo as repo
import src.models.revisao_service as revisao_svc

logger = logging.getLogger(__name__)


class _ExamOptionRow(QFrame):
    """Linha inteira clicável, mantendo o radio como indicador visual."""

    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class ExecucaoProvaPage(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(34, 28, 34, 28)
        self.layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(14)
        self.lbl_info = QLabel("Prova não iniciada")
        self.lbl_info.setObjectName("exam-info")
        header.addWidget(self.lbl_info)
        header.addStretch()
        self.lbl_tempo = QLabel("00:00")
        self.lbl_tempo.setObjectName("timer-label")
        header.addWidget(self.lbl_tempo)
        self.layout.addLayout(header)

        self.lbl_progresso = QLabel("Questão 0 de 0")
        self.lbl_progresso.setObjectName("exam-progress-label")
        self.layout.addWidget(self.lbl_progresso)
        self.barra_progresso = QProgressBar()
        self.barra_progresso.setObjectName("exam-progress")
        self.barra_progresso.setTextVisible(False)
        self.barra_progresso.setRange(0, 1)
        self.barra_progresso.setValue(0)
        self.layout.addWidget(self.barra_progresso)

        self.cartao_questao = QFrame()
        self.cartao_questao.setObjectName("exam-question-card")
        cartao_layout = QVBoxLayout(self.cartao_questao)
        cartao_layout.setContentsMargins(24, 22, 24, 24)
        cartao_layout.setSpacing(14)
        self.lbl_tipo_questao = QLabel("ENUNCIADO")
        self.lbl_tipo_questao.setObjectName("exam-question-kicker")
        self.lbl_tipo_questao.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        cartao_layout.addWidget(self.lbl_tipo_questao)
        self._context_sections = {}
        self._adicionar_secao_contexto(cartao_layout, "texto_apoio", "Texto de apoio")
        self._adicionar_secao_contexto(cartao_layout, "instrucoes_prova", "Instruções da prova")
        self.bloco_enunciado = QFrame()
        self.bloco_enunciado.setObjectName("exam-statement-block")
        enunciado_layout = QVBoxLayout(self.bloco_enunciado)
        enunciado_layout.setContentsMargins(16, 12, 16, 14)
        enunciado_layout.setSpacing(6)
        self.lbl_enunciado_titulo = QLabel("QUESTÃO")
        self.lbl_enunciado_titulo.setObjectName("exam-statement-title")
        enunciado_layout.addWidget(self.lbl_enunciado_titulo)
        self.lbl_enunciado = QTextEdit()
        self.lbl_enunciado.setObjectName("exam-statement")
        self.lbl_enunciado.setReadOnly(True)
        self.lbl_enunciado.setLineWrapMode(QTextEdit.WidgetWidth)
        self.lbl_enunciado.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lbl_enunciado.setMinimumHeight(66)
        self.lbl_enunciado.setMaximumHeight(360)
        self.lbl_enunciado.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        enunciado_layout.addWidget(self.lbl_enunciado)
        self.lbl_imagem = QLabel()
        self.lbl_imagem.setObjectName("exam-question-image")
        self.lbl_imagem.setAlignment(Qt.AlignCenter)
        self.lbl_imagem.setMaximumHeight(420)
        self.lbl_imagem.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.lbl_imagem.hide()
        enunciado_layout.addWidget(self.lbl_imagem)
        cartao_layout.addWidget(self.bloco_enunciado)
        self.alternativas_frame = QFrame()
        self.alternativas_frame.setObjectName("exam-options-card")
        self.alternativas_frame.setMinimumWidth(0)
        self.alternativas_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.alternativas_layout = QVBoxLayout(self.alternativas_frame)
        self.alternativas_layout.setContentsMargins(12, 10, 12, 10)
        self.alternativas_layout.setSpacing(8)
        self.grupo_botoes = QButtonGroup(self)
        self.grupo_botoes.setExclusive(True)
        self._option_targets = {}
        self.alternativas_scroll = QScrollArea()
        self.alternativas_scroll.setObjectName("exam-options-scroll")
        self.alternativas_scroll.setWidgetResizable(True)
        self.alternativas_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.alternativas_scroll.setMinimumHeight(76)
        self.alternativas_scroll.setMaximumHeight(360)
        self.alternativas_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.alternativas_scroll.setWidget(self.alternativas_frame)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._reiniciar_rolagem)
        cartao_layout.addWidget(self.alternativas_scroll)
        # O espaço livre deve ficar abaixo das alternativas, sem afastá-las
        # do enunciado quando a janela é alta.
        cartao_layout.addStretch(1)
        self.layout.addWidget(self.cartao_questao, 1)

        nav = QHBoxLayout()
        nav.setSpacing(10)
        self.btn_anterior = QPushButton("‹  Anterior")
        self.btn_anterior.setObjectName("secondary-button")
        self.btn_anterior.clicked.connect(self.questao_anterior)
        self.btn_proxima = QPushButton("Próxima  ›")
        self.btn_proxima.clicked.connect(self.proxima_questao)
        self.btn_finalizar = QPushButton("Finalizar prova")
        self.btn_finalizar.setObjectName("danger-button")
        self.btn_finalizar.clicked.connect(self.confirmar_finalizacao)
        nav.addWidget(self.btn_anterior)
        nav.addWidget(self.btn_proxima)
        nav.addStretch()
        nav.addWidget(self.btn_finalizar)
        self.layout.addLayout(nav)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.atualizar_tempo)
        self.prova_id = None
        self.tentativa_id = None
        self.questoes = []
        self.idx_atual = 0
        self.respostas_memoria = {}
        self.tempo_gasto = 0
        self.tempo_limite_seg = 0
        self.em_andamento = False
        self._mostrar_estado_inicial()

    def _adicionar_secao_contexto(self, parent_layout, field_name, title):
        section = QFrame()
        section.setObjectName("exam-context-section")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(6)
        toggle = QToolButton()
        toggle.setObjectName("exam-context-toggle")
        toggle.setText(title)
        toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.RightArrow)
        toggle.setCheckable(True)
        toggle.setChecked(False)
        text = QTextEdit()
        text.setObjectName("exam-context-text")
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.WidgetWidth)
        text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        text.setMinimumHeight(0)
        text.setMaximumHeight(180)
        text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text.hide()
        toggle.toggled.connect(lambda expanded, button=toggle, editor=text: self._alternar_contexto(button, editor, expanded))
        section_layout.addWidget(toggle)
        section_layout.addWidget(text)
        parent_layout.addWidget(section)
        self._context_sections[field_name] = (section, toggle, text)

    def _alternar_contexto(self, button, editor, expanded):
        button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        editor.setVisible(expanded)
        if expanded:
            QTimer.singleShot(0, lambda: self._ajustar_altura_texto(editor, 48, 180))

    def _atualizar_contexto(self, questao):
        for field_name, (section, toggle, editor) in self._context_sections.items():
            value = questao.get(field_name)
            available = isinstance(value, str) and bool(value.strip())
            editor.setPlainText(value.strip() if available else "")
            self._aplicar_espacamento_leitura(editor)
            toggle.setChecked(False)
            section.setVisible(available)
            editor.setVisible(False)
            if available:
                self._ajustar_altura_texto(editor, 48, 180)

    def _limpar_contexto(self):
        for section, toggle, editor in self._context_sections.values():
            toggle.setChecked(False)
            editor.clear()
            editor.hide()
            section.hide()

    def showEvent(self, event):
        super().showEvent(event)
        # Ao voltar para esta aba depois de finalizar, nunca reutilize o
        # enunciado/alternativas da tentativa anterior.
        if not self.em_andamento:
            self._mostrar_estado_inicial()
        else:
            QTimer.singleShot(0, self._ajustar_alturas_conteudo)

    def _mostrar_estado_inicial(self):
        self.timer.stop()
        self.lbl_info.setText("Nenhuma prova em andamento")
        self.lbl_progresso.setText("Escolha uma prova para começar")
        self.lbl_tipo_questao.setText("MODO PROVA")
        self.lbl_enunciado.setText("Suas questões aparecerão aqui quando você iniciar uma prova.")
        self._limpar_contexto()
        self.lbl_imagem.clear()
        self.lbl_imagem.hide()
        self.limpar_alternativas()
        self.btn_anterior.setEnabled(False)
        self.btn_proxima.setEnabled(False)
        self.btn_finalizar.setEnabled(False)
        self.barra_progresso.setRange(0, 1)
        self.barra_progresso.setValue(0)
        self.lbl_tempo.setText("00:00")

    def iniciar(self, prova_id, nome_prova):
        if self.em_andamento:
            QMessageBox.information(self, "Prova em andamento", "Finalize a prova atual antes de iniciar outra.")
            return
        self.prova_id = prova_id
        self.questoes = repo.buscar_questoes_da_prova(prova_id)
        if not self.questoes:
            QMessageBox.critical(self, "Erro", "Esta prova não possui questões.")
            return
        self.tentativa_id = repo.iniciar_tentativa(prova_id)
        configuracao = repo.obter_prova(prova_id) or {}
        self.tempo_limite_seg = max(0, int(configuracao.get("tempo_limite_min") or 0)) * 60
        self.lbl_info.setText(f"{nome_prova}  ·  {len(self.questoes)} questões")
        progresso = repo.obter_progresso(self.tentativa_id)
        self.idx_atual = min(progresso["indice"], len(self.questoes) - 1)
        self.respostas_memoria = progresso["respostas"]
        self.tempo_gasto = progresso["tempo_seg"]
        self.em_andamento = True
        self.lbl_tempo.setText(f"{self.tempo_gasto // 60:02d}:{self.tempo_gasto % 60:02d}")
        self.barra_progresso.setRange(0, len(self.questoes))
        self.timer.start(1000)
        self.btn_finalizar.setEnabled(True)
        self.mostrar_questao_atual()
        logger.info("Tentativa %s iniciada para prova %s", self.tentativa_id, prova_id)

    def atualizar_tempo(self):
        self.tempo_gasto += 1
        self._salvar_progresso()
        self.lbl_tempo.setText(f"{self.tempo_gasto // 60:02d}:{self.tempo_gasto % 60:02d}")
        if self.tempo_limite_seg and self.tempo_gasto >= self.tempo_limite_seg:
            self._finalizar_tentativa_automaticamente()

    def limpar_alternativas(self):
        self._option_targets.clear()
        for button in self.grupo_botoes.buttons():
            self.grupo_botoes.removeButton(button)
            button.deleteLater()
        while self.alternativas_layout.count():
            item = self.alternativas_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def mostrar_questao_atual(self):
        q = self.questoes[self.idx_atual]
        numero = self.idx_atual + 1
        self.lbl_progresso.setText(f"Questão {numero} de {len(self.questoes)}")
        self.barra_progresso.setValue(numero)
        self.lbl_tipo_questao.setText((q.get("disciplina") or "QUESTÃO").upper())
        self._atualizar_contexto(q)
        self.lbl_enunciado.setPlainText(formatar_enunciado(q["enunciado"]))
        self._aplicar_espacamento_leitura(self.lbl_enunciado)
        self._ajustar_altura_texto(self.lbl_enunciado, 66, 360)
        caminho_imagem = q.get("imagem_path")
        pixmap = QPixmap()
        if caminho_imagem:
            caminho = Path(caminho_imagem)
            if not caminho.is_absolute():
                caminho = Path(__file__).resolve().parents[3] / caminho
            pixmap.load(str(caminho))
        if not pixmap.isNull():
            imagem_exibida = pixmap.scaled(900, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_imagem.setPixmap(imagem_exibida)
            self.lbl_imagem.setFixedHeight(imagem_exibida.height())
            self.lbl_imagem.show()
        else:
            self.lbl_imagem.clear()
            self.lbl_imagem.hide()
        self.limpar_alternativas()
        opcoes = [(a["letra"], f"{a['letra']})  {a['texto']}") for a in q.get("alternativas", [])] if q["tipo"] == "multipla_escolha" else [("Certo", "Certo"), ("Errado", "Errado")]
        if not opcoes:
            opcoes = [(letra, letra) for letra in "ABCDE"]
        for valor, rotulo in opcoes:
            option_row = _ExamOptionRow()
            option_row.setObjectName("exam-option")
            option_row.setMinimumWidth(0)
            option_row.setMinimumHeight(48)
            option_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            option_layout = QHBoxLayout(option_row)
            option_layout.setContentsMargins(12, 8, 12, 8)
            option_layout.setSpacing(10)
            rb = QRadioButton()
            rb.setObjectName("exam-option-toggle")
            rb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            label = QLabel(rotulo)
            label.setObjectName("exam-option-label")
            label.setWordWrap(True)
            label.setTextFormat(Qt.PlainText)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            label.setTextInteractionFlags(Qt.NoTextInteraction)
            option_layout.addWidget(rb)
            option_layout.addWidget(label, 1)
            self.alternativas_layout.addWidget(option_row)
            self.grupo_botoes.addButton(rb)
            option_row.clicked.connect(rb.click)
            label.installEventFilter(self)
            rb.installEventFilter(self)
            self._option_targets[label] = rb
            self._option_targets[rb] = rb
            if self.respostas_memoria.get(q["id"]) == valor:
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, o=valor, qid=q["id"]: self.salvar_resposta_temp(checked, qid, o))
            rb.toggled.connect(lambda checked, row=option_row: self._marcar_opcao(row, checked))
            self._marcar_opcao(option_row, rb.isChecked())
        self._ajustar_altura_alternativas()
        self.btn_anterior.setEnabled(self.idx_atual > 0)
        self.btn_proxima.setEnabled(self.idx_atual < len(self.questoes) - 1)
        self.alternativas_scroll.verticalScrollBar().setValue(0)
        self._scroll_timer.start(0)
        QTimer.singleShot(0, self._ajustar_alturas_conteudo)

    @staticmethod
    def _aplicar_espacamento_leitura(editor):
        cursor = QTextCursor(editor.document())
        cursor.select(QTextCursor.Document)
        formato = QTextBlockFormat()
        formato.setLineHeight(140.0, QTextBlockFormat.ProportionalHeight.value)
        cursor.mergeBlockFormat(formato)

    @staticmethod
    def _ajustar_altura_texto(editor, altura_minima, altura_maxima):
        """Deixa o editor na altura do conteúdo, com rolagem só quando precisa."""
        largura = max(1, editor.viewport().width())
        editor.document().setTextWidth(largura)
        altura_documento = editor.document().documentLayout().documentSize().height()
        altura = round(altura_documento + 2 * editor.frameWidth() + 12)
        editor.setFixedHeight(max(altura_minima, min(altura_maxima, altura)))

    def _ajustar_altura_alternativas(self):
        self.alternativas_layout.activate()
        espacamento = max(0, self.alternativas_layout.spacing())
        margens = self.alternativas_layout.contentsMargins()
        largura = self.alternativas_scroll.viewport().width()
        alturas_linhas = []
        for indice in range(self.alternativas_layout.count()):
            linha = self.alternativas_layout.itemAt(indice).widget()
            if linha is None:
                continue
            linha.ensurePolished()
            linha_layout = linha.layout()
            margens_linha = linha_layout.contentsMargins()
            botao = linha_layout.itemAt(0).widget()
            texto = linha_layout.itemAt(1).widget()
            largura_texto = max(
                1,
                largura
                - margens_linha.left()
                - margens_linha.right()
                - botao.sizeHint().width()
                - linha_layout.spacing(),
            )
            altura_texto = texto.heightForWidth(largura_texto) if texto.hasHeightForWidth() else texto.sizeHint().height()
            altura_interna = max(altura_texto, botao.sizeHint().height())
            altura = max(
                linha.minimumHeight(),
                altura_interna + margens_linha.top() + margens_linha.bottom() + 2,
            )
            linha.setFixedHeight(altura)
            alturas_linhas.append(altura)

        altura_conteudo = (
            sum(alturas_linhas)
            + espacamento * max(0, len(alturas_linhas) - 1)
            + margens.top()
            + margens.bottom()
            + 8  # borda do cartão e área interna do scroll
        )
        self.alternativas_scroll.setFixedHeight(max(76, min(360, altura_conteudo)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._ajustar_alturas_conteudo)

    def _ajustar_alturas_conteudo(self):
        self._ajustar_altura_texto(self.lbl_enunciado, 66, 360)
        for section, _, editor in self._context_sections.values():
            if section.isVisible() and editor.isVisible():
                self._ajustar_altura_texto(editor, 48, 180)
        self._ajustar_altura_alternativas()

    def _reiniciar_rolagem(self):
        self.alternativas_scroll.verticalScrollBar().setValue(0)
        self.lbl_enunciado.verticalScrollBar().setValue(0)

    @staticmethod
    def _marcar_opcao(row, selecionada):
        row.setProperty("selected", selecionada)
        row.style().unpolish(row)
        row.style().polish(row)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonPress and watched in self._option_targets:
            if event.button() == Qt.LeftButton:
                self._option_targets[watched].click()
                return True
        return super().eventFilter(watched, event)

    def salvar_resposta_temp(self, checked, q_id, opcao):
        if checked:
            self.respostas_memoria[q_id] = opcao
            self._salvar_progresso()

    def _salvar_progresso(self):
        repo.salvar_progresso(self.tentativa_id, self.respostas_memoria, self.idx_atual, self.tempo_gasto)

    def questao_anterior(self):
        if self.idx_atual > 0:
            self.idx_atual -= 1
            self._salvar_progresso()
            self.mostrar_questao_atual()

    def proxima_questao(self):
        if self.idx_atual < len(self.questoes) - 1:
            self.idx_atual += 1
            self._salvar_progresso()
            self.mostrar_questao_atual()

    def confirmar_finalizacao(self):
        if not self.em_andamento or not self.tentativa_id:
            return
        if len(self.respostas_memoria) < len(self.questoes) and QMessageBox.question(self, "Aviso", "Existem questões sem resposta. Deseja finalizar mesmo assim?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
            return
        self.timer.stop()
        self._finalizar_tentativa()

    def _finalizar_tentativa_automaticamente(self):
        if not self.em_andamento or not self.tentativa_id:
            return
        self.timer.stop()
        self._finalizar_tentativa()

    def _finalizar_tentativa(self):
        resultado = repo.finalizar_tentativa(self.tentativa_id, self.respostas_memoria, self.tempo_gasto)
        for errada in resultado["erradas"]:
            revisao_svc.registrar_erro(errada["id"])
        logger.info("Tentativa %s finalizada: nota %.1f", self.tentativa_id, resultado["nota"])
        self.mostrar_resultado(resultado)

    def mostrar_resultado(self, resultado):
        msg = f"Prova finalizada!\n\nNota: {resultado['nota']:.1f} / 100\nAcertos: {resultado['acertos']} de {resultado['total']}\nTempo: {self.lbl_tempo.text()}"
        if resultado["erradas"]:
            msg += "\n\nQuestões erradas:" + "".join(f"\n- Q_ID {e['id']} (Marcada: {e['marcada']} | Correta: {e['correta']})" for e in resultado["erradas"][:5])
        QMessageBox.information(self, "Resultado", msg)
        self.prova_id = None
        self.tentativa_id = None
        self.questoes = []
        self.respostas_memoria = {}
        self.idx_atual = 0
        self.tempo_limite_seg = 0
        self.em_andamento = False
        self._mostrar_estado_inicial()
        if self.parentWidget() and hasattr(self.parentWidget(), "setCurrentIndex"):
            self.parentWidget().setCurrentIndex(3)
