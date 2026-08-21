import logging
import os
import re

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QComboBox, QHeaderView, QLineEdit, QMessageBox, QProgressDialog, QScrollArea, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

import src.models.questoes_repo as repo
from src.importador.extrator import extrair_gabaritos_pdf, extrair_texto
from src.importador.parser import parsear_questoes

logger = logging.getLogger(__name__)


class GabaritoWorker(QObject):
    # O resultado é um dicionário Python. object evita que o Shiboken tente
    # convertê-lo para um tipo C++ ao atravessar a thread.
    concluido = Signal(object)
    falhou = Signal(str)

    def __init__(self, caminho, codigo):
        super().__init__(); self.caminho = caminho; self.codigo = codigo

    @Slot()
    def executar(self):
        try:
            self.concluido.emit(extrair_gabaritos_pdf(self.caminho, self.codigo))
        except Exception as exc:
            logger.exception("Erro ao extrair gabarito em segundo plano")
            self.falhou.emit(str(exc))


class ImportacaoPage(QWidget):
    def __init__(self):
        super().__init__(); layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); top = QHBoxLayout()
        self.lbl_arquivo = QLabel("Nenhum arquivo selecionado"); btn = QPushButton("Selecionar Questões (PDF/DOCX)"); btn.clicked.connect(self.selecionar_arquivo)
        btn_gabarito = QPushButton("Selecionar Gabarito (PDF)"); btn_gabarito.clicked.connect(self.selecionar_gabarito)
        top.addWidget(btn); top.addWidget(btn_gabarito); top.addWidget(self.lbl_arquivo); top.addStretch(); layout.addLayout(top)
        gabarito_lote = QHBoxLayout(); self.gabarito_lote_input = QLineEdit(); self.gabarito_lote_input.setPlaceholderText("Cole o gabarito inteiro: A D B C ..."); aplicar_gabarito = QPushButton("Aplicar Gabarito em Lote"); aplicar_gabarito.clicked.connect(self.aplicar_gabarito_lote); gabarito_lote.addWidget(self.gabarito_lote_input); gabarito_lote.addWidget(aplicar_gabarito); layout.addLayout(gabarito_lote)
        main = QHBoxLayout(); self.lista_questoes = QListWidget(); self.lista_questoes.setObjectName("import-list"); self.lista_questoes.setFixedWidth(300); self.lista_questoes.itemClicked.connect(self.carregar_edicao); main.addWidget(self.lista_questoes)
        self.painel_edicao = QWidget(); self.painel_edicao.setDisabled(True); form = QFormLayout(self.painel_edicao)
        self.lbl_confianca = QLabel(); form.addRow("Confiança da Extração:", self.lbl_confianca)
        self.enunciado_input = QTextEdit(); form.addRow("Enunciado:", self.enunciado_input)
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
        self.banca_input = QComboBox(); self.banca_input.setEditable(True); form.addRow("Banca:", self.banca_input)
        self.ano_input = QLineEdit(); form.addRow("Ano:", self.ano_input)
        self.gabarito_input = QComboBox(); self.gabarito_input.addItems(["A", "B", "C", "D", "E", "Certo", "Errado"]); form.addRow("Gabarito (Obrigatório):", self.gabarito_input)
        salvar = QPushButton("Salvar Questão Revisada"); salvar.clicked.connect(self.salvar_questao); form.addRow(salvar)
        salvar_todas = QPushButton("Salvar Todas as Questões"); salvar_todas.clicked.connect(self.salvar_todas); form.addRow(salvar_todas)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.painel_edicao); main.addWidget(scroll); layout.addLayout(main)
        self.questoes_extraidas = []; self.item_atual = None; self.caminho_questoes = ""; self.gabarito_thread = None; self.gabarito_worker = None; self.gabarito_progresso = None

    def selecionar_arquivo(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar Prova", "", "Arquivos (*.pdf *.docx)")
        if not caminho: return
        self.lbl_arquivo.setText(os.path.basename(caminho)); self.lista_questoes.clear(); self.painel_edicao.setDisabled(True); self.caminho_questoes = caminho
        try:
            self.questoes_extraidas = parsear_questoes(extrair_texto(caminho))
            if self.questoes_extraidas:
                primeira = self.questoes_extraidas[0]
                self.disciplina_input.setCurrentText(primeira.get("disciplina", ""))
                self.banca_input.setCurrentText(primeira.get("banca", ""))
                if primeira.get("ano"):
                    self.ano_input.setText(str(primeira["ano"]))
            logger.info("Arquivo importado: %s (%s questões)", caminho, len(self.questoes_extraidas))
            if not self.questoes_extraidas:
                QMessageBox.warning(self, "Aviso", "Nenhuma questão detectada pelo parser heurístico."); return
            for i, q in enumerate(self.questoes_extraidas):
                gabarito = f" - {q['gabarito']}" if q.get("gabarito") else ""
                item = QListWidgetItem(f"Q{i + 1} [{q['confianca'].upper()}]{gabarito} - {' '.join(q['enunciado'].split()[:6])}..."); item.setData(Qt.UserRole, i); self.lista_questoes.addItem(item)
        except Exception:
            logger.exception("Erro ao processar arquivo %s", caminho)
            QMessageBox.critical(self, "Erro", "Erro ao processar arquivo. Consulte data/app.log para detalhes.")

    def selecionar_gabarito(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar Gabarito", "", "Arquivos (*.pdf)")
        if not caminho:
            return
        if not self.questoes_extraidas:
            QMessageBox.warning(self, "Aviso", "Selecione primeiro o PDF das questões.")
            return
        nome_questoes = os.path.basename(self.caminho_questoes).lower()
        codigo = re.search(r"(dpf\d+[_-]\d+)", nome_questoes, re.IGNORECASE)
        if not codigo:
            # Alguns editais usam o nome do cargo no arquivo, enquanto o
            # gabarito reúne vários cargos. Use o código do cargo conhecido.
            codigos_por_nome = {
                "analista_de_informatica": "401",
                "analista": "401",
                "tecnico_de_informatica": "203",
                "auxiliar_administrativo": "200",
                "contador": "402",
                "advogado": "400",
            }
            codigo_cargo = next((valor for chave, valor in codigos_por_nome.items() if chave in nome_questoes), None)
        else:
            codigo_cargo = codigo.group(1)
        self.gabarito_progresso = QProgressDialog("Lendo o gabarito...", None, 0, 0, self)
        self.gabarito_progresso.setWindowTitle("Importação do gabarito")
        self.gabarito_progresso.setWindowModality(Qt.WindowModal)
        self.gabarito_progresso.setMinimumDuration(0)
        self.gabarito_progresso.show()
        self.gabarito_thread = QThread(self)
        self.caminho_gabarito = caminho
        self.gabarito_worker = GabaritoWorker(caminho, codigo_cargo)
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
        for numero, q in enumerate(self.questoes_extraidas, 1):
            if numero in gabaritos:
                q["gabarito"] = gabaritos[numero]
                item = self.lista_questoes.item(numero - 1)
                item.setText(f"Q{numero} [{q['confianca'].upper()}] - {q['gabarito']} - {' '.join(q['enunciado'].split()[:6])}...")
        self.lbl_arquivo.setText(f"{self.lbl_arquivo.text()} | gabarito: {os.path.basename(self.caminho_gabarito)}")
        if self.item_atual:
            self.carregar_edicao(self.item_atual)
        mensagem = f"{len(gabaritos)} gabaritos reconhecidos e vinculados."
        if len(gabaritos) < len(self.questoes_extraidas):
            mensagem += " Alguns campos ficaram pendentes para conferência no lote."
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
        tokens = re.findall(r"(?:CERTO|ERRADO|C|E|[A-E])", self.gabarito_lote_input.text().upper())
        if len(tokens) != len(self.questoes_extraidas):
            QMessageBox.warning(self, "Quantidade diferente", f"Foram encontradas {len(tokens)} respostas para {len(self.questoes_extraidas)} questões.")
            return
        for numero, (q, token) in enumerate(zip(self.questoes_extraidas, tokens), 1):
            q["gabarito"] = {"C": "Certo", "E": "Errado", "CERTO": "Certo", "ERRADO": "Errado"}.get(token, token)
            item = self.lista_questoes.item(numero - 1)
            item.setText(f"Q{numero} [{q['confianca'].upper()}] - {q['gabarito']} - {' '.join(q['enunciado'].split()[:6])}...")
        if self.item_atual:
            self.carregar_edicao(self.item_atual)
        QMessageBox.information(self, "Sucesso", f"{len(tokens)} gabaritos aplicados em lote.")

    def carregar_edicao(self, item):
        self.item_atual = item; q = self.questoes_extraidas[item.data(Qt.UserRole)]; self.painel_edicao.setDisabled(False); self.lbl_confianca.setText(f"<b>{q['confianca'].upper()}</b>")
        self.lbl_confianca.setStyleSheet("color: green;" if q["confianca"] == "alta" else "color: orange;"); texto = q["enunciado"]
        self.enunciado_input.setText(texto); self.tipo_combo.setCurrentText(q["tipo"])
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
        dados = {"enunciado": self.enunciado_input.toPlainText(), "tipo": self.tipo_combo.currentText(), "alternativas": alternativas, "disciplina": self.disciplina_input.currentText(), "topico": "", "banca": self.banca_input.currentText(), "ano": int(self.ano_input.text()) if self.ano_input.text().isdigit() else None, "dificuldade": "media", "gabarito": self.gabarito_input.currentText()}
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
            for q in self.questoes_extraidas:
                dados = {"enunciado": q["enunciado"], "tipo": q["tipo"], "alternativas": q.get("alternativas") or [], "disciplina": q.get("disciplina") or self.disciplina_input.currentText(), "topico": "", "banca": q.get("banca") or self.banca_input.currentText(), "ano": q.get("ano") or (int(self.ano_input.text()) if self.ano_input.text().isdigit() else None), "dificuldade": "media", "gabarito": q.get("gabarito")}
                repo.criar_questao(dados)
            self.lista_questoes.clear(); self.questoes_extraidas = []; self.painel_edicao.setDisabled(True)
            QMessageBox.information(self, "Sucesso", "Todas as questões foram salvas no banco!")
        except Exception:
            logger.exception("Erro ao salvar questões importadas em lote")
            QMessageBox.critical(self, "Erro", "Erro ao salvar em lote. Consulte data/app.log para detalhes.")
