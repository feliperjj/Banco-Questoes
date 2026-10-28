"""Registro explícito de perfis documentais usados pelos funis de importação."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PerfilRegistrado:
    id: str
    versao: str
    papel: str
    familia: str
    descricao: str
    assinatura: tuple[str, ...]
    limites: tuple[str, ...]


PERFIS = (
    PerfilRegistrado("questoes_nomeadas_v1", "1", "caderno", "multipla_escolha",
        "Questões com rótulos nomeados", ("QUESTÃO, ITEM ou Q seguido do número",),
        ("documentos com mais de um padrão precisam de conferência",)),
    PerfilRegistrado("questoes_nomeadas_v2", "2", "caderno", "multipla_escolha",
        "Questões com rótulos nomeados", ("QUESTÃO, ITEM ou Q seguido do número",),
        ("documentos com mais de um padrão precisam de conferência",)),
    PerfilRegistrado("multipla_escolha_numero_isolado_v2", "2", "caderno", "multipla_escolha",
        "Múltipla escolha com número em linha própria", ("número sozinho seguido pelo enunciado",),
        ("números sem alternativas locais não abrem questões",)),
    PerfilRegistrado("multipla_escolha_pontuada_v2", "2", "caderno", "multipla_escolha",
        "Múltipla escolha com número pontuado", ("número seguido de ponto ou parêntese",),
        ("enumerações internas não podem abrir questão",)),
    PerfilRegistrado("multipla_escolha_traco_v2", "2", "caderno", "multipla_escolha",
        "Múltipla escolha com marcador por traço", ("número seguido de traço",),
        ("números de referência exigem alternativas locais",)),
    PerfilRegistrado("multipla_escolha_dois_pontos_v2", "2", "caderno", "multipla_escolha",
        "Múltipla escolha com marcador por dois-pontos", ("número seguido de dois-pontos",),
        ("números de referência exigem alternativas locais",)),
    PerfilRegistrado("multipla_escolha_numero_espaco_v2", "2", "caderno", "multipla_escolha",
        "Múltipla escolha com número e enunciado na mesma linha", ("número seguido de espaço e enunciado",),
        ("números de referência exigem alternativas locais",)),
    PerfilRegistrado(
        "multipla_escolha_sequencia_isolada_v3", "3", "caderno", "multipla_escolha",
        "Múltipla escolha com marcadores numéricos isolados",
        ("número oficial em linha própria", "alternativas A–E no bloco da questão"),
        ("número sem âncora física suficiente fica pendente", "colunas e quebras de página exigem conferência"),
    ),
    PerfilRegistrado(
        "multipla_escolha_numerada_v1", "1", "caderno", "multipla_escolha",
        "Múltipla escolha com número e enunciado no mesmo bloco",
        ("marcador numérico reconhecido pelo segmentador geral", "alternativas no bloco local"),
        ("formatos com empate de limites permanecem ambíguos",),
    ),
    PerfilRegistrado(
        "certo_errado_contexto_v1", "1", "caderno", "certo_errado",
        "Certo ou errado com texto compartilhado",
        ("rótulo TEXTO DE APOIO", "rótulo ITEM PARA JULGAMENTO"),
        ("o texto de apoio só é compartilhado no intervalo ancorado",),
    ),
    PerfilRegistrado(
        "certo_errado_sequencial_v1", "1", "caderno", "certo_errado",
        "Certo ou errado com itens numerados em sequência",
        ("marcadores de itens CEBRASPE", "ausência de alternativas A–E"),
        ("páginas sem marcador legível precisam de conferência",),
    ),
    PerfilRegistrado("multipla_escolha_predominante_v2", "2", "caderno", "multipla_escolha",
        "Múltipla escolha por marcadores recorrentes", ("marcadores numéricos alinhados", "alternativas locais"),
        ("a repetição do marcador não comprova o número oficial",)),
    PerfilRegistrado("generico_v1", "1", "caderno", "desconhecida",
        "Formato de questão não identificado", ("segmentação geral conservadora",),
        ("não libera certificação automática",)),
    PerfilRegistrado(
        "pares_numero_resposta", "1", "gabarito", "multipla_escolha",
        "Pares de número e resposta", ("número e alternativa na mesma linha",),
        ("cargos ou versões múltiplas exigem seleção de escopo",),
    ),
    PerfilRegistrado(
        "matriz_numeros_e_respostas", "1", "gabarito", "multipla_escolha",
        "Matriz de números e respostas", ("números agrupados em linha",),
        ("lacunas e colunas ambíguas permanecem pendentes",),
    ),
    PerfilRegistrado(
        "lista_respostas", "1", "gabarito", "desconhecida",
        "Lista de respostas", ("respostas em lista ou blocos",),
        ("a associação por posição não é prova documental",),
    ),
    PerfilRegistrado(
        "multiprova_por_colunas", "1", "gabarito", "multipla_escolha",
        "Gabarito com várias provas em colunas", ("cabeçalhos explícitos de versão",),
        ("tipo de prova deve ser selecionado",),
    ),
    PerfilRegistrado(
        "matriz_multiversao", "1", "gabarito", "multipla_escolha",
        "Gabarito com várias versões", ("cabeçalhos de versão distintos",),
        ("código, cargo e versão devem coincidir",),
    ),
    PerfilRegistrado(
        "cex_itens_em_grade", "1", "gabarito", "certo_errado",
        "Gabarito certo/errado em grade", ("rótulo ITEM seguido de números",),
        ("grade sem número físico permanece pendente",),
    ),
    PerfilRegistrado(
        "listas_respostas_por_bloco", "1", "gabarito", "desconhecida",
        "Listas de respostas por bloco", ("sequências longas de respostas",),
        ("blocos e cargo precisam ser selecionados",),
    ),
)

POR_ID = {perfil.id: perfil for perfil in PERFIS}


def obter_perfil(perfil_id: str) -> PerfilRegistrado | None:
    return POR_ID.get(perfil_id)


def listar_perfis(papel: str | None = None) -> tuple[PerfilRegistrado, ...]:
    return tuple(perfil for perfil in PERFIS if papel is None or perfil.papel == papel)
