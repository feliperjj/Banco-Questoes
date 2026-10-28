"""Associação rastreável entre o reconhecimento do caderno e o gabarito."""
from .perfis.documentos import PerfilDocumento, pontuar_associacao, _sobreposicao_rotulos


def associar_documentos(caderno: PerfilDocumento, gabarito: PerfilDocumento, *,
                        numeros_caderno: set[int], respostas: dict[int, str],
                        codigo: str = "", cargo: str = "", evidencia_catalogo: str = "") -> dict:
    """Classifica a associação sem usar nome de arquivo ou posição visual."""
    base = pontuar_associacao(caderno, gabarito, codigo=codigo, cargo=cargo,
                              evidencia_catalogo=evidencia_catalogo)
    esperados = {int(n) for n in numeros_caderno if isinstance(n, int) and not isinstance(n, bool)}
    recebidos = {int(n) for n in respostas if isinstance(n, int) and not isinstance(n, bool)}
    faltantes = sorted(esperados - recebidos)
    extras = sorted(recebidos - esperados)
    conflitos = sorted(getattr(respostas, "conflitos", ()))
    faixa_compativel = bool(esperados & recebidos)
    meta_caderno = caderno.metadados or {}
    meta_gabarito = gabarito.metadados or {}
    codigo_fonte_comum = bool(set(meta_caderno.get("codigo", ()))
                              & (set(meta_gabarito.get("codigo", ())) | set(gabarito.identificadores)))
    cargo_fonte_comum = bool(_sobreposicao_rotulos(
        set(meta_caderno.get("cargo", ())), set(meta_gabarito.get("cargo", ()))
    ))
    versao_fonte_comum = bool(set(meta_caderno.get("versao", ())) & set(meta_gabarito.get("versao", ())))
    identidade_forte = codigo_fonte_comum and cargo_fonte_comum and versao_fonte_comum

    if base["decisao"] == "descartada":
        estado = "incompativel"
    elif conflitos or extras or not faixa_compativel:
        estado = "incompativel" if extras or (esperados and recebidos and not faixa_compativel) else "incompleto"
    elif faltantes:
        estado = "incompleto"
    elif base["decisao"] == "confirmada" or identidade_forte:
        estado = "correspondente"
    else:
        estado = "ambiguo"

    return {
        "estado": estado,
        "motivo": {
            "correspondente": "Identidade documental e numeração conferem.",
            "incompleto": "Há números sem resposta ou conflitos que precisam de conferência.",
            "ambiguo": "A estrutura coincide, mas faltam identificadores documentais suficientes.",
            "incompativel": "As evidências documentais não correspondem ao caderno selecionado.",
        }[estado],
        "numeros_esperados": len(esperados),
        "respostas_extraidas": len(recebidos),
        "faltantes": faltantes,
        "extras": extras,
        "conflitos": conflitos,
        "reconhecimento": base,
        "acao": "conferir_identidade" if estado == "ambiguo" else "corrigir_lacunas" if estado == "incompleto" else None,
    }
