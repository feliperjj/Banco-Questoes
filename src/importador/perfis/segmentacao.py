"""Perfis concorrentes: reconhecer, segmentar, validar e só então selecionar.

Não consulta banca nem gabaritos. Empates conservam o candidato geral e deixam
um aviso; mais blocos não bastam para vencer um perfil estruturalmente íntegro.
"""
from dataclasses import dataclass, field
import re

from .lexico import (_INICIO_QUESTAO, _INICIO_QUESTAO_NOMEADA,
                     _INICIO_ALTERNATIVA, _MARCADOR_QUESTAO,
                     _separar_alternativas_horizontais, _juntar_linhas, _partes_alternativas)
from .certo_errado import _separar_itens_cespe
from .multipla_escolha import _blocos_multipla_escolha


@dataclass(frozen=True)
class Segmentacao:
    perfil: str
    candidatos: list[str]
    tem_alternativas: bool
    aviso: str = ""
    diagnostico: tuple[dict, ...] = ()


@dataclass(frozen=True)
class Perfil:
    id: str
    descricao: str
    padrao: str = ""


PERFIS = (
    Perfil("questoes_nomeadas_v2", "QUESTÃO, QUESTAO, QUEST�O, QUESTÃO Nº, ITEM e Q.",
           r"(?im)^\s*(?:quest(?:ão|ao|�o)|item|q\.)\s*(?:n[º°o.]?\s*)?(\d{1,3})(?:\s*[:.)–—-][ \t]*|[ \t]*\n|[ \t]+)"),
    Perfil("multipla_escolha_numero_isolado_v2", "Número sozinho na linha", r"(?m)^[ \t]*(\d{1,3})[ \t]*\n"),
    Perfil("multipla_escolha_pontuada_v2", "Número seguido de ponto, parêntese, dois-pontos ou traço", r"(?m)^[ \t]*(\d{1,3})[ \t]*[.)][ \t]+"),
    Perfil("multipla_escolha_traco_v2", "Número seguido de traço", r"(?m)^[ \t]*(\d{1,3})[ \t]*[-–—][ \t]+"),
    Perfil("multipla_escolha_dois_pontos_v2", "Número seguido de dois-pontos", r"(?m)^[ \t]*(\d{1,3})[ \t]*:[ \t]+"),
    Perfil("multipla_escolha_numero_espaco_v2", "Número e enunciado na mesma linha", r"(?m)^[ \t]*(\d{1,3})[ \t]+(?=\S)"),
)


def partes_bloco(bloco):
    marcador = _MARCADOR_QUESTAO.match(bloco.strip())
    conteudo = bloco.strip()[marcador.end():] if marcador else bloco.strip()
    conteudo = re.split(r"(?im)^\s*JUSTIFICATIVA(?:[ \t]*[-–:]|[ \t]*$)", conteudo)[0]
    return _partes_alternativas(conteudo)


def _pontuar(blocos):
    numeros, validos, defeitos = [], 0, 0
    for bloco in blocos:
        m = _MARCADOR_QUESTAO.match(bloco.strip())
        if not m:
            defeitos += 1
            continue
        partes = partes_bloco(bloco)
        letras = [l.upper() for l in partes[1::2]]
        if len(_juntar_linhas(partes[0])) < 10:
            defeitos += 1
            continue
        if letras:
            if len(letras) < 2:
                defeitos += 1
                continue
            if letras != list('ABCDE'[:len(letras)]):
                defeitos += 1
            validos += 1
            numeros.append(int(m.group(1)))
    duplicados = len(numeros) - len(set(numeros))
    amplitude = max(numeros) - min(numeros) if numeros else 0
    return (len(set(numeros)), -duplicados, -defeitos, validos, -amplitude)


def _por_padrao(texto, perfil):
    marcadores = list(re.finditer(perfil.padrao, texto))
    if perfil.id == 'multipla_escolha_numero_isolado_v2':
        # Frações, rodapés e células numéricas não iniciam um enunciado.
        # Exigir texto na linha seguinte impede que roubem o próximo marcador.
        marcadores = [m for m in marcadores
                      if re.match(r'[ \t]*[“"\(\[]?[A-ZÀ-Ý]', texto[m.end():])
                      and not _INICIO_ALTERNATIVA.match(texto[m.end():])]
        # Avaliar o bloco à frente: um número de página antes de uma nova
        # questão não pode consumir essa questão por faltar alternativas.
        validos = [m for i, m in enumerate(marcadores)
                   if len(partes_bloco('QUESTÃO ' + m.group(1) + '\n' +
                       texto[m.end():marcadores[i+1].start() if i+1 < len(marcadores) else len(texto)])) >= 5]
        return ['QUESTÃO ' + m.group(1) + '\n' + texto[m.end():validos[i+1].start() if i+1 < len(validos) else len(texto)]
                for i, m in enumerate(validos)]
    inicios = []
    for m in marcadores:
        if perfil.id.startswith('questoes_nomeadas') or not inicios:
            inicios.append(m)
        else:
            # Uma enumeração dentro do enunciado não encerra uma questão.
            anterior = 'QUESTÃO ' + inicios[-1].group(1) + '\n' + texto[inicios[-1].end():m.start()]
            if len(partes_bloco(anterior)) >= 5:
                inicios.append(m)
    return ['QUESTÃO ' + m.group(1) + '\n' + texto[m.end():inicios[i+1].start() if i+1 < len(inicios) else len(texto)]
            for i, m in enumerate(inicios)]


def _geral(texto):
    nomeadas = bool(_INICIO_QUESTAO_NOMEADA.search(texto))
    alternativas = len(_INICIO_ALTERNATIVA.findall(texto)) >= 2
    sem = [] if nomeadas or alternativas else _separar_itens_cespe(texto)
    if sem:
        return 'certo_errado_sequencial_v1', sem, alternativas
    padrao = _INICIO_QUESTAO_NOMEADA if nomeadas else _INICIO_QUESTAO
    partes = padrao.split(texto)
    blocos = [partes[i] + partes[i+1] for i in range(1, len(partes)-1, 2)]
    perfil = 'questoes_nomeadas_v1' if nomeadas else 'multipla_escolha_numerada_v1' if alternativas else 'generico_v1'
    return perfil, blocos, alternativas


def _sequencia_isolada(texto):
    """Caminho consecutivo entre marcadores impressos, sem criar números.

    Desempata ocorrências repetidas pela presença de alternativas locais;
    números de figura/rodapé não podem deslocar o restante da sequência.
    """
    ms = list(re.finditer(PERFIS[1].padrao, texto))
    ms = [m for m in ms if re.match(r'[ \t]*[“"\(\[]?[A-ZÀ-Ý]', texto[m.end():])
          and not _INICIO_ALTERNATIVA.match(texto[m.end():])]
    caminhos = {}
    melhor = ([], 0)
    for i, m in enumerate(ms):
        n = int(m.group(1))
        fim = ms[i+1].start() if i+1 < len(ms) else len(texto)
        local = int(len(partes_bloco('QUESTÃO '+str(n)+'\n'+texto[m.end():fim])) >= 5)
        anterior, qualidade = caminhos.get(n-1, ([], 0))
        candidato = (anterior + [m], qualidade + local)
        chave = lambda c: (len(c[0]), c[1])
        if n not in caminhos or chave(candidato) > chave(caminhos[n]):
            caminhos[n] = candidato
        if chave(candidato) > chave(melhor):
            melhor = candidato
    selecionados = melhor[0]
    if len(selecionados) < 3:
        return []
    return ['QUESTÃO '+m.group(1)+'\n'+texto[m.end():selecionados[i+1].start() if i+1<len(selecionados) else len(texto)]
            for i,m in enumerate(selecionados)]


def segmentar(texto_questoes: str, texto_original: str, banca: str = "") -> Segmentacao:
    perfil, geral, alternativas = _geral(texto_questoes)
    if '\nITEM PARA JULGAMENTO\n' in texto_questoes and '\nTEXTO DE APOIO\n' in texto_questoes:
        return Segmentacao('certo_errado_contexto_v1', geral, False)
    if perfil == 'certo_errado_sequencial_v1':
        return Segmentacao(perfil, geral, False)
    # Os cabeçalhos nomeados têm precedência sobre números internos.
    nomeado = _por_padrao(texto_questoes, PERFIS[0])
    if nomeado and not _INICIO_QUESTAO_NOMEADA.search(texto_questoes):
        return Segmentacao(PERFIS[0].id, nomeado, alternativas)
    if perfil == 'questoes_nomeadas_v1':
        return Segmentacao(perfil, geral, alternativas)
    candidatos = [(perfil, geral)]
    sequencia = _sequencia_isolada(texto_questoes)
    if sequencia:
        candidatos.append(('multipla_escolha_sequencia_isolada_v3', sequencia))
    for p in PERFIS[1:]:
        blocos = _por_padrao(texto_questoes, p)
        if blocos and _pontuar(blocos)[3] >= 2:
            candidatos.append((p.id, blocos))
    # Perfil predominante legado também concorre, agora sem condição de banca.
    predominante = _blocos_multipla_escolha(texto_original)
    if predominante and _pontuar(predominante)[3] >= 2:
        candidatos.append(('multipla_escolha_predominante_v2', predominante))
    # Um especialista não pode trocar uma sequência maior por poucos blocos
    # bonitos, nem ganhar absorvendo marcadores e criando duplicatas.
    def numeros_extraiveis(bs):
        ns = []
        for b in bs:
            m = _MARCADOR_QUESTAO.match(b.strip())
            ps = partes_bloco(b)
            if m and len(_juntar_linhas(ps[0])) >= 10 and (not alternativas or len(ps) >= 3):
                ns.append(int(m.group(1)))
        return ns
    base_numeros = numeros_extraiveis(geral)
    seguros = [candidatos[0]]
    for p, bs in candidatos[1:]:
        ns = numeros_extraiveis(bs)
        if len(ns) >= len(set(base_numeros)) and ns == sorted(set(ns)):
            seguros.append((p, bs))
    candidatos = seguros
    pontuacoes = [_pontuar(blocos) for _, blocos in candidatos]
    melhor = max(range(len(candidatos)), key=lambda i: pontuacoes[i])
    if base_numeros == sorted(set(base_numeros)) and base_numeros:
        # Sem ganho de numeração, limites diferentes exigem revisão: não
        # absorver rodapés, instruções ou texto da próxima página para pontuar.
        if numeros_extraiveis(candidatos[melhor][1]) == base_numeros:
            melhor = 0
    selecionado, blocos = candidatos[melhor]
    diagnostico = tuple({'perfil': p, 'blocos': len(b), 'pontuacao': list(pontuacoes[i]), 'selecionado': i == melhor}
                        for i, (p, b) in enumerate(candidatos))
    aviso = ''
    if selecionado == 'generico_v1':
        aviso = 'Formato não identificado com segurança; revise a segmentação.'
    elif any(i != melhor and pontuacoes[i] == pontuacoes[melhor]
             and [partes_bloco(b) for b in bs] != [partes_bloco(b) for b in blocos]
             for i, (_, bs) in enumerate(candidatos)):
        aviso = 'Há segmentações diferentes com qualidade equivalente; revise os limites das questões.'
    return Segmentacao(selecionado, blocos, alternativas, aviso, diagnostico)
