"""Formatação de leitura; não modifica o texto persistido nem o gabarito."""
import re


def formatar_enunciado(texto):
    romanos = re.findall(r"(?<!\w)(I{1,3}|IV|V)[.)]\s+", texto)
    if len(romanos) >= 2 and romanos == ['I', 'II', 'III', 'IV', 'V'][:len(romanos)]:
        texto = re.sub(r"\s+(?=(?:III|II|IV|I|V)[.)]\s+)", "\n\n", texto)
        texto = re.sub(r"(?<=[.!?])\s+(?=(?:Está correto|Assinale|Com base no texto)\b)", "\n\n", texto)
    # Só interpretar lacunas como itens quando o comando explicita V/F.
    contexto_vf = re.search(r"verdadeir[oa]", texto, re.I) and re.search(r"fals[oa]", texto, re.I)
    marcador = r"\(\s*\)"
    if not contexto_vf or len(re.findall(marcador, texto)) < 2:
        return texto
    texto = re.sub(r"\s*(\(\s*\))\s*", r"\n\n(  )  ", texto).strip()
    # Separar o comando final da última afirmação sem remover seu conteúdo.
    texto = re.sub(r"(?<=[.!?])\s+(?=(?:Assinale|Marque|Selecione)\b)", "\n\n", texto)
    return texto
