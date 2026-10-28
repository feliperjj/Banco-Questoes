"""Fluxo de importação: arquivo, associação e revisão com rascunhos estáveis."""
import logging
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog, QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QComboBox, QScrollArea, QSpinBox, QSplitter, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from src.importador.extrator import extrair_gabaritos_pdf, extrair_texto
from src.importador.lote import parsear_gabarito_em_lote
from src.importador.servico import importar_caderno
from src.importador.validacao import numero_oficial_explicitamente_extraido
from src.importador.associacao_documental import associar_documentos
from src.importador.catalogo import carregar_catalogo, normalizar_chave
from src.importador.perfis.registro import obter_perfil
from src.config import ROOT_DIR
from src.models import questoes_repo as repo
from src.models.importacao_session import EstadoImportacao, ImportacaoSession, validar_questao
from src.ui.background import BackgroundTask
from src.ui.components.question_editor import QuestionEditor
from src.ui.components.import_choices import ScopeChoice, PageProfileChoices

logger = logging.getLogger(__name__)


def _texto(texto, nome="section-hint"):
    label = QLabel(texto)
    label.setObjectName(nome)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    label.setTextFormat(Qt.PlainText)
    return label


class ImportacaoPage(QWidget):
    abrir_prova = Signal(int)
    abrir_gerador = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("import-page")
        self.session = ImportacaoSession()
        self.current_index = None
        self._loading_instrucoes = False
        self.caminho_questoes_pendente = ""
        self.caminho_gabarito = ""
        self.reconhecimento_caderno = None
        self.reconhecimento_gabarito = None
        self._indices_salvamento = []
        self.operation = None
        self._restoring_draft = False
        self._draft_source_hashes = {}
        self._perfis_caderno_paginas = {}
        self._perfis_gabarito_paginas = {}
        self._paginas_caderno = []
        self._paginas_gabarito = []
        self._quantidade_esperada = None
        self._ultima_verificacao = None
        self.task = BackgroundTask(self)
        self.task.result.connect(self._resultado)
        self.task.error.connect(self._falha)
        self.task.idle.connect(self._task_idle)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(_texto("Seu próximo conjunto de estudos", "section-kicker"))
        layout.addWidget(_texto("Importar questões", "page-title"))
        self.resumo = _texto("Comece com um PDF ou DOCX. Revise antes de adicionar ao acervo.", "page-subtitle")
        layout.addWidget(self.resumo)
        self.steps = QTabWidget()
        self.steps.setObjectName("import-steps")
        layout.addWidget(self.steps, 1)
        self._arquivo_step()
        self._gabarito_step()
        self._revisao_step()
        self.feedback = _texto("Nenhum dado será salvo antes da sua revisão.", "import-feedback")
        layout.addWidget(self.feedback)
        saved_actions = QHBoxLayout()
        self.btn_abrir_prova = QPushButton("Abrir prova e pendências")
        self.btn_abrir_prova.clicked.connect(lambda: self.abrir_prova.emit(self._ultima_verificacao["prova_id"]))
        self.btn_gerar_simulado = QPushButton("Gerar simulado aleatório")
        self.btn_gerar_simulado.clicked.connect(self.abrir_gerador.emit)
        saved_actions.addWidget(self.btn_abrir_prova)
        saved_actions.addWidget(self.btn_gerar_simulado)
        saved_actions.addStretch()
        layout.addLayout(saved_actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(5)
        self.progress.hide()
        layout.addWidget(self.progress)
        footer = QHBoxLayout()
        self.btn_anterior = QPushButton("Voltar")
        self.btn_anterior.setObjectName("secondary-button")
        self.btn_anterior.clicked.connect(lambda: self.steps.setCurrentIndex(self.steps.currentIndex() - 1))
        self.btn_salvar_questao = QPushButton("Salvar esta")
        self.btn_salvar_questao.setObjectName("secondary-button")
        self.btn_salvar_questao.clicked.connect(self.salvar_questao)
        self.btn_salvar_todas = QPushButton("Salvar pendentes")
        self.btn_salvar_todas.clicked.connect(self.salvar_todas)
        self.btn_proxima = QPushButton("Continuar")
        self.btn_proxima.clicked.connect(lambda: self.steps.setCurrentIndex(self.steps.currentIndex() + 1))
        self.btn_cancelar = QPushButton("Cancelar operação")
        self.btn_cancelar.setObjectName("secondary-button")
        self.btn_cancelar.clicked.connect(self._cancelar_operacao)
        self.btn_cancelar.hide()
        footer.addWidget(self.btn_anterior)
        footer.addStretch()
        footer.addWidget(self.btn_salvar_questao)
        footer.addWidget(self.btn_salvar_todas)
        footer.addWidget(self.btn_proxima)
        footer.addWidget(self.btn_cancelar)
        layout.addLayout(footer)
        self.steps.currentChanged.connect(self._sync)
        self.steps.currentChanged.connect(self._agendar_rascunho)
        self.nome_prova_input.textChanged.connect(self._agendar_rascunho)
        self.cargo_gabarito_input.textChanged.connect(self._agendar_rascunho)
        self.codigo_gabarito_input.textChanged.connect(self._agendar_rascunho)
        self.versao_gabarito_input.textChanged.connect(self._agendar_rascunho)
        self.perfil_caderno_combo.currentIndexChanged.connect(self._agendar_rascunho)
        self.perfil_gabarito_combo.currentIndexChanged.connect(self._agendar_rascunho)
        self.nova_versao_checkbox.toggled.connect(self._agendar_rascunho)
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(450)
        self._draft_timer.timeout.connect(self._salvar_rascunho)
        self._sync()
        self._restaurar_rascunho()

    @property
    def questoes_extraidas(self):
        return self.session.questoes

    @property
    def caminho_questoes(self):
        return self.session.caminho

    @property
    def ocupada(self):
        return self.task.running or self.session.estado in {EstadoImportacao.LENDO, EstadoImportacao.SALVANDO}

    def _scroll_step(self, titulo):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("import-step-scroll")
        content = QWidget()
        content.setMinimumWidth(0)
        box = QVBoxLayout(content)
        box.setContentsMargins(22, 22, 22, 22)
        box.setSpacing(16)
        scroll.setWidget(content)
        self.steps.addTab(scroll, titulo)
        return box

    def _arquivo_step(self):
        box = self._scroll_step("1  Arquivo")
        box.addWidget(_texto("Transforme uma prova em questões para estudar.", "import-hero-title"))
        box.addWidget(_texto("Escolha o caderno de questões. Na próxima etapa, associe um gabarito ou siga direto para a revisão."))
        box.addWidget(_texto("Nome da prova cadastrada", "section-title"))
        self.nome_prova_input = QLineEdit()
        self.nome_prova_input.setPlaceholderText("Ex.: Concurso 2026 — Analista")
        box.addWidget(self.nome_prova_input)
        self.btn_selecionar_questoes = QPushButton("Escolher PDF ou DOCX")
        self.btn_selecionar_questoes.setMinimumHeight(44)
        self.btn_selecionar_questoes.clicked.connect(self.selecionar_arquivo)
        box.addWidget(self.btn_selecionar_questoes, alignment=Qt.AlignLeft)
        self.lbl_arquivo = _texto("Nenhum arquivo selecionado", "file-status")
        box.addWidget(self.lbl_arquivo)
        self.lbl_perfil_caderno = _texto("Perfil do caderno: ainda não reconhecido.", "section-hint")
        box.addWidget(self.lbl_perfil_caderno)
        self.perfil_caderno_combo = QComboBox()
        self.perfil_caderno_combo.setObjectName("proof-profile-choice")
        self.perfil_caderno_combo.hide()
        box.addWidget(self.perfil_caderno_combo)
        self.btn_reprocessar_caderno = QPushButton("Reprocessar com o perfil selecionado")
        self.btn_reprocessar_caderno.setObjectName("secondary-button")
        self.btn_reprocessar_caderno.clicked.connect(self._reprocessar_caderno)
        self.btn_reprocessar_caderno.hide()
        box.addWidget(self.btn_reprocessar_caderno, alignment=Qt.AlignLeft)
        self.btn_paginas_caderno = QPushButton("Conferir leitura por página…")
        self.btn_paginas_caderno.clicked.connect(lambda: self._conferir_paginas("caderno"))
        box.addWidget(self.btn_paginas_caderno, alignment=Qt.AlignLeft)
        box.addWidget(_texto("01  Escolha o arquivo\n\n02  Associe as respostas por cargo e tipo\n\n03  Confira as pendências e salve", "import-guide"))
        box.addStretch()

    def _gabarito_step(self):
        box = self._scroll_step("2  Gabarito")
        box.addWidget(_texto("Encontre a resposta certa para cada questão.", "section-title"))
        box.addWidget(_texto("Leia o PDF para ver os cargos, códigos e versões reconhecidos. Se houver várias opções, selecione o escopo do seu caderno e releia o gabarito."))
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.cargo_gabarito_input = ScopeChoice()
        self.cargo_gabarito_input.setPlaceholderText("Ex.: Analista de Sistemas")
        self.codigo_gabarito_input = ScopeChoice()
        self.codigo_gabarito_input.setPlaceholderText("Ex.: T1; ou códigos Cebraspe separados por ;")
        self.codigo_gabarito_input.setToolTip("Para reunir os blocos básico e específico, informe os dois códigos exatos separados por ponto e vírgula.")
        form.addRow("Cargo no gabarito", self.cargo_gabarito_input)
        form.addRow("Tipo ou código da prova", self.codigo_gabarito_input)
        self.versao_gabarito_input = ScopeChoice()
        self.versao_gabarito_input.setPlaceholderText("Selecione a versão reconhecida, quando houver")
        form.addRow("Versão do caderno", self.versao_gabarito_input)
        box.addLayout(form)
        self.btn_selecionar_gabarito = QPushButton("Ler gabarito em PDF")
        self.btn_selecionar_gabarito.clicked.connect(self.selecionar_gabarito)
        box.addWidget(self.btn_selecionar_gabarito, alignment=Qt.AlignLeft)
        self.lbl_perfil_gabarito = _texto("Perfil do gabarito: ainda não reconhecido.", "section-hint")
        box.addWidget(self.lbl_perfil_gabarito)
        self.perfil_gabarito_combo = QComboBox()
        self.perfil_gabarito_combo.setObjectName("answer-profile-choice")
        self.perfil_gabarito_combo.hide()
        box.addWidget(self.perfil_gabarito_combo)
        self.btn_reprocessar_gabarito = QPushButton("Reler páginas com o perfil selecionado")
        self.btn_reprocessar_gabarito.setObjectName("secondary-button")
        self.btn_reprocessar_gabarito.clicked.connect(self._reprocessar_gabarito)
        self.btn_reprocessar_gabarito.hide()
        box.addWidget(self.btn_reprocessar_gabarito, alignment=Qt.AlignLeft)
        self.btn_paginas_gabarito = QPushButton("Conferir leitura por página…")
        self.btn_paginas_gabarito.clicked.connect(lambda: self._conferir_paginas("gabarito"))
        box.addWidget(self.btn_paginas_gabarito, alignment=Qt.AlignLeft)
        self.lbl_associacao = _texto("A associação documental será exibida após a leitura dos dois arquivos.", "section-hint")
        box.addWidget(self.lbl_associacao)
        box.addWidget(_texto("Ou cole a sequência completa", "section-title"))
        box.addWidget(_texto("Uma resposta por número oficial, da questão 1 até a última. Para cadernos com lacunas ou numeração repetida, use o PDF ou revise individualmente."))
        self.gabarito_lote_input = QLineEdit()
        self.gabarito_lote_input.setPlaceholderText("A B C D E … ou CERTO ERRADO …")
        box.addWidget(self.gabarito_lote_input)
        self.btn_aplicar_gabarito = QPushButton("Aplicar sequência")
        self.btn_aplicar_gabarito.setObjectName("secondary-button")
        self.btn_aplicar_gabarito.clicked.connect(self.aplicar_gabarito_lote)
        box.addWidget(self.btn_aplicar_gabarito, alignment=Qt.AlignLeft)
        box.addStretch()

    def _revisao_step(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(8)
        self.nova_versao_checkbox = QCheckBox("Criar nova versão se este par já existir com conteúdo diferente")
        self.nova_versao_checkbox.setToolTip(
            "Por padrão, PDFs já importados com o mesmo conteúdo reutilizam a prova existente. "
            "Marque esta opção para versionar as questões quando você corrigiu o conteúdo extraído."
        )
        box.addWidget(self.nova_versao_checkbox)
        self.classificar_btn = QPushButton("Classificar intervalo…")
        self.classificar_btn.setObjectName("secondary-button")
        self.classificar_btn.clicked.connect(self._classificar_dialog)
        box.addWidget(self.classificar_btn, alignment=Qt.AlignRight)
        self.instrucoes_toggle = QPushButton("Instruções gerais da prova · ver ou adicionar")
        self.instrucoes_toggle.setObjectName("secondary-button")
        self.instrucoes_toggle.setCheckable(True)
        self.instrucoes_toggle.toggled.connect(self._alternar_instrucoes)
        self.instrucoes_toggle.hide()
        box.addWidget(self.instrucoes_toggle, alignment=Qt.AlignLeft)
        self.instrucoes_editor = QTextEdit()
        self.instrucoes_editor.setObjectName("exam-instructions-review")
        self.instrucoes_editor.setAcceptRichText(False)
        self.instrucoes_editor.setPlaceholderText("Informações compartilhadas da prova, separadas das questões.")
        self.instrucoes_editor.setMinimumHeight(80)
        self.instrucoes_editor.setMaximumHeight(150)
        self.instrucoes_editor.textChanged.connect(self._editar_instrucoes)
        self.instrucoes_editor.hide()
        box.addWidget(self.instrucoes_editor)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        left = QWidget()
        left.setMinimumWidth(165)
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        self.filtro = QComboBox()
        for nome, valor in [("Todas as questões", "todas"), ("Não salvas", "pendentes"), ("Sem gabarito", "sem_gabarito"), ("Salvas", "salvas")]:
            self.filtro.addItem(nome, valor)
        self.filtro.currentIndexChanged.connect(self._refresh_list)
        left_box.addWidget(self.filtro)
        self.lista_questoes = QListWidget()
        self.lista_questoes.setObjectName("import-review-list")
        self.lista_questoes.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lista_questoes.currentItemChanged.connect(self.carregar_edicao)
        left_box.addWidget(self.lista_questoes, 1)
        self.splitter.addWidget(left)
        right = QWidget()
        right.setMinimumWidth(250)
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        self.lbl_confianca = _texto("Selecione uma questão para revisar.", "section-hint")
        right_box.addWidget(self.lbl_confianca)
        self.editor = QuestionEditor()
        self.painel_edicao = self.editor
        self.editor.changed.connect(self._editar_rascunho)
        right_box.addWidget(self.editor, 1)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([210, 540])
        box.addWidget(self.splitter, 1)
        self.steps.addTab(page, "3  Revisão")

    def _sync(self, *args):
        busy = self.ocupada
        tem = bool(self.session.questoes)
        pendentes = self.session.pendentes
        for index in (1, 2):
            self.steps.setTabEnabled(index, tem)
        self.steps.tabBar().setEnabled(not busy)
        self.instrucoes_toggle.setEnabled(not busy)
        # Instruções são salvas no cadastro da prova quando o lote é concluído.
        # Depois disso, deixá-las editáveis criaria uma revisão que não persiste.
        self.instrucoes_editor.setEnabled(not busy and bool(pendentes))
        self.filtro.setEnabled(not busy)
        self.lista_questoes.setEnabled(not busy)
        self.btn_selecionar_questoes.setEnabled(not busy)
        self.btn_selecionar_gabarito.setEnabled(not busy and bool(pendentes))
        self.perfil_caderno_combo.setEnabled(not busy and bool(self.session.caminho))
        self.btn_reprocessar_caderno.setEnabled(not busy and bool(self.session.caminho) and bool(self.perfil_caderno_combo.count()))
        self.perfil_gabarito_combo.setEnabled(not busy and bool(pendentes))
        self.btn_reprocessar_gabarito.setEnabled(not busy and bool(pendentes) and bool(self.caminho_gabarito))
        self.btn_paginas_caderno.setEnabled(not busy and bool(self._paginas_caderno) and not bool(self.session.salvas))
        self.btn_paginas_gabarito.setEnabled(not busy and bool(self._paginas_gabarito) and bool(pendentes))
        for field in (self.codigo_gabarito_input, self.cargo_gabarito_input, self.versao_gabarito_input):
            field.setEnabled(not busy and bool(pendentes))
        self.btn_aplicar_gabarito.setEnabled(not busy and bool(pendentes))
        self.classificar_btn.setEnabled(not busy and bool(pendentes))
        self.progress.setVisible(busy)
        step = self.steps.currentIndex()
        self.btn_anterior.setEnabled(step > 0 and not busy)
        self.btn_proxima.setVisible(step < 2)
        self.btn_proxima.setEnabled(tem and not busy)
        self.btn_proxima.setText("Revisar questões" if step == 1 else "Continuar")
        self.btn_salvar_todas.setVisible(step == 2)
        self.btn_salvar_questao.setVisible(step == 2)
        self.btn_salvar_todas.setEnabled(bool(pendentes) and not busy)
        self.btn_salvar_todas.setText(f"Salvar pendentes ({len(pendentes)})")
        editavel = self.current_index in pendentes and not busy
        self.editor.setEnabled(editavel)
        self.btn_salvar_questao.setEnabled(editavel)
        self.btn_cancelar.setVisible(busy)
        self.btn_cancelar.setEnabled(busy and not self.task.cancellation_requested)
        self.btn_cancelar.setText("Cancelando…" if self.task.cancellation_requested else "Cancelar operação")
        saved = bool(self._ultima_verificacao and self._ultima_verificacao.get("prova_id"))
        self.btn_abrir_prova.setVisible(saved)
        self.btn_gerar_simulado.setVisible(saved)
        self.btn_abrir_prova.setEnabled(not busy)
        self.btn_gerar_simulado.setEnabled(not busy)
        if tem:
            com_resposta = sum(bool(q.get("gabarito")) for q in self.session.questoes)
            expected = self._quantidade_esperada if self._quantidade_esperada is not None else "não informadas"
            resumo = f"Esperadas: {expected} · Extraídas: {len(self.session.questoes)} · Com resposta: {com_resposta} · Salvas: {len(self.session.salvas)}"
            if self._ultima_verificacao:
                result = self._ultima_verificacao
                resumo += f"\nÚltimo lote — verificadas: {result.get('verificadas', 0)} · Elegíveis: {result.get('certificadas', 0)} · Pendentes: {len(result.get('pendentes', []))}"
            self.resumo.setText(resumo)

    def _informar(self, texto, erro=False):
        self.feedback.setText(texto)
        self.feedback.setProperty("error", erro)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

    def _agendar_rascunho(self, *args):
        if not self._restoring_draft and self.session.caminho and not self.ocupada:
            self._draft_timer.start()

    def _dados_rascunho(self):
        return {
            "caminho_caderno": self.session.caminho,
            "caminho_gabarito": self.caminho_gabarito,
            "nome_prova": self.nome_prova_input.text(),
            "cargo_gabarito": self.cargo_gabarito_input.text(),
            "codigo_gabarito": self.codigo_gabarito_input.text(),
            "versao_gabarito": self.versao_gabarito_input.text(),
            "perfis_caderno_paginas": self._perfis_caderno_paginas,
            "perfis_gabarito_paginas": self._perfis_gabarito_paginas,
            "paginas_caderno": self._paginas_caderno,
            "paginas_gabarito": self._paginas_gabarito,
            "quantidade_esperada": self._quantidade_esperada,
            "questoes": self.session.questoes,
            "salvas": {str(index): int(question_id) for index, question_id in self.session.salvas.items()},
            "instrucoes_prova": self.session.instrucoes_prova,
            "indice_atual": self.current_index,
            "etapa": self.steps.currentIndex(),
            "perfil_caderno": self.perfil_caderno_combo.currentData() or "",
            "perfil_gabarito": self.perfil_gabarito_combo.currentData() or "",
            "criar_nova_versao": self.nova_versao_checkbox.isChecked(),
            "source_hashes": self._draft_source_hashes,
        }

    def _salvar_rascunho(self):
        if self._restoring_draft or not self.session.caminho:
            return True
        try:
            from src.models.importacao_rascunho import salvar_rascunho
            self._draft_source_hashes = salvar_rascunho(self._dados_rascunho())
            return True
        except Exception as error:
            logger.exception("Falha ao salvar rascunho de importação")
            self._informar(f"Não foi possível proteger o rascunho: {error}", True)
            return False

    def _restaurar_rascunho(self):
        from src.models.importacao_rascunho import (
            FonteRascunhoAlterada, carregar_rascunho,
        )
        try:
            data = carregar_rascunho()
        except FonteRascunhoAlterada as error:
            self._informar(f"O rascunho não foi retomado porque {error} Confira a fonte e reimporte o caderno.", True)
            return
        except ValueError as error:
            self._informar(str(error), True)
            return
        if not data:
            return
        self._restoring_draft = True
        try:
            self.session.questoes = data.get("questoes", [])
            self.session.salvas = {int(index): int(question_id)
                                   for index, question_id in data.get("salvas", {}).items()}
            self.session.caminho = data.get("caminho_caderno", "")
            self.session.instrucoes_prova = data.get("instrucoes_prova", "")
            self.session.restaurar_estado()
            self.caminho_gabarito = data.get("caminho_gabarito", "")
            self._draft_source_hashes = data.get("source_hashes", {})
            self.nome_prova_input.setText(data.get("nome_prova", ""))
            self.cargo_gabarito_input.setText(data.get("cargo_gabarito", ""))
            self.codigo_gabarito_input.setText(data.get("codigo_gabarito", ""))
            self.versao_gabarito_input.setText(data.get("versao_gabarito", ""))
            self._perfis_caderno_paginas = {int(n): v for n, v in data.get("perfis_caderno_paginas", {}).items()}
            self._perfis_gabarito_paginas = {int(n): v for n, v in data.get("perfis_gabarito_paginas", {}).items()}
            self._paginas_caderno = data.get("paginas_caderno", [])
            self._paginas_gabarito = data.get("paginas_gabarito", [])
            self._quantidade_esperada = data.get("quantidade_esperada")
            self.nova_versao_checkbox.setChecked(bool(data.get("criar_nova_versao", False)))
            self.lbl_arquivo.setText(Path(self.session.caminho).name)
            self.lbl_arquivo.setToolTip(self.session.caminho)
            self.instrucoes_editor.blockSignals(True)
            self.instrucoes_editor.setPlainText(self.session.instrucoes_prova)
            self.instrucoes_editor.blockSignals(False)
            self.instrucoes_toggle.show()
            self.perfil_caderno_combo.clear()
            if data.get("perfil_caderno"):
                self.perfil_caderno_combo.addItem(self._nome_perfil(data["perfil_caderno"]), data["perfil_caderno"])
                self.lbl_perfil_caderno.setText(f"Rascunho recuperado · {self._nome_perfil(data['perfil_caderno'])}")
            self.perfil_gabarito_combo.clear()
            if data.get("perfil_gabarito"):
                self.perfil_gabarito_combo.addItem(self._nome_perfil(data["perfil_gabarito"]), data["perfil_gabarito"])
                self.lbl_perfil_gabarito.setText("Perfil salvo no rascunho; releia o gabarito para atualizar o diagnóstico.")
            self.lbl_associacao.setText("Confira cargo e tipo antes de aplicar o gabarito recuperado.")
            self.current_index = data.get("indice_atual")
            self._refresh_list()
            self.steps.setCurrentIndex(min(max(int(data.get("etapa", 2)), 0), 2))
            self._informar("Rascunho recuperado. As fontes foram conferidas e permanecem disponíveis.")
        finally:
            self._restoring_draft = False
        self._sync()

    def selecionar_arquivo(self):
        if self.ocupada:
            return
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar caderno", "", "Provas (*.pdf *.docx)")
        if not caminho:
            return
        if self.session.pendentes and QMessageBox.question(self, "Substituir a revisão?", "O lote atual contém questões não salvas. Deseja substituí-lo?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.caminho_questoes_pendente = caminho
        self.operation = "questoes"
        self._start(lambda: importar_caderno(caminho), "Lendo o caderno. Você pode continuar usando as outras telas.")

    def _nome_perfil(self, perfil_id):
        perfil = obter_perfil(perfil_id)
        return perfil.descricao if perfil else perfil_id.replace("_", " ")

    def _entrada_catalogo_caderno(self, caminho):
        from pathlib import Path
        sample_root = (ROOT_DIR / "samples").resolve()
        book = Path(caminho).resolve()
        if not book.is_relative_to(sample_root):
            return None, None
        try:
            key = normalizar_chave(book.relative_to(sample_root).as_posix())
            entry = carregar_catalogo(ROOT_DIR / "config" / "gabaritos.json").get(key)
        except (OSError, ValueError, KeyError):
            return None, None
        if not entry or entry.get("confirmado") is not True:
            return None, None
        return key, entry

    def _reprocessar_caderno(self):
        if self.ocupada or not self.session.caminho or not self.perfil_caderno_combo.count():
            return
        if self.session.salvas:
            self._informar("O perfil não pode ser reprocessado depois que parte do lote foi salva. Retome a revisão do mesmo lote.", True)
            return
        perfil = self.perfil_caderno_combo.currentData()
        escolhas = dict(self._perfis_caderno_paginas)
        self.caminho_questoes_pendente = self.session.caminho
        self.operation = "questoes"
        self._start(lambda: importar_caderno(self.session.caminho, perfil_escolhido=perfil, perfis_paginas=escolhas),
                    "Reprocessando o caderno pelo perfil selecionado.")

    def _reprocessar_gabarito(self):
        if self.ocupada or not self.caminho_gabarito or not self.session.pendentes:
            return
        cargo = self.cargo_gabarito_input.text().strip() or None
        codigo = self.codigo_gabarito_input.text().strip() or None
        numeros = {numero for q in self.session.questoes
                   for numero, motivo in [numero_oficial_explicitamente_extraido(q)] if numero is not None}
        perfil = self.perfil_gabarito_combo.currentData()
        reconhecidos = {page["perfil"] for page in self._paginas_gabarito}
        if len(reconhecidos) > 1 or perfil not in reconhecidos:
            perfil = None
        escolhas = dict(self._perfis_gabarito_paginas)
        versao = self.versao_gabarito_input.text().strip() or None
        caminho = self.caminho_gabarito
        self.operation = "gabarito"
        self._start(lambda: extrair_gabaritos_pdf(caminho, codigo, cargo,
            numeros_esperados=numeros, perfil_escolhido=perfil, perfis_paginas=escolhas, versao=versao),
            "Relendo o gabarito pelas páginas compatíveis com o perfil selecionado.")

    def selecionar_gabarito(self):
        if self.ocupada or not self.session.pendentes:
            return
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar gabarito", "", "Gabaritos (*.pdf)")
        if not caminho:
            return
        cargo = self.cargo_gabarito_input.text().strip() or None
        codigo = self.codigo_gabarito_input.text().strip() or None
        versao = self.versao_gabarito_input.text().strip() or None
        numeros = {numero for q in self.session.questoes
                   for numero, motivo in [numero_oficial_explicitamente_extraido(q)]
                   if numero is not None}
        if self.caminho_gabarito and Path(self.caminho_gabarito).resolve() != Path(caminho).resolve():
            self._draft_source_hashes.pop("gabarito", None)
            self._perfis_gabarito_paginas = {}
        self.caminho_gabarito = caminho
        self.operation = "gabarito"
        self._start(lambda: extrair_gabaritos_pdf(caminho, codigo, cargo, numeros_esperados=numeros, versao=versao), "Lendo o gabarito. PDFs escaneados podem levar mais tempo.")

    def _conferir_paginas(self, papel):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        paginas = self._paginas_caderno if papel == "caderno" else self._paginas_gabarito
        escolhas = self._perfis_caderno_paginas if papel == "caderno" else self._perfis_gabarito_paginas
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Leitura por página — {papel}")
        dialog.resize(860, 480)
        layout = QVBoxLayout(dialog)
        layout.addWidget(_texto("Confira cada página. A escolha de leitura mantém as validações da fonte; páginas sem texto precisam de OCR ou conferência manual."))
        table = PageProfileChoices(paginas, papel, escolhas, dialog)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        if papel == "caderno":
            self._perfis_caderno_paginas = table.selections()
            self._reprocessar_caderno()
        else:
            self._perfis_gabarito_paginas = table.selections()
            self._reprocessar_gabarito()

    def _start(self, function, mensagem):
        self.session.estado = EstadoImportacao.LENDO
        self._informar(mensagem)
        from src.importador.lote_verificado import ImportacaoCancelada
        def cancellable(cancel_event):
            if cancel_event.is_set():
                raise ImportacaoCancelada("Importação cancelada com segurança.")
            result = function()
            if cancel_event.is_set():
                raise ImportacaoCancelada("Importação cancelada com segurança.")
            return result
        self.task.start(cancellable, cancellable=True)
        self._sync()

    def _cancelar_operacao(self):
        if self.task.cancel():
            self._informar("Cancelamento solicitado. A leitura atual será encerrada com segurança antes de atualizar a revisão.")
            self._sync()

    @Slot()
    def _task_idle(self):
        self._sync()
        if self.operation == "questoes" and self.session.questoes:
            self.steps.setCurrentIndex(1)
        self.operation = None

    @Slot(object)
    def _resultado(self, resultado):
        if self.operation == "questoes":
            self._finalizar_importacao_questoes(resultado)
        elif self.operation == "salvar":
            self._finalizar_salvamento(resultado)
        else:
            self._finalizar_importacao_gabarito(resultado)

    @Slot(str)
    def _falha(self, erro):
        self.caminho_questoes_pendente = ""
        self.session.restaurar_estado()
        cancelada = "Importação cancelada com segurança." in erro
        duplicada_divergente = "fonte_ja_importada_com_conteudo_diferente" in erro
        mensagem = ("Operação cancelada. A revisão anterior foi preservada." if cancelada else
                    "Este par já foi importado com conteúdo diferente. Confira a edição e marque a opção de nova versão antes de salvar novamente."
                    if duplicada_divergente else
                    f"Não foi possível ler o arquivo. A revisão anterior foi preservada. {erro}")
        self._informar(mensagem, not cancelada)
        self._sync()

    @Slot(object)
    def _finalizar_importacao_questoes(self, questoes):
        caminho = self.caminho_questoes_pendente
        self.caminho_questoes_pendente = ""
        previous_path = Path(self.session.caminho).resolve() if self.session.caminho else None
        new_path = Path(caminho).resolve() if caminho else None
        chave_catalogo, entrada_catalogo = self._entrada_catalogo_caderno(caminho)
        if not self.nome_prova_input.text().strip():
            self.nome_prova_input.setText(Path(caminho).stem)
        if not questoes and self.session.questoes:
            self.session.restaurar_estado()
            self._informar("Nenhuma questão foi reconhecida. A revisão anterior foi preservada; tente outro arquivo.", True)
        else:
            self.reconhecimento_caderno = getattr(questoes, "perfil_documento", None)
            if previous_path != new_path:
                self.caminho_gabarito = ""
                self.reconhecimento_gabarito = None
                self.perfil_gabarito_combo.clear()
                self._draft_source_hashes = {}
                self.cargo_gabarito_input.clear()
                self.codigo_gabarito_input.clear()
                self.versao_gabarito_input.clear()
                self._perfis_caderno_paginas = {}
                self._perfis_gabarito_paginas = {}
                self._paginas_gabarito = []
                self.nova_versao_checkbox.setChecked(False)
            if entrada_catalogo:
                if not self.cargo_gabarito_input.text().strip():
                    self.cargo_gabarito_input.setText(entrada_catalogo.get("cargo", ""))
                if not self.codigo_gabarito_input.text().strip():
                    self.codigo_gabarito_input.setText(entrada_catalogo.get("codigo") or entrada_catalogo.get("prova", ""))
                if chave_catalogo:
                    self.lbl_associacao.setText(
                        f"Par catalogado e confirmado para este caderno ({chave_catalogo}). Confira o escopo antes de aplicar o gabarito."
                    )
            self.session.carregar(questoes, caminho)
            self._loading_instrucoes = True
            self.instrucoes_editor.blockSignals(True)
            self.instrucoes_editor.setPlainText(self.session.instrucoes_prova)
            self.instrucoes_editor.blockSignals(False)
            self._loading_instrucoes = False
            self.instrucoes_toggle.setChecked(False)
            self.instrucoes_toggle.show()
            self.current_index = None
            self.lbl_arquivo.setText(Path(caminho).name)
            self.lbl_arquivo.setToolTip(caminho)
            self._refresh_list()
            perfis = sorted({q.get("perfil_importacao", "não informado") for q in questoes})
            avisos = sorted(set(getattr(questoes, "avisos", ())) | {q["aviso_importacao"] for q in questoes if q.get("aviso_importacao")})
            self.lbl_arquivo.setToolTip(caminho + "\nPerfis: " + ", ".join(perfis))
            relatorio = getattr(questoes, "relatorio", {})
            self._quantidade_esperada = relatorio.get("declarada")
            self._ultima_verificacao = None
            self._paginas_caderno = relatorio.get("leitura_paginas", [])
            reconhecimento = relatorio.get("reconhecimento", {}) if isinstance(relatorio, dict) else {}
            estado = reconhecimento.get("estado", "nao_suportado")
            perfil_atual = reconhecimento.get("perfil_usado") or reconhecimento.get("perfil") or "desconhecido"
            candidatos = list(dict.fromkeys([perfil_atual, *reconhecimento.get("candidatos", [])]))
            if estado != "reconhecido":
                from src.importador.perfis.registro import listar_perfis
                candidatos = list(dict.fromkeys([*candidatos, *(item.id for item in listar_perfis("caderno"))]))
            self.perfil_caderno_combo.clear()
            for perfil_id in candidatos:
                self.perfil_caderno_combo.addItem(self._nome_perfil(perfil_id), perfil_id)
            self.perfil_caderno_combo.setCurrentIndex(max(0, self.perfil_caderno_combo.findData(perfil_atual)))
            self.perfil_caderno_combo.setVisible(len(candidatos) > 1 or estado != "reconhecido")
            self.btn_reprocessar_caderno.setVisible(not self.perfil_caderno_combo.isHidden())
            aviso = reconhecimento.get("aviso") or ""
            self.lbl_perfil_caderno.setText(
                f"Reconhecimento {estado}: {self._nome_perfil(perfil_atual)}. "
                f"{len(candidatos)} opção(ões) de perfil avaliadas. {aviso}".strip()
            )
            self._informar("Caderno carregado. Associe um gabarito ou siga para a revisão." if questoes else "Nenhuma questão reconhecida. Tente outro PDF ou DOCX.", not bool(questoes))
            if avisos:
                self._informar(" ".join(avisos), True)
        self._sync()
        # Durante uma tarefa real os controles são liberados apenas em idle.
        self._agendar_rascunho()

    @Slot(object)
    def _finalizar_importacao_gabarito(self, gabaritos):
        self.session.restaurar_estado()
        self.reconhecimento_gabarito = getattr(gabaritos, "perfil_documento", None)
        paginas = getattr(gabaritos, "perfis_paginas", [])
        self._paginas_gabarito = paginas
        if self.reconhecimento_gabarito:
            perfil_atual = self.reconhecimento_gabarito.padrao
            perfis_paginas = list(dict.fromkeys(item["perfil"] for item in paginas))
            candidatos = list(dict.fromkeys([perfil_atual, *perfis_paginas]))
            self.perfil_gabarito_combo.clear()
            self.perfil_gabarito_combo.addItem("Reconhecer por página", "")
            for perfil_id in candidatos:
                self.perfil_gabarito_combo.addItem(self._nome_perfil(perfil_id), perfil_id)
            escolhido = getattr(gabaritos, "perfil_escolhido", None) or ""
            self.perfil_gabarito_combo.setCurrentIndex(max(0, self.perfil_gabarito_combo.findData(escolhido)))
            misto = len(perfis_paginas) > 1
            # Uma única escolha global poderia eliminar silenciosamente as
            # páginas de outro layout. Documentos mistos permanecem roteados
            # pelo perfil reconhecido em cada página.
            self.perfil_gabarito_combo.setVisible(len(candidatos) > 1 and not misto)
            self.btn_reprocessar_gabarito.setVisible(True)
            self.btn_reprocessar_gabarito.setText("Reler com o escopo e as leituras escolhidas")
            descricao = ", ".join(self._nome_perfil(perfil) for perfil in perfis_paginas)
            estado = f"Layouts mistos por página: {descricao}" if misto else f"Reconhecimento: {self._nome_perfil(perfil_atual)}"
            self.lbl_perfil_gabarito.setText(f"{estado} · {len(paginas)} página(s) com texto avaliadas.")
            if self.reconhecimento_gabarito.situacao == 'preliminar':
                self.lbl_perfil_gabarito.setText(self.lbl_perfil_gabarito.text() + ' · Gabarito preliminar: liberação automática bloqueada.')
            self._atualizar_associacao(gabaritos)
            metadata = self.reconhecimento_gabarito.metadados or {}
            for name, field in (("cargo", self.cargo_gabarito_input), ("codigo", self.codigo_gabarito_input), ("versao", self.versao_gabarito_input)):
                field.set_options(metadata.get(name, ()))
            problem = self._conferir_escopo(gabaritos)
            if problem:
                self._informar(problem, True)
                self._sync()
                self._agendar_rascunho()
                return
        if not gabaritos:
            self._informar(" ".join(getattr(gabaritos, "avisos", ())) or "Nenhuma resposta reconhecida para a seleção. Confira cargo/tipo, cole a sequência ou revise individualmente.", True)
        else:
            resultado = self.session.associar(gabaritos)
            avisos_fonte = getattr(gabaritos, "avisos", [])
            self._informar(f"{resultado['extraidos']} respostas lidas; {resultado['vinculados']} vinculadas. Pendências: {len(resultado['faltantes'])} sem resposta válida, {len(resultado.get('incompativeis', []))} incompatíveis, {len(resultado['duplicados'])} duplicados e {len(resultado['conflitos'])} conflitos.")
            if avisos_fonte:
                self._informar(" ".join(avisos_fonte), True)
            if self.reconhecimento_gabarito and self.reconhecimento_gabarito.situacao == 'preliminar':
                self._informar(self.feedback.text() + ' Gabarito preliminar: as questões permanecerão pendentes para resolução com nota.', True)
            self._refresh_list()
        self._sync()
        self._agendar_rascunho()

    def _conferir_escopo(self, gabaritos):
        from src.importador.perfis.documentos import _normalizar, normalizar_versao, versao_da_selecao
        metadata = self.reconhecimento_gabarito.metadados or {}
        book = (self.reconhecimento_caderno.metadados or {}) if self.reconhecimento_caderno else {}
        choices = getattr(gabaritos, "selecao_escopo", {})
        for key, label in (("cargo", "cargo"), ("codigo", "código"), ("versao", "versão")):
            options = metadata.get(key, ())
            selected = choices.get(key, "")
            if key == "versao" and not selected:
                code = choices.get("codigo", "")
                selected = versao_da_selecao(code)
            if len(options) > 1 and not selected:
                return f"O gabarito contém várias opções de {label}. Selecione {label} na lista e clique em reler antes de vincular respostas."
            normalize = normalizar_versao if key == "versao" else _normalizar
            if selected and book.get(key) and normalize(selected) not in {normalize(value) for value in book[key]}:
                # Códigos CEBRASPE compostos representam a seleção explícita de mais de um bloco.
                if key == "codigo" and ";" in selected and all(normalize(value.strip()) in {normalize(v) for v in book[key]} for value in selected.split(";")):
                    continue
                if key == "codigo" and versao_da_selecao(selected) in book.get("versao", ()):
                    continue
                return f"O {label} selecionado diverge do caderno. Confira as opções reconhecidas e releia o gabarito."
        return ""

    def _evidencia_catalogo(self):
        if not self.session.caminho or not self.caminho_gabarito:
            return ""
        from pathlib import Path
        sample_root = (ROOT_DIR / "samples").resolve()
        book = Path(self.session.caminho).resolve()
        answer = Path(self.caminho_gabarito).resolve()
        key, entry = self._entrada_catalogo_caderno(str(book))
        if not key or not entry:
            return ""
        answer_paths = [sample_root / entry["gabarito"]]
        if entry.get("complemento"):
            answer_paths.append(sample_root / entry["complemento"])
        if answer in {path.resolve() for path in answer_paths}:
            return f"config/gabaritos.json:{key}"
        return ""

    def _atualizar_associacao(self, gabaritos):
        if not self.reconhecimento_caderno or not self.reconhecimento_gabarito:
            return
        numerados = {numero for q in self.session.questoes
                     for numero, motivo in [numero_oficial_explicitamente_extraido(q)] if numero is not None}
        resultado = associar_documentos(
            self.reconhecimento_caderno, self.reconhecimento_gabarito,
            numeros_caderno=numerados, respostas=gabaritos,
            codigo=self.codigo_gabarito_input.text().strip(),
            cargo=self.cargo_gabarito_input.text().strip(),
            evidencia_catalogo=self._evidencia_catalogo(),
        )
        self.lbl_associacao.setText(
            f"Associação: {resultado['estado']} · {resultado['motivo']} "
            f"{len(resultado['faltantes'])} sem resposta, {len(resultado['extras'])} extra(s), "
            f"{len(resultado['conflitos'])} conflito(s)."
        )

    def aplicar_gabarito_lote(self):
        if self.ocupada or not self.session.pendentes:
            return
        tokens = parsear_gabarito_em_lote(self.gabarito_lote_input.text())
        numeracoes = [numero_oficial_explicitamente_extraido(q)[0] for q in self.session.questoes]
        if (None in numeracoes or len(set(numeracoes)) != len(numeracoes)
                or sorted(numeracoes) != list(range(1, len(tokens) + 1))
                or len(tokens) != len(numeracoes)):
            self._informar("A sequência precisa cobrir os números oficiais de 1 até o final, sem lacunas ou duplicidades. Use o PDF ou revise individualmente.", True)
            return
        self._finalizar_importacao_gabarito(dict(enumerate(tokens, 1)))

    def _refresh_list(self, *args):
        previous = self.current_index
        self.lista_questoes.blockSignals(True)
        self.lista_questoes.clear()
        selected = None
        filtro = self.filtro.currentData()
        for i, q in enumerate(self.session.questoes):
            saved = i in self.session.salvas
            if (filtro == "pendentes" and saved) or (filtro == "salvas" and not saved) or (filtro == "sem_gabarito" and (q.get("gabarito") or saved)):
                continue
            item = QListWidgetItem(self._item_text(i))
            item.setData(Qt.UserRole, i)
            item.setToolTip("\n\n".join(filter(None, [q.get("aviso_importacao"), q.get("enunciado", "")])))
            self.lista_questoes.addItem(item)
            if i == previous:
                selected = item
        if selected is None and self.lista_questoes.count():
            selected = self.lista_questoes.item(0)
        self.lista_questoes.setCurrentItem(selected)
        self.lista_questoes.blockSignals(False)
        self.carregar_edicao(selected)

    def _item_text(self, indice):
        q = self.session.questoes[indice]
        status = "Salva" if indice in self.session.salvas else (q.get("gabarito") or "Sem gabarito")
        resumo = " ".join(q.get("enunciado", "").split())
        numero, motivo = numero_oficial_explicitamente_extraido(q)
        rotulo = f"Questão {numero}" if numero is not None else f"Item visual {indice + 1} · número pendente"
        return f"{rotulo}  ·  {status}\n{resumo[:27]}{'…' if len(resumo) > 27 else ''}"

    def carregar_edicao(self, item, previous=None):
        self.current_index = item.data(Qt.UserRole) if item else None
        if item:
            q = self.session.questoes[self.current_index]
            self.editor.load(q)
            self.lbl_confianca.setText("Salva no acervo · edite na tela Questões" if self.current_index in self.session.salvas else
                                      f"{self._item_text(self.current_index).splitlines()[0]} · {'Confira o texto extraído' if q.get('confianca') != 'alta' else 'Revise enunciado e alternativas'}")
        else:
            self.editor.load({})
            self.lbl_confianca.setText("Nenhuma questão neste filtro.")
        self._sync()
        self._agendar_rascunho()

    def _editar_rascunho(self):
        if self.current_index in self.session.pendentes:
            self.session.editar(self.current_index, self.editor.data())
            item = self.lista_questoes.currentItem()
            if item:
                item.setText(self._item_text(self.current_index))
            self._sync()
            self._agendar_rascunho()

    def salvar_questao(self):
        if self.current_index in self.session.pendentes:
            self._salvar([self.current_index])

    def salvar_todas(self):
        self._salvar(self.session.pendentes)

    def _cadastrar_prova_se_completa(self):
        if self.session.pendentes:
            return None
        dados = []
        for indice, questao in enumerate(self.session.questoes):
            item = dict(questao)
            item["_questao_id"] = self.session.salvas[indice]
            dados.append(item)
        return repo.criar_prova_cadastrada(
            self.nome_prova_input.text().strip(),
            dados,
            arquivo_questoes=self.session.caminho,
            arquivo_gabarito=self.caminho_gabarito,
            instrucoes_prova=self.session.instrucoes_prova,
        )

    def _alternar_instrucoes(self, expandido):
        self.instrucoes_editor.setVisible(expandido)

    def _editar_instrucoes(self):
        if not self._loading_instrucoes:
            self.session.instrucoes_prova = self.instrucoes_editor.toPlainText().strip()
            self._agendar_rascunho()

    def _salvar(self, indices):
        if self.ocupada or not indices:
            return
        for i in indices:
            try:
                validar_questao(self.session.questoes[i])
            except ValueError as exc:
                self.current_index = i
                self.filtro.setCurrentIndex(0)
                self._refresh_list()
                numero, _ = numero_oficial_explicitamente_extraido(self.session.questoes[i])
                self._informar(f"Questão {numero if numero is not None else f'na posição visual {i + 1}'}: {exc}", True)
                return
        sem = sum(not self.session.questoes[i].get("gabarito") for i in indices)
        if sem and QMessageBox.question(self, "Salvar sem gabarito?", f"{sem} questão(ões) ficarão disponíveis para revisão, mas não entrarão em novas provas até receberem um gabarito. Salvar?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.session.estado = EstadoImportacao.SALVANDO
        self._sync()
        questoes = [self.session.questoes[i] for i in indices]
        perfis = sorted({q.get("perfil_extracao", "texto") for q in questoes})
        perfil_importacao = sorted({q.get("perfil_importacao", "não informado") for q in questoes})
        diagnosticos = [
            {"numero": q.get("numero"), "avisos": q.get("aviso_importacao", "")}
            for q in questoes if q.get("aviso_importacao")
        ]
        metadata = {
            "extractor": "importacao_dois_funis_v1",
            "profile": perfil_importacao[0] if len(perfil_importacao) == 1 else "roteamento_paginas_v1",
            "parameters": {"perfis_importacao": perfil_importacao,
                "perfis_extracao": perfis,
                "perfis_caderno_paginas": dict(self._perfis_caderno_paginas),
                "perfis_gabarito_paginas": dict(self._perfis_gabarito_paginas)},
            "diagnostics": diagnosticos,
        }
        self._indices_salvamento = list(indices)
        perfil = self.perfil_caderno_combo.currentData() or ""
        self.operation = "salvar"
        from copy import deepcopy
        lote = deepcopy(questoes)
        caminho_caderno = self.session.caminho
        caminho_gabarito = self.caminho_gabarito or None
        nome = self.nome_prova_input.text().strip()
        instrucoes = self.session.instrucoes_prova
        codigo = self.codigo_gabarito_input.text().strip()
        cargo = self.cargo_gabarito_input.text().strip()
        versao = self.versao_gabarito_input.text().strip()
        nova_versao = self.nova_versao_checkbox.isChecked()
        prova = None
        if set(indices) == set(self.session.pendentes):
            prova = {
                "nome": nome,
                "instrucoes_prova": instrucoes,
                "lote_indices": list(indices),
                "composicao": [
                    {"dados": dict(question), "questao_id": self.session.salvas.get(index),
                     "lote_index": index if index in indices else None}
                    for index, question in enumerate(self.session.questoes)
                ],
            }
        from src.importador.lote_verificado import salvar_lote_verificado
        self.task.start(lambda cancel_event: salvar_lote_verificado(
            lote, caminho_caderno=caminho_caderno, caminho_gabarito=caminho_gabarito,
            nome_prova=nome, instrucoes_prova=instrucoes, perfil_caderno=perfil,
            codigo_gabarito=codigo, cargo_gabarito=cargo, versao_gabarito=versao, extraction_metadata=metadata,
            prova=prova, cancel_event=cancel_event,
            allow_new_version=nova_versao,
        ), cancellable=True)
        self._informar("Conferindo as duas fontes e salvando o lote. Os itens sem evidência completa continuarão pendentes.")
        self._sync()

    def _finalizar_salvamento(self, resultado):
        try:
            ids = resultado["ids"]
            self.session.marcar_salvas(self._indices_salvamento, ids)
            prova_id = resultado.get("prova_id")
        except Exception:
            logger.exception("Falha ao concluir o lote salvo")
            self.session.restaurar_estado()
            self._informar("O lote foi salvo, mas não foi possível concluir o cadastro da prova. A revisão permanece recuperável.", True)
        else:
            self._ultima_verificacao = resultado
            pendentes = len(resultado.get("pendentes", []))
            if resultado.get("retomada_parcial"):
                mensagem = (
                    f"Lote parcial retomado: {resultado.get('reutilizadas', 0)} questão(ões) reutilizadas. "
                    f"{resultado.get('certificadas', 0)} elegíveis e {pendentes} pendentes para revisão."
                )
                if resultado.get("nova_versao"):
                    mensagem += " As correções foram salvas em nova versão."
            elif resultado.get("reutilizada"):
                mensagem = (
                    f"Este par já estava importado: a prova existente (ID {prova_id}) foi reutilizada; "
                    f"{resultado.get('certificadas', 0)} questões liberadas e {pendentes} pendentes para revisão."
                )
            elif resultado.get("nova_versao"):
                mensagem = (
                    f"Nova versão criada para {len(ids)} questão(ões) da prova; "
                    f"{resultado.get('certificadas', 0)} liberadas e {pendentes} pendentes para revisão."
                )
            else:
                mensagem = (
                f"{len(ids)} questão(ões) adicionadas ao acervo. "
                f"{resultado.get('certificadas', 0)} liberadas pela conferência documental; "
                f"{pendentes} permanecem para revisão."
                )
            if prova_id and not resultado.get("reutilizada"):
                mensagem += f" Prova cadastrada com sucesso (ID {prova_id})."
            self._informar(mensagem)
        self._indices_salvamento = []
        if self.session.pendentes:
            self._agendar_rascunho()
        else:
            from src.models.importacao_rascunho import remover_rascunho
            remover_rascunho()
            self._draft_source_hashes = {}
        self._refresh_list()
        self._sync()

    def _classificar_dialog(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle("Classificar por número oficial")
        dialog.resize(390, 340)
        form = QFormLayout(dialog)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        inicio, fim = QSpinBox(), QSpinBox()
        numeros = [numero for q in self.session.questoes
                   for numero, motivo in [numero_oficial_explicitamente_extraido(q)]
                   if numero is not None]
        if not numeros:
            self._informar("Nenhuma questão possui número oficial extraído; a classificação por intervalo está indisponível.", True)
            return
        for widget in (inicio, fim):
            widget.setRange(min(numeros), max(numeros))
        fim.setValue(max(numeros))
        disciplina, topico = QLineEdit(), QLineEdit()
        for label, widget in [("Da questão", inicio), ("Até a questão", fim), ("Disciplina", disciplina), ("Assunto", topico)]:
            form.addRow(label, widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Aplicar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.rejected.connect(dialog.reject)
        def aplicar():
            try:
                qtd = self.session.classificar(inicio.value(), fim.value(), disciplina.text(), topico.text())
            except ValueError as exc:
                QMessageBox.warning(dialog, "Revise o intervalo", str(exc))
                return
            self._refresh_list()
            self._informar(f"{qtd} questão(ões) não salvas classificadas pelo número oficial.")
            dialog.accept()
        buttons.accepted.connect(aplicar)
        form.addRow(buttons)
        dialog.exec()
