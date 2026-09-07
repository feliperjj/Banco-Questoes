"""Fluxo de importação: arquivo, associação e revisão com rascunhos estáveis."""
import logging
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QComboBox, QScrollArea, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from src.importador.extrator import extrair_gabaritos_pdf, extrair_texto
from src.importador.lote import parsear_gabarito_em_lote
from src.importador.servico import importar_caderno
from src.models import questoes_repo as repo
from src.models.importacao_session import EstadoImportacao, ImportacaoSession, validar_questao
from src.ui.background import BackgroundTask
from src.ui.components.question_editor import QuestionEditor

logger = logging.getLogger(__name__)


def _texto(texto, nome="section-hint"):
    label = QLabel(texto)
    label.setObjectName(nome)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    label.setTextFormat(Qt.PlainText)
    return label


class ImportacaoPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("import-page")
        self.session = ImportacaoSession()
        self.current_index = None
        self.caminho_questoes_pendente = ""
        self.caminho_gabarito = ""
        self.operation = None
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
        footer.addWidget(self.btn_anterior)
        footer.addStretch()
        footer.addWidget(self.btn_salvar_questao)
        footer.addWidget(self.btn_salvar_todas)
        footer.addWidget(self.btn_proxima)
        layout.addLayout(footer)
        self.steps.currentChanged.connect(self._sync)
        self._sync()

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
        self.btn_selecionar_questoes = QPushButton("Escolher PDF ou DOCX")
        self.btn_selecionar_questoes.setMinimumHeight(44)
        self.btn_selecionar_questoes.clicked.connect(self.selecionar_arquivo)
        box.addWidget(self.btn_selecionar_questoes, alignment=Qt.AlignLeft)
        self.lbl_arquivo = _texto("Nenhum arquivo selecionado", "file-status")
        box.addWidget(self.lbl_arquivo)
        box.addWidget(_texto("01  Escolha o arquivo\n\n02  Associe as respostas por cargo e tipo\n\n03  Confira as pendências e salve", "import-guide"))
        box.addStretch()

    def _gabarito_step(self):
        box = self._scroll_step("2  Gabarito")
        box.addWidget(_texto("Encontre a resposta certa para cada questão.", "section-title"))
        box.addWidget(_texto("Para PDFs com vários cargos, informe o nome exato e o tipo de prova. Essa etapa é opcional: questões sem gabarito podem ser revisadas depois."))
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.cargo_gabarito_input = QLineEdit()
        self.cargo_gabarito_input.setPlaceholderText("Ex.: Analista de Sistemas")
        self.codigo_gabarito_input = QLineEdit()
        self.codigo_gabarito_input.setPlaceholderText("Ex.: T1; ou códigos Cebraspe separados por ;")
        self.codigo_gabarito_input.setToolTip("Para reunir os blocos básico e específico, informe os dois códigos exatos separados por ponto e vírgula.")
        form.addRow("Cargo no gabarito", self.cargo_gabarito_input)
        form.addRow("Tipo ou código da prova", self.codigo_gabarito_input)
        box.addLayout(form)
        self.btn_selecionar_gabarito = QPushButton("Ler gabarito em PDF")
        self.btn_selecionar_gabarito.clicked.connect(self.selecionar_gabarito)
        box.addWidget(self.btn_selecionar_gabarito, alignment=Qt.AlignLeft)
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
        self.classificar_btn = QPushButton("Classificar intervalo…")
        self.classificar_btn.setObjectName("secondary-button")
        self.classificar_btn.clicked.connect(self._classificar_dialog)
        box.addWidget(self.classificar_btn, alignment=Qt.AlignRight)
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
        self.filtro.setEnabled(not busy)
        self.lista_questoes.setEnabled(not busy)
        self.btn_selecionar_questoes.setEnabled(not busy)
        self.btn_selecionar_gabarito.setEnabled(not busy and bool(pendentes))
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
        if tem:
            sem = sum(not self.session.questoes[i].get("gabarito") for i in pendentes)
            self.resumo.setText(f"{len(self.session.questoes)} questões   ·   {len(self.session.salvas)} salvas   ·   {sem} pendentes sem gabarito")

    def _informar(self, texto, erro=False):
        self.feedback.setText(texto)
        self.feedback.setProperty("error", erro)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

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

    def selecionar_gabarito(self):
        if self.ocupada or not self.session.pendentes:
            return
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar gabarito", "", "Gabaritos (*.pdf)")
        if not caminho:
            return
        cargo = self.cargo_gabarito_input.text().strip() or None
        codigo = self.codigo_gabarito_input.text().strip() or None
        numeros = {int(q.get("numero", i + 1)) for i, q in enumerate(self.session.questoes)}
        self.caminho_gabarito = caminho
        self.operation = "gabarito"
        self._start(lambda: extrair_gabaritos_pdf(caminho, codigo, cargo, numeros_esperados=numeros), "Lendo o gabarito. PDFs escaneados podem levar mais tempo.")

    def _start(self, function, mensagem):
        self.session.estado = EstadoImportacao.LENDO
        self._informar(mensagem)
        self.task.start(function)
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
        else:
            self._finalizar_importacao_gabarito(resultado)

    @Slot(str)
    def _falha(self, erro):
        self.caminho_questoes_pendente = ""
        self.session.restaurar_estado()
        self._informar(f"Não foi possível ler o arquivo. A revisão anterior foi preservada. {erro}", True)
        self._sync()

    @Slot(object)
    def _finalizar_importacao_questoes(self, questoes):
        caminho = self.caminho_questoes_pendente
        self.caminho_questoes_pendente = ""
        if not questoes and self.session.questoes:
            self.session.restaurar_estado()
            self._informar("Nenhuma questão foi reconhecida. A revisão anterior foi preservada; tente outro arquivo.", True)
        else:
            self.session.carregar(questoes, caminho)
            self.current_index = None
            self.lbl_arquivo.setText(Path(caminho).name)
            self.lbl_arquivo.setToolTip(caminho)
            self._refresh_list()
            perfis = sorted({q.get("perfil_importacao", "não informado") for q in questoes})
            avisos = sorted(set(getattr(questoes, "avisos", ())) | {q["aviso_importacao"] for q in questoes if q.get("aviso_importacao")})
            self.lbl_arquivo.setToolTip(caminho + "\nPerfis: " + ", ".join(perfis))
            self._informar("Caderno carregado. Associe um gabarito ou siga para a revisão." if questoes else "Nenhuma questão reconhecida. Tente outro PDF ou DOCX.", not bool(questoes))
            if avisos:
                self._informar(" ".join(avisos), True)
        self._sync()
        # Durante uma tarefa real os controles são liberados apenas em idle.

    @Slot(object)
    def _finalizar_importacao_gabarito(self, gabaritos):
        self.session.restaurar_estado()
        if not gabaritos:
            self._informar(" ".join(getattr(gabaritos, "avisos", ())) or "Nenhuma resposta reconhecida para a seleção. Confira cargo/tipo, cole a sequência ou revise individualmente.", True)
        else:
            resultado = self.session.associar(gabaritos)
            avisos_fonte = getattr(gabaritos, "avisos", [])
            self._informar(f"{resultado['extraidos']} respostas lidas. Pendências: {len(resultado['faltantes'])} números ausentes, {len(resultado['duplicados'])} duplicados e {len(resultado['conflitos'])} conflitos.")
            if avisos_fonte:
                self._informar(" ".join(avisos_fonte), True)
            self._refresh_list()
        self._sync()

    def aplicar_gabarito_lote(self):
        if self.ocupada or not self.session.pendentes:
            return
        tokens = parsear_gabarito_em_lote(self.gabarito_lote_input.text())
        numeros = [int(q.get("numero", i + 1)) for i, q in enumerate(self.session.questoes)]
        if len(tokens) != len(numeros) or sorted(numeros) != list(range(1, len(tokens) + 1)):
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
        return f"Questão {q.get('numero', indice + 1)}  ·  {status}\n{resumo[:27]}{'…' if len(resumo) > 27 else ''}"

    def carregar_edicao(self, item, previous=None):
        self.current_index = item.data(Qt.UserRole) if item else None
        if item:
            q = self.session.questoes[self.current_index]
            self.editor.load(q)
            self.lbl_confianca.setText("Salva no acervo · edite na tela Questões" if self.current_index in self.session.salvas else
                                      f"Questão {q.get('numero', self.current_index + 1)} · {'Confira o texto extraído' if q.get('confianca') != 'alta' else 'Revise enunciado e alternativas'}")
        else:
            self.editor.load({})
            self.lbl_confianca.setText("Nenhuma questão neste filtro.")
        self._sync()

    def _editar_rascunho(self):
        if self.current_index in self.session.pendentes:
            self.session.editar(self.current_index, self.editor.data())
            item = self.lista_questoes.currentItem()
            if item:
                item.setText(self._item_text(self.current_index))
            self._sync()

    def salvar_questao(self):
        if self.current_index in self.session.pendentes:
            self._salvar([self.current_index])

    def salvar_todas(self):
        self._salvar(self.session.pendentes)

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
                self._informar(f"Questão {self.session.questoes[i].get('numero', i + 1)}: {exc}", True)
                return
        sem = sum(not self.session.questoes[i].get("gabarito") for i in indices)
        if sem and QMessageBox.question(self, "Salvar sem gabarito?", f"{sem} questão(ões) ficarão disponíveis para revisão, mas não entrarão em novas provas até receberem um gabarito. Salvar?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.session.estado = EstadoImportacao.SALVANDO
        self._sync()
        try:
            ids = repo.criar_questoes_em_lote([self.session.questoes[i] for i in indices])
            self.session.marcar_salvas(indices, ids)
        except Exception:
            logger.exception("Falha ao salvar lote revisado")
            self.session.restaurar_estado()
            self._informar("Não foi possível salvar. Os rascunhos foram preservados; tente novamente.", True)
        else:
            self._informar(f"{len(ids)} questão(ões) adicionadas ao acervo. Os itens salvos não serão importados novamente neste lote.")
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
        numeros = [int(q.get("numero", i + 1)) for i, q in enumerate(self.session.questoes)]
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
