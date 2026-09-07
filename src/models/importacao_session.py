"""Estado de revisão independente de Qt e de persistência."""
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum

from src.importador.validacao import associar_gabaritos


class EstadoImportacao(Enum):
    VAZIO = "vazio"
    LENDO = "lendo"
    REVISAO = "revisao"
    SALVANDO = "salvando"
    CONCLUIDO = "concluido"


def validar_questao(dados):
    if not str(dados.get("enunciado") or "").strip():
        raise ValueError("Preencha o enunciado antes de salvar.")
    tipo = dados.get("tipo")
    if tipo not in {"multipla_escolha", "certo_errado"}:
        raise ValueError("Selecione o tipo da questão.")
    resposta = dados.get("gabarito") or None
    permitidas = set("ABCDE") if tipo == "multipla_escolha" else {"Certo", "Errado"}
    if resposta not in permitidas | {None, "Anulada"}:
        raise ValueError("Escolha um gabarito compatível com o tipo da questão.")
    if tipo == "multipla_escolha":
        alternativas = dados.get("alternativas") or []
        letras = [a.get("letra") for a in alternativas if str(a.get("texto") or "").strip()]
        if len(letras) < 2:
            raise ValueError("Preencha pelo menos duas alternativas.")
        if len(letras) != len(set(letras)) or not set(letras) <= set("ABCDE"):
            raise ValueError("Use letras distintas de A a E nas alternativas.")
        if resposta in permitidas and resposta not in letras:
            raise ValueError("Preencha a alternativa indicada pelo gabarito.")
    ano = dados.get("ano")
    if ano not in (None, ""):
        if not str(ano).isdigit() or not 1900 <= int(ano) <= 2100:
            raise ValueError("Informe um ano entre 1900 e 2100 ou deixe em branco.")


@dataclass
class ImportacaoSession:
    questoes: list[dict] = field(default_factory=list)
    salvas: dict[int, int] = field(default_factory=dict)
    caminho: str = ""
    estado: EstadoImportacao = EstadoImportacao.VAZIO

    @property
    def pendentes(self):
        return [i for i in range(len(self.questoes)) if i not in self.salvas]

    def carregar(self, questoes, caminho):
        self.questoes = deepcopy(questoes)
        self.salvas.clear()
        self.caminho = caminho
        self.restaurar_estado()

    def restaurar_estado(self):
        self.estado = (EstadoImportacao.VAZIO if not self.questoes else
                       EstadoImportacao.REVISAO if self.pendentes else EstadoImportacao.CONCLUIDO)

    def editar(self, indice, dados):
        if indice in self.salvas:
            raise ValueError("Esta questão já foi salva. Edite-a no banco de questões.")
        self.questoes[indice].update(deepcopy(dados))

    def marcar_salvas(self, indices, ids):
        if len(indices) != len(ids):
            raise ValueError("A quantidade salva não corresponde à seleção.")
        self.salvas.update(zip(indices, ids))
        self.restaurar_estado()

    def associar(self, gabaritos):
        # A lista completa mantém a detecção de números duplicados; itens
        # salvos são congelados e não recebem alterações silenciosas.
        copia = deepcopy(self.questoes)
        resultado = associar_gabaritos(copia, gabaritos)
        for i in self.pendentes:
            self.questoes[i] = copia[i]
        return resultado

    def classificar(self, inicio, fim, disciplina, topico):
        if inicio > fim or not disciplina.strip():
            raise ValueError("Informe uma disciplina e um intervalo válido.")
        indices = [i for i in self.pendentes if inicio <= int(self.questoes[i].get("numero", i + 1)) <= fim]
        for i in indices:
            self.questoes[i].update(disciplina=disciplina.strip(), topico=topico.strip())
        return len(indices)
