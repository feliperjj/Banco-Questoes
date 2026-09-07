"""Estratégia isolada: certo errado (v1)."""
import re


def _separar_itens_cespe(texto: str) -> list[str]:
    """Separa itens CESPE, ignorando números de linha dos textos-base."""
    from src.importador.perfis.lexico import _INICIO_NUMERADO, _parece_grade_respostas
    candidatos = [
        candidato for candidato in _INICIO_NUMERADO.finditer(texto)
        if not _parece_grade_respostas(candidato.group(0))
    ]
    if not candidatos:
        return []

    blocos_reais = []
    for indice, candidato in enumerate(candidatos):
        fim = candidatos[indice + 1].start() if indice + 1 < len(candidatos) else len(texto)
        bloco = texto[candidato.start():fim].strip()
        # Itens da prova têm uma justificativa; números de linha dos textos-base não.
        if re.search(r'(?im)^\s*JUSTIFICATIVA(?:\s*[-–:]|\s*$)', bloco):
            blocos_reais.append(bloco)

    # Algumas fontes não trazem justificativa. Nesse caso, aproveita a
    # sequência numerada principal como fallback. Em PDFs de duas colunas a
    # ordem de leitura pode intercalar números de texto-base (por exemplo,
    # 1, 2, 3, 4, 10, 5, 25, 11...). Consolidar a primeira ocorrência de cada
    # número a partir do primeiro item 1 recupera a sequência sem duplicar
    # blocos discursivos posteriores.
    if len(blocos_reais) < 2:
        inicio = next((indice for indice, candidato in enumerate(candidatos) if int(candidato.group(1)) == 1), None)
        sequencia_por_numero = {}
        if inicio is not None:
            for candidato in candidatos[inicio:]:
                numero = int(candidato.group(1))
                if numero >= 1:
                    sequencia_por_numero.setdefault(numero, candidato)

        maior_prefixo = 0
        while maior_prefixo + 1 in sequencia_por_numero:
            maior_prefixo += 1
        selecionados = {
            numero: sequencia_por_numero[numero]
            for numero in range(1, maior_prefixo + 1)
        }
        # O fim do bloco é determinado pela ordem física do PDF, enquanto a
        # saída volta à ordem numérica oficial.
        por_posicao = sorted(selecionados.items(), key=lambda item: item[1].start())
        blocos_por_numero = {}
        for indice, (numero, candidato) in enumerate(por_posicao):
            fim = por_posicao[indice + 1][1].start() if indice + 1 < len(por_posicao) else len(texto)
            blocos_por_numero[numero] = texto[candidato.start():fim].strip()
        blocos_reais = [blocos_por_numero[numero] for numero in range(1, maior_prefixo + 1)]
    return blocos_reais
