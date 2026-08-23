import logging
import os
import re

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QComboBox, QHeaderView, QLineEdit, QMessageBox, QProgressDialog, QScrollArea, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

import src.models.questoes_repo as repo
from src.importador.extrator import extrair_gabaritos_pdf, extrair_texto
from src.importador.lote import aplicar_classificacao_as_questoes, aplicar_gabarito_as_questoes, parsear_gabarito_em_lote
from src.importador.parser import parsear_questoes
from src.importador.validacao import associar_gabaritos

logger = logging.getLogger(__name__)


class GabaritoWorker(QObject):
    # O resultado é um dicionário Python. object evita que o Shiboken tente
    # convertê-lo para um tipo C++ ao atravessar a thread.
    concluido = Signal(object)
    falhou = Signal(str)

    def __init__(self, caminho, codigo, cargo=None, numeros_esperados=None):
        super().__init__(); self.caminho = caminho; self.codigo = codigo; self.cargo = cargo; self.numeros_esperados = numeros_esperados

    @Slot()
    def executar(self):
        try:
            self.concluido.emit(extrair_gabaritos_pdf(
                self.caminho, self.codigo, self.cargo, numeros_esperados=self.numeros_esperados,
            ))
        except Exception as exc:
            logger.exception("Erro ao extrair gabarito em segundo plano")
            self.falhou.emit(str(exc))


class QuestoesWorker(QObject):
    concluido = Signal(object)
    falhou = Signal(str)

    def __init__(self, caminho):
        super().__init__(); self.caminho = caminho

    @Slot()
    def executar(self):
        try:
            self.concluido.emit(parsear_questoes(extrair_texto(self.caminho), self.caminho))
        except Exception as exc:
            logger.exception("Erro ao extrair questões em segundo plano")
            self.falhou.emit(str(exc))


class ImportacaoPage(QWidget):
    def __init__(self):
        super().__init__(); layout = QVBoxLayout(self); layout.setContentsMargins(30, 26, 30, 26); layout.setSpacing(10)
        titulo = QLabel("Importar questões"); titulo.setObjectName("page-title"); layout.addWidget(titulo)
        subtitulo = QLabel("Extraia questões, associe gabaritos e revise os dados antes de salvar."); subtitulo.setObjectName("page-subtitle"); layout.addWidget(subtitulo)
        top = QHBoxLayout(); top.setSpacing(8)
        self.lbl_arquivo = QLabel("Nenhum arquivo selecionado"); self.btn_selecionar_questoes = QPushButton("Selecionar Questões (PDF/DOCX)"); self.btn_selecionar_questoes.clicked.connect(self.selecionar_arquivo)
        self.lbl_arquivo.setObjectName("file-status"); self.lbl_arquivo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.btn_selecionar_gabarito = QPushButton("Selecionar Gabarito (PDF)"); self.btn_selecionar_gabarito.setObjectName("secondary-button"); self.btn_selecionar_gabarito.clicked.connect(self.selecionar_gabarito)
        top.addWidget(self.btn_selecionar_questoes); top.addWidget(self.btn_selecionar_gabarito); top.addWidget(self.lbl_arquivo); top.addStretch(); layout.addLayout(top)
        seletor_gabarito = QHBoxLayout(); self.cargo_gabarito_input = QLineEdit(); self.cargo_gabarito_input.setPlaceholderText("Cargo exato no gabarito (opcional)"); self.codigo_gabarito_input = QLineEdit(); self.codigo_gabarito_input.setPlaceholderText("Código/prova exato (opcional)"); seletor_gabarito.addWidget(self.cargo_gabarito_input); seletor_gabarito.addWidget(self.codigo_gabarito_input); layout.addLayout(seletor_gabarito)
        gabarito_lote = QHBoxLayout(); self.gabarito_lote_input = QLineEdit(); self.gabarito_lote_input.setPlaceholderText("Cole o gabarito inteiro: A D B C ..."); aplicar_gabarito = QPushButton("Aplicar Gabarito em Lote"); aplicar_gabarito.clicked.connect(self.aplicar_gabarito_lote); gabarito_lote.addWidget(self.gabarito_lote_input); gabarito_lote.addWidget(aplicar_gabarito); layout.addLayout(gabarito_lote)
        classificacao = QGroupBox("Classificar questões em lote")
        classificacao_layout = QHBoxLayout(classificacao)
        self.classificacao_inicio = QSpinBox(); self.classificacao_inicio.setMinimum(1); self.classificacao_inicio.setPrefix("Da questão ")
        self.classificacao_fim = QSpinBox(); self.classificacao_fim.setMinimum(1); self.classificacao_fim.setPrefix("até ")
        self.disciplina_lote_input = QComboBox(); self.disciplina_lote_input.setEditable(True); self.disciplina_lote_input.addItems(["Língua Portuguesa", "Matemática", "Raciocínio Lógico", "Informática", "Conhecimentos Específicos"])
        self.categoria_lote_input = QLineEdit(); self.categoria_lote_input.setPlaceholderText("Categoria / assunto")
        aplicar_classificacao = QPushButton("Aplicar ao bloco"); aplicar_classificacao.clicked.connect(self.aplicar_classificacao_lote)
        classificacao_layout.addWidget(self.classificacao_inicio); classificacao_layout.addWidget(self.classificacao_fim); classificacao_layout.addWidget(self.disciplina_lote_input); classificacao_layout.addWidget(self.categoria_lote_input); classificacao_layout.addWidget(aplicar_classificacao); layout.addWidget(classificacao)
        revisao_titulo = QLabel("Revisão das questões extraídas"); revisao_titulo.setObjectName("section-title"); layout.addWidget(revisao_titulo)
        main = QHBoxLayout(); main.setSpacing(12); self.lista_questoes = QListWidget(); self.lista_questoes.setObjectName("import-list"); self.lista_questoes.setMinimumWidth(230); self.lista_questoes.setMaximumWidth(330); self.lista_questoes.itemClicked.connect(self.carregar_edicao); main.addWidget(self.lista_questoes, 1)
        self.painel_edicao = QWidget(); self.painel_edicao.setMinimumWidth(0); self.painel_edicao.setDisabled(True); form = QFormLayout(self.painel_edicao)
        form.setContentsMargins(16, 14, 16, 16); form.setSpacing(7); form.setRowWrapPolicy(QFormLayout.WrapAllRows); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.lbl_confianca = QLabel(); form.addRow("Confiança da Extração:", self.lbl_confianca)
        self.enunciado_input = QTextEdit(); self.enunciado_input.setMinimumHeight(100); form.addRow("Enunciado:", self.enunciado_input)
        self.tipo_combo = QComboBox(); self.tipo_combo.addItems(["multipla_escolha", "certo_errado"]); form.addRow("Tipo:", self.tipo_combo)
        self.alternativas_tabela = QTableWidget(5, 2)
        self.alternativas_tabela.setHorizontalHeaderLabels(["Letra", "Texto da opção"])
        self.alternativas_tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.alternativas_tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.alternativas_tabela.verticalHeader().setVisible(False)
        for linha, letra in enumerate("ABCDE"):
            self.alternativas_tabela.setItem(linha, 0, QTableWidgetItem(letra))
        form.addRow("Opções (se houver):", self.alternativas_tabela)
        self.disciplina_input = QComboBox(); self.disciplina_input.setEditable(True); form.addRow("Disciplina:", self.disciplina_input)
        self.topico_input = QLineEdit(); self.topico_input.setPlaceholderText("Ex.: Redes, Gramática, Banco de Dados..."); form.addRow("Categoria / Assunto:", self.topico_input)
        self.banca_input = QComboBox(); self.banca_input.setEditable(True); form.addRow("Banca:", self.banca_input)
        self.ano_input = QLineEdit(); form.addRow("Ano:", self.ano_input)
        self.gabarito_input = QComboBox(); self.gabarito_input.addItems(["A", "B", "C", "D", "E", "Certo", "Errado", "Anulada"]); form.addRow("Gabarito (Obrigatório):", self.gabarito_input)
        salvar = QPushButton("Salvar Questão Revisada"); salvar.clicked.connect(self.salvar_questao); form.addRow(salvar)
        salvar_todas = QPushButton("Salvar Todas as Questões"); salvar_todas.clicked.connect(self.salvar_todas); form.addRow(salvar_todas)
        scroll = QScrollArea(); scroll.setObjectName("import-editor-scroll"); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); scroll.setWidget(self.painel_edicao); main.addWidget(scroll, 3); layout.addLayout(main, 1)
        self.questoes_extraidas = []; self.item_atual = None; self.caminho_questoes = ""; self.caminho_questoes_pendente = ""; self.gabarito_thread = None; self.gabarito_worker = None; self.gabarito_progresso = None; self.questoes_thread = None; self.questoes_worker = None; self.questoes_progresso = None

    def selecionar_arquivo(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar Prova", "", "Arquivos (*.pdf *.docx)")
        if not caminho: return
        self.caminho_questoes_pendente = caminho
        self.btn_selecionar_questoes.setEnabled(False); self.btn_selecionar_gabarito.setEnabled(False)
        self.questoes_progresso = QProgressDialog("Lendo questões...", None, 0, 0, self); self.questoes_progresso.setWindowTitle("Importação"); self.questoes_progresso.setWindowModality(Qt.WindowModal); self.questoes_progresso.setMinimumDuration(0); self.questoes_progresso.show()
        self.questoes_thread = QThread(self); self.questoes_worker = QuestoesWorker(caminho); self.questoes_worker.moveToThread(self.questoes_thread)
        self.questoes_thread.started.connect(self.questoes_worker.executar); self.questoes_worker.concluido.connect(self._finalizar_importacao_questoes); self.questoes_worker.falhou.connect(self._falha_importacao_questoes)
        self.questoes_worker.concluido.connect(self.questoes_thread.quit); self.questoes_worker.falhou.connect(self.questoes_thread.quit); self.questoes_thread.finished.connect(self.questoes_worker.deleteLater); self.questoes_thread.finished.connect(self.questoes_thread.deleteLater); self.questoes_thread.start()

    @Slot(object)
    def _finalizar_importacao_questoes(self, questoes):
        if self.questoes_progresso: self.questoes_progresso.close(); self.questoes_progresso.deleteLater(); self.questoes_progresso = None
        caminho = self.caminho_questoes_pendente
        self.caminho_questoes = caminho
        self.caminho_questoes_pendente = ""
        self.lbl_arquivo.setText(os.path.basename(caminho))
        self.btn_selecionar_questoes.setEnabled(True); self.btn_selecionar_gabarito.setEnabled(True)
        self.lista_questoes.clear(); self.questoes_extraidas = questoes
        try:
            self.classificacao_inicio.setMaximum(max(1, len(self.questoes_extraidas)))
            self.classificacao_fim.setMaximum(max(1, len(self.questoes_extraidas)))
            self.classificacao_fim.setValue(max(1, len(self.questoes_extraidas)))
            if self.questoes_extraidas:
                primeira = self.questoes_extraidas[0]
                self.disciplina_input.setCurrentText(primeira.get("disciplina", ""))
                self.topico_input.setText(primeira.get("topico", ""))
                self.banca_input.setCurrentText(primeira.get("banca", ""))
                if primeira.get("ano"):
                    self.ano_input.setText(str(primeira["ano"]))
            logger.info("Arquivo importado: %s (%s questões)", caminho, len(self.questoes_extraidas))
            if not self.questoes_extraidas:
                QMessageBox.warning(self, "Aviso", "Nenhuma questão detectada pelo parser heurístico."); return
            for i, q in enumerate(self.questoes_extraidas):
                gabarito = f" - {q['gabarito']}" if q.get("gabarito") else ""
                numero = int(q.get("numero", i + 1))
                item = QListWidgetItem(f"Q{numero} [{q['confianca'].upper()}]{gabarito} - {' '.join(q['enunciado'].split()[:6])}..."); item.setData(Qt.UserRole, i); self.lista_questoes.addItem(item)
        except Exception:
            logger.exception("Erro ao processar arquivo %s", caminho)
            QMessageBox.critical(self, "Erro", "Erro ao processar arquivo. Consulte data/app.log para detalhes.")

    @Slot(str)
    def _falha_importacao_questoes(self, erro):
        if self.questoes_progresso: self.questoes_progresso.close(); self.questoes_progresso.deleteLater(); self.questoes_progresso = None
        self.caminho_questoes_pendente = ""
        self.btn_selecionar_questoes.setEnabled(True); self.btn_selecionar_gabarito.setEnabled(True)
        QMessageBox.critical(self, "Erro", f"Não foi possível processar o arquivo.\n\n{erro}")

    def selecionar_gabarito(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar Gabarito", "", "Arquivos (*.pdf)")
        if not caminho:
            return
        if not self.questoes_extraidas:
            QMessageBox.warning(self, "Aviso", "Selecione primeiro o PDF das questões.")
            return
        nome_questoes = os.path.basename(self.caminho_questoes).lower()
        codigo = re.search(r"(dpf\d+[_-]\d+)", nome_questoes, re.IGNORECASE)
        # Sem código explícito no nome não escolha um cargo por aproximação:
        # PDFs multiprovas precisam de seleção inequívoca ou revisão manual.
        codigo_cargo = self.codigo_gabarito_input.text().strip() or (codigo.group(1) if codigo else None)
        cargo = self.cargo_gabarito_input.text().strip() or None
        self.gabarito_progresso = QProgressDialog("Lendo o gabarito...", None, 0, 0, self)
        self.gabarito_progresso.setWindowTitle("Importação do gabarito")
        self.gabarito_progresso.setWindowModality(Qt.WindowModal)
        self.gabarito_progresso.setMinimumDuration(0)
        self.gabarito_progresso.show()
        self.gabarito_thread = QThread(self)
        self.caminho_gabarito = caminho
        numeros_esperados = {
            int(q.get("numero", indice)) for indice, q in enumerate(self.questoes_extraidas, 1)
        }
        self.gabarito_worker = GabaritoWorker(caminho, codigo_cargo, cargo, numeros_esperados)
        self.gabarito_worker.moveToThread(self.gabarito_thread)
        self.gabarito_thread.started.connect(self.gabarito_worker.executar)
        self.gabarito_worker.concluido.connect(self._finalizar_importacao_gabarito)
        self.gabarito_worker.falhou.connect(self._falha_importacao_gabarito)
        self.gabarito_worker.concluido.connect(self.gabarito_thread.quit)
        self.gabarito_worker.falhou.connect(self.gabarito_thread.quit)
        self.gabarito_thread.finished.connect(self.gabarito_worker.deleteLater)
        self.gabarito_thread.finished.connect(self.gabarito_thread.deleteLater)
        self.gabarito_thread.start()

    @Slot(object)
    def _finalizar_importacao_gabarito(self, gabaritos):
        if self.gabarito_progresso:
            self.gabarito_progresso.close(); self.gabarito_progresso.deleteLater(); self.gabarito_progresso = None
        if not gabaritos:
            QMessageBox.warning(self, "Gabarito escaneado", "Este PDF não possui texto selecionável. Cole a sequência de respostas no campo de gabarito em lote.")
            return
        associacao = associar_gabaritos(self.questoes_extraidas, gabaritos)
        for linha in range(self.lista_questoes.count()):
            item = self.lista_questoes.item(linha)
            indice = item.data(Qt.UserRole)
            q = self.questoes_extraidas[indice]
            numero = int(q.get("numero", indice + 1))
            if q.get("gabarito"):
                item.setText(f"Q{numero} [{q['confianca'].upper()}] - {q['gabarito']} - {' '.join(q['enunciado'].split()[:6])}...")
        self.lbl_arquivo.setText(f"{self.lbl_arquivo.text()} | gabarito: {os.path.basename(self.caminho_gabarito)}")
        if self.item_atual:
            self.carregar_edicao(self.item_atual)
        mensagem = f"Extraídos: {associacao['extraidos']} | vinculados: {associacao['vinculados']} | faltantes: {len(associacao['faltantes'])} | extras: {len(associacao['extras'])} | duplicados: {len(associacao['duplicados'])}."
        if associacao["revisao_manual"]: mensagem += " Revisão manual necessária."
        QMessageBox.information(self, "OCR concluído", mensagem)

    @Slot(str)
    def _falha_importacao_gabarito(self, erro):
        if self.gabarito_progresso:
            self.gabarito_progresso.close(); self.gabarito_progresso.deleteLater(); self.gabarito_progresso = None
        QMessageBox.critical(self, "Erro no OCR", f"Não foi possível ler o gabarito.\n\n{erro}")

    def aplicar_gabarito_lote(self):
        if not self.questoes_extraidas:
            QMessageBox.warning(self, "Aviso", "Selecione primeiro o PDF das questões.")
            return
        tokens = parsear_gabarito_em_lote(self.gabarito_lote_input.text())
        if len(tokens) != len(self.questoes_extraidas):
            QMessageBox.warning(self, "Quantidade diferente", f"Foram encontradas {len(tokens)} respostas para {len(self.questoes_extraidas)} questões.")
            return
        aplicar_gabarito_as_questoes(self.questoes_extraidas, tokens)
        for linha in range(self.lista_questoes.count()):
            item = self.lista_questoes.item(linha)
            indice = item.data(Qt.UserRole)
            numero = int(self.questoes_extraidas[indice].get("numero", indice + 1))
            q = self.questoes_extraidas[indice]
            item.setText(f"Q{numero} [{q['confianca'].upper()}] - {q['gabarito']} - {' '.join(q['enunciado'].split()[:6])}...")
        if self.item_atual:
            self.carregar_edicao(self.item_atual)
        QMessageBox.information(self, "Sucesso", f"{len(tokens)} gabaritos aplicados em lote.")

    def aplicar_classificacao_lote(self):
        if not self.questoes_extraidas:
            QMessageBox.warning(self, "Aviso", "Selecione primeiro o PDF das questões.")
            return
        inicio = self.classificacao_inicio.value()
        fim = self.classificacao_fim.value()
        disciplina = self.disciplina_lote_input.currentText().strip()
        categoria = self.categoria_lote_input.text().strip()
        if inicio > fim:
            QMessageBox.warning(self, "Faixa inválida", "A questão inicial não pode ser maior que a final.")
            return
        if not disciplina:
            QMessageBox.warning(self, "Disciplina obrigatória", "Informe a disciplina do bloco.")
            return
        quantidade = aplicar_classificacao_as_questoes(self.questoes_extraidas, inicio, fim, disciplina, categoria)
        for numero in range(inicio, min(fim, len(self.questoes_extraidas)) + 1):
            questao = self.questoes_extraidas[numero - 1]
            item = self.lista_questoes.item(numero - 1)
            if item:
                resumo = " ".join(questao["enunciado"].split()[:5])
                item.setText(f"Q{numero} [{questao['confianca'].upper()}] - {disciplina} - {resumo}...")
        self.disciplina_input.setCurrentText(disciplina)
        self.topico_input.setText(categoria)
        if self.item_atual:
            self.carregar_edicao(self.item_atual)
        QMessageBox.information(self, "Classificação aplicada", f"{quantidade} questão(ões) classificadas em lote.")

    def carregar_edicao(self, item):
        self.item_atual = item; q = self.questoes_extraidas[item.data(Qt.UserRole)]; self.painel_edicao.setDisabled(False); self.lbl_confianca.setText(f"<b>{q['confianca'].upper()}</b>")
        self.lbl_confianca.setStyleSheet("color: green;" if q["confianca"] == "alta" else "color: orange;"); texto = q["enunciado"]
        self.enunciado_input.setText(texto); self.tipo_combo.setCurrentText(q["tipo"])
        self.topico_input.setText(q.get("topico", ""))
        self.alternativas_tabela.setEnabled(q["tipo"] == "multipla_escolha")
        for linha in range(self.alternativas_tabela.rowCount()):
            item_letra = self.alternativas_tabela.item(linha, 0)
            item_texto = self.alternativas_tabela.item(linha, 1)
            if item_letra is None:
                item_letra = QTableWidgetItem("ABCDE"[linha]); self.alternativas_tabela.setItem(linha, 0, item_letra)
            item_letra.setText("ABCDE"[linha])
            item_letra.setFlags(item_letra.flags() & ~Qt.ItemIsEditable)
            texto_opcao = q.get("alternativas") or []
            valor = next((a["texto"] for a in texto_opcao if a["letra"].upper() == "ABCDE"[linha]), "")
            if item_texto is None:
                item_texto = QTableWidgetItem(); self.alternativas_tabela.setItem(linha, 1, item_texto)
            item_texto.setText(valor)
        self.gabarito_input.setCurrentText(q.get("gabarito") or ("Certo" if q["tipo"] == "certo_errado" else "A"))

    def salvar_questao(self):
        if not self.item_atual: return
        alternativas = []
        if self.tipo_combo.currentText() == "multipla_escolha":
            for linha in range(self.alternativas_tabela.rowCount()):
                texto = self.alternativas_tabela.item(linha, 1)
                if texto and texto.text().strip():
                    alternativas.append({"letra": "ABCDE"[linha], "texto": texto.text().strip()})
        dados = {"enunciado": self.enunciado_input.toPlainText(), "tipo": self.tipo_combo.currentText(), "alternativas": alternativas, "disciplina": self.disciplina_input.currentText(), "topico": self.topico_input.text().strip(), "banca": self.banca_input.currentText(), "ano": int(self.ano_input.text()) if self.ano_input.text().isdigit() else None, "dificuldade": "media", "gabarito": self.gabarito_input.currentText()}
        try:
            repo.criar_questao(dados); row = self.lista_questoes.row(self.item_atual); self.lista_questoes.takeItem(row); self.painel_edicao.setDisabled(True); self.item_atual = None; logger.info("Questão importada salva"); QMessageBox.information(self, "Sucesso", "Questão salva no banco!")
        except Exception:
            logger.exception("Erro ao salvar questão importada")
            QMessageBox.critical(self, "Erro", "Erro ao salvar. Consulte data/app.log para detalhes.")

    def salvar_todas(self):
        if not self.questoes_extraidas:
            return
        sem_gabarito = sum(1 for q in self.questoes_extraidas if not q.get("gabarito"))
        if sem_gabarito:
            resposta = QMessageBox.question(self, "Gabaritos ausentes", f"{sem_gabarito} questão(ões) estão sem gabarito. Salvar mesmo assim?", QMessageBox.Yes | QMessageBox.No)
            if resposta != QMessageBox.Yes:
                return
        try:
            questoes = []
            for q in self.questoes_extraidas:
                dados = {"enunciado": q["enunciado"], "tipo": q["tipo"], "alternativas": q.get("alternativas") or [], "disciplina": q.get("disciplina") or self.disciplina_input.currentText(), "topico": q.get("topico") or self.topico_input.text().strip(), "banca": q.get("banca") or self.banca_input.currentText(), "ano": q.get("ano") or (int(self.ano_input.text()) if self.ano_input.text().isdigit() else None), "dificuldade": "media", "gabarito": q.get("gabarito")}
                questoes.append(dados)
            repo.criar_questoes_em_lote(questoes)
            self.lista_questoes.clear(); self.questoes_extraidas = []; self.item_atual = None; self.painel_edicao.setDisabled(True)
            QMessageBox.information(self, "Sucesso", "Todas as questões foram salvas no banco!")
        except Exception:
            logger.exception("Erro ao salvar questões importadas em lote")
            QMessageBox.critical(self, "Erro", "Erro ao salvar em lote. Consulte data/app.log para detalhes.")
