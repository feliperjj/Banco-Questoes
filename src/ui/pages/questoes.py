import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from src.ui.components.question_editor import QuestionEditor
from src.ui.components.question_source_review import QuestionSourceReviewDialog
from src.ui.database_task import DatabaseTask
from src.models.review_workflow import STAGE_LABELS
from src.models.provenance_service import (
    begin_source_verification_batch, end_source_verification_batch,
)

import src.models.questoes_repo as repo
from src.importador.validacao import problemas_estrutura


logger = logging.getLogger(__name__)


class QuestaoDialog(QDialog):
    def __init__(self, questao_dados=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar questão" if questao_dados else "Nova questão")
        self.resize(620, 660)
        self.questao_id = (questao_dados or {}).get("id")
        self._dirty = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        titulo = QLabel(self.windowTitle())
        titulo.setObjectName("page-title")
        layout.addWidget(titulo)
        self.editor = QuestionEditor()
        self.editor.load(questao_dados or {})
        self.editor.changed.connect(self._alterado)
        layout.addWidget(self.editor, 1)
        # Os consumidores existentes continuam usando os mesmos campos públicos.
        for nome in ("enunciado_input", "tipo_combo", "disciplina_input", "topico_input",
                     "banca_input", "ano_input", "dificuldade_combo", "gabarito_input", "alternativas_input"):
            setattr(self, nome, getattr(self.editor, nome))
        footer = QHBoxLayout()
        if self.questao_id:
            excluir = QPushButton("Excluir questão")
            excluir.setObjectName("danger-button")
            excluir.clicked.connect(self.excluir)
            footer.addWidget(excluir)
        footer.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setObjectName("secondary-button")
        cancelar.clicked.connect(self.reject)
        footer.addWidget(cancelar)
        self.salvar_btn = QPushButton("Salvar questão")
        self.salvar_btn.clicked.connect(self.salvar)
        footer.addWidget(self.salvar_btn)
        self.review_btn = QPushButton("Conferir com originais")
        self.review_btn.setObjectName("secondary-button")
        self.review_btn.setEnabled(bool(self.questao_id))
        self.review_btn.clicked.connect(self.abrir_conferencia)
        footer.addWidget(self.review_btn)
        layout.addLayout(footer)

    def _alterado(self):
        self._dirty = True

    def reject(self):
        if self._dirty and QMessageBox.question(self, "Descartar alterações?",
                "Há alterações não salvas. Deseja descartá-las?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        super().reject()

    def salvar(self, fechar=True):
        try:
            dados = self.editor.data(validate=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Revise a questão", str(exc))
            return
        self.salvar_btn.setEnabled(False)
        try:
            if self.questao_id:
                repo.atualizar_questao(self.questao_id, dados)
            else:
                self.questao_id = repo.criar_questao(dados)
        except Exception:
            logger.exception("Falha ao salvar questão")
            QMessageBox.critical(self, "Não foi possível salvar", "Suas alterações continuam no formulário. Tente novamente.")
            self.salvar_btn.setEnabled(True)
            return
        self._dirty = False
        self.review_btn.setEnabled(True)
        if fechar:
            self.accept()

    def abrir_conferencia(self):
        if self._dirty:
            self.salvar(fechar=False)
            if self._dirty or not self.questao_id:
                return
        dialog = QuestionSourceReviewDialog(self.questao_id, self)
        dialog.exec()

    def excluir(self):
        if QMessageBox.question(self, "Excluir questão?", "A questão será removida do acervo ativo. O histórico será preservado.",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            repo.excluir_questao(self.questao_id)
        except Exception:
            logger.exception("Falha ao excluir questão")
            QMessageBox.critical(self, "Não foi possível excluir", "Tente novamente.")
            return
        self._dirty = False
        self.accept()


class QuestoesPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(12)
        titulo = QLabel("Banco de questões")
        titulo.setObjectName("page-title")
        subtitulo = QLabel("Pesquise, revise e mantenha seu acervo organizado.")
        subtitulo.setObjectName("page-subtitle")
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        self.filtro_gabarito = QComboBox()
        for label, value in (
            ("Todas as questões", "all"), ("Sem gabarito", "no_answer"),
            ("Com gabarito", "answer"), ("Anuladas", "annulled"),
            ("Problemas de extração", "structure"),
            ("Funil: fonte ou identidade", "funnel:identidade_fonte"),
            ("Funil: numeração", "funnel:numeracao"),
            ("Funil: estrutura e visual", "funnel:estrutura"),
            ("Funil: alertas suspeitos", "funnel:revisao_alertas"),
            ("Funil: revisão de conteúdo", "funnel:revisao_conteudo"),
            ("Funil: confirmação de gabarito", "funnel:confirmacao_gabarito"),
            ("Funil: conflito de identidade/gabarito", "funnel:conflito"),
            ("Funil: conteúdo rejeitado", "funnel:rejeitada"),
            ("Funil: liberadas", "funnel:liberada"),
        ):
            self.filtro_gabarito.addItem(label, value)
        self._diagnostic_generation = 0
        self._diagnostic_candidates = []
        self._diagnostic_matches = []
        self._diagnostic_index = 0
        self._diagnostic_stage = ""
        self._source_verification_token = None
        self.filtro_gabarito.currentIndexChanged.connect(self.carregar_dados)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.busca_input = QLineEdit()
        self.busca_input.setObjectName("search-input")
        self.busca_input.setPlaceholderText("Buscar no enunciado...")
        self.busca_input.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.carregar_dados)
        self.busca_input.textChanged.connect(lambda: self._search_timer.start())
        btn_nova = QPushButton("+ Nova questão")
        btn_nova.setObjectName("primary-action")
        btn_nova.clicked.connect(self.abrir_nova_questao)
        top.addWidget(self.busca_input); top.addWidget(btn_nova); layout.addLayout(top)
        linha = QHBoxLayout()
        self.contagem = QLabel()
        self.contagem.setObjectName("section-hint")
        linha.addWidget(self.contagem, 1)
        linha.addWidget(self.filtro_gabarito)
        layout.addLayout(linha)
        self.analysis_status = QLabel("Selecione uma questão para ver a etapa do funil e todos os motivos.")
        self.analysis_status.setObjectName("section-hint")
        self.analysis_status.setWordWrap(True)
        analysis_row = QHBoxLayout()
        analysis_row.addWidget(self.analysis_status, 1)
        self.analyze_selected = QPushButton("Analisar e conferir fonte")
        self.analyze_selected.setObjectName("secondary-button")
        self.analyze_selected.clicked.connect(self.abrir_analise_selecionada)
        analysis_row.addWidget(self.analyze_selected)
        self.review_queue_task = DatabaseTask(self)
        self.review_queue_button = QPushButton('Revisar pendências da lista')
        self.review_queue_button.clicked.connect(self.abrir_fila_revisao)
        layout.addLayout(analysis_row)
        queue_actions = QHBoxLayout()
        queue_actions.addWidget(self.review_queue_button)
        self.triage_button = QPushButton('Triar lista automaticamente')
        self.triage_button.setObjectName('secondary-button')
        self.triage_button.clicked.connect(self.abrir_triagem)
        queue_actions.addWidget(self.triage_button)
        queue_actions.addStretch()
        layout.addLayout(queue_actions)
        self.tabela = QTableWidget(); self.tabela.setColumnCount(7); self.tabela.setHorizontalHeaderLabels(["ID", "Enunciado", "Disciplina", "Banca", "Ano", "Gabarito", "Funil / motivos"])
        self.tabela.setObjectName("question-bank-table"); self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); self.tabela.setSelectionBehavior(QTableWidget.SelectRows); self.tabela.setEditTriggers(QTableWidget.NoEditTriggers); self.tabela.setAlternatingRowColors(True); self.tabela.setShowGrid(False); self.tabela.verticalHeader().setVisible(False); self.tabela.verticalHeader().setDefaultSectionSize(48); self.tabela.doubleClicked.connect(self.abrir_edicao_questao)
        layout.addWidget(self.tabela)
        self.empty = QLabel("Nenhuma questão encontrada. Altere a busca ou importe um caderno.")
        self.empty.setObjectName("empty-state")
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.carregar_dados()

    def showEvent(self, event):
        super().showEvent(event)
        self.carregar_dados()

    def carregar_dados(self):
        if hasattr(self, 'review_queue_task'):
            self.review_queue_task.invalidate()
            self.review_queue_button.setEnabled(True)
        self._end_diagnostic_cache()
        self._diagnostic_generation += 1
        generation = self._diagnostic_generation
        questoes = repo.buscar_questoes(texto=self.busca_input.text())
        filtro = self.filtro_gabarito.currentData()
        if filtro == "no_answer":
            questoes = [q for q in questoes if not q.get("gabarito")]
        elif filtro == "answer":
            questoes = [q for q in questoes if q.get("gabarito") and q["gabarito"] != "Anulada"]
        elif filtro == "annulled":
            questoes = [q for q in questoes if q.get("gabarito") == "Anulada"]
        elif filtro == "structure":
            questoes = [q for q in questoes if problemas_estrutura(q)]
        elif isinstance(filtro, str) and filtro.startswith("funnel:"):
            self.review_queue_button.setEnabled(False)
            self._diagnostic_stage = filtro.split(":", 1)[1]
            self._diagnostic_candidates = questoes
            self._diagnostic_matches = []
            self._diagnostic_index = 0
            self._source_verification_token = begin_source_verification_batch()
            self._diagnose_next(generation)
            return
        self._populate_table(questoes)

    def _diagnose_next(self, generation):
        if generation != self._diagnostic_generation:
            return
        if self._diagnostic_index >= len(self._diagnostic_candidates):
            self._end_diagnostic_cache()
            self._populate_table(self._diagnostic_matches)
            self.contagem.setText(f"{len(self._diagnostic_matches)} questões nesta etapa · diagnóstico do acervo concluído")
            return
        question = self._diagnostic_candidates[self._diagnostic_index]
        assessment = repo.diagnosticar_questao(question["id"])
        question["_funnel_assessment"] = assessment
        stage = self._diagnostic_stage
        has_alerts = any(item["natureza"] == "suspeita" for item in assessment["alertas"])
        codes = {item["codigo"] for item in assessment["pendencias"]}
        matches = (
            assessment["etapa_principal"] == stage
            or (stage == "estrutura" and any(item["etapa"] == "estrutura" for item in assessment["pendencias"]))
            or (stage == "revisao_alertas" and has_alerts)
            or (stage == "conflito" and bool(codes & {"gabarito_conflitante", "escopo_divergente"}))
            or (stage == "rejeitada" and assessment["estado_conteudo"] == "rejeitado")
        )
        if matches:
            self._diagnostic_matches.append(question)
        self._diagnostic_index += 1
        self.contagem.setText(f"Analisando questões para a fila: {self._diagnostic_index}/{len(self._diagnostic_candidates)}")
        QTimer.singleShot(0, lambda: self._diagnose_next(generation))

    def _end_diagnostic_cache(self):
        if self._source_verification_token is not None:
            end_source_verification_batch(self._source_verification_token)
            self._source_verification_token = None

    def _populate_table(self, questoes):
        self.review_queue_button.setEnabled(True)
        self.contagem.setText(f"{len(questoes)} questões · clique duas vezes para editar")
        self.empty.setVisible(not questoes)
        self.tabela.setRowCount(len(questoes))
        for row, q in enumerate(questoes):
            assessment = q.get("_funnel_assessment")
            funnel = "\n".join(item["codigo"] for item in assessment["pendencias"]) if assessment else "Use Analisar"
            valores = [q["id"], q["enunciado"][:50] + "..." if len(q["enunciado"]) > 50 else q["enunciado"], q["disciplina"] or "", q["banca"] or "", str(q["ano"]) if q["ano"] else "", q.get("gabarito") or "Sem gabarito", funnel]
            for col, valor in enumerate(valores): self.tabela.setItem(row, col, QTableWidgetItem(str(valor)))
            self.tabela.item(row, 0).setData(Qt.UserRole, q)
            self.tabela.item(row, 1).setToolTip(q["enunciado"])
            self.tabela.item(row, 6).setToolTip(funnel)
        self.tabela.setColumnWidth(0, 48)
        self.tabela.setColumnWidth(4, 70)
        for col in (2, 3, 5):
            self.tabela.setColumnWidth(col, 100)
        self.tabela.setColumnWidth(6, 190)

    def abrir_nova_questao(self):
        if QuestaoDialog(parent=self).exec(): self.carregar_dados()

    def abrir_edicao_questao(self, index):
        dados = self.tabela.item(index.row(), 0).data(Qt.UserRole)
        if QuestaoDialog(questao_dados=dados, parent=self).exec(): self.carregar_dados()

    def abrir_analise_selecionada(self):
        selecionada = self.tabela.currentRow()
        if selecionada < 0:
            self.analysis_status.setText("Selecione uma questão na lista para iniciar a análise.")
            return
        dados = self.tabela.item(selecionada, 0).data(Qt.UserRole)
        assessment = dados.get("_funnel_assessment") or repo.diagnosticar_questao(dados["id"])
        motivos = "; ".join(item["codigo"] for item in assessment["pendencias"])
        self.analysis_status.setText(
            f"{STAGE_LABELS.get(assessment['etapa_principal'], 'Conferência pendente')} · "
            f"{'liberada' if assessment['liberada'] else 'pendente'}"
            + (f" · Motivos: {motivos}" if motivos else " · sem pendências")
        )
        dialog = QuestionSourceReviewDialog(dados["id"], self)
        dialog.exec()
        self.carregar_dados()

    def abrir_triagem(self):
        ids = [self.tabela.item(row, 0).data(Qt.UserRole)['id'] for row in range(self.tabela.rowCount())]
        if not ids:
            self.analysis_status.setText('Não há questões nesta lista. Ajuste a busca ou os filtros.')
            return
        from src.ui.components.triage_review import TriageReviewDialog
        dialog = TriageReviewDialog(ids, self)
        QTimer.singleShot(0, dialog.start_analysis)
        dialog.exec()
        self.carregar_dados()

    def abrir_fila_revisao(self):
        ids = [self.tabela.item(row, 0).data(Qt.UserRole)['id'] for row in range(self.tabela.rowCount())]
        if not ids:
            self.analysis_status.setText('Não há questões nesta lista. Ajuste a busca ou os filtros.')
            return
        self.review_queue_button.setEnabled(False)
        self.analysis_status.setText('Preparando a fila de pendências desta lista…')
        self.review_queue_task.submit(lambda: repo.diagnosticar_fila(ids), self._fila_pronta, self._erro_fila)

    def _fila_pronta(self, pending):
        self.review_queue_button.setEnabled(True)
        if not pending:
            self.analysis_status.setText('Todas as questões desta lista estão liberadas.')
            return
        ids = [item['id'] for item in pending]
        dialog = QuestionSourceReviewDialog(ids[0], self, question_ids=ids)
        dialog.exec()
        self.carregar_dados()
        self.analysis_status.setText('Fila revisada. Os filtros foram atualizados com as decisões atuais.')

    def _erro_fila(self, error):
        self.review_queue_button.setEnabled(True)
        self.analysis_status.setText(f'Não foi possível preparar a fila: {error}')
