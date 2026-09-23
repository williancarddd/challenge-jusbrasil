# -*- coding: utf-8 -*-
"""Orquestra um único documento: extrai -> resolve -> monta o JSON do
contrato (schema 1.2: documento_id, citacoes[] com inicio/fim/trecho/tipo/
classificacao/resolucao/confianca)."""
from confidence import confidence_for
from extract import extract_raw
from resolve import (KB, resolve_jurisprudencia_numero, resolve_lei_artigo,
                      resolve_sumula)

CONTEXT_RADIUS = 250


def process_texto(texto: str, kb: KB):
    raw = extract_raw(texto)
    citacoes = []
    for c in raw:
        via = c["via"]
        if via == "sumula":
            classe, id_ = resolve_sumula(kb, c["numero"], c["tribunal"], c["vinculante"])
            path = "sumula"
        elif via == "artigo":
            classe, id_ = resolve_lei_artigo(kb, c["numero"], c["codigo"])
            path = "artigo"
        elif via in ("vaga_slot", "vaga_fixa"):
            classe, id_, path = "incompleta", None, via
        elif via == "numero":
            trecho = texto[c["inicio"]:c["fim"]]
            ctx = texto[max(0, c["inicio"] - CONTEXT_RADIUS):c["fim"] + CONTEXT_RADIUS]
            classe, id_, path = resolve_jurisprudencia_numero(kb, trecho, ctx)
        else:
            classe, id_, path = "incompleta", None, "desconhecido"

        conf = confidence_for(path, classe)
        citacoes.append({
            "inicio": c["inicio"],
            "fim": c["fim"],
            "trecho": texto[c["inicio"]:c["fim"]],
            "tipo": c["tipo"],
            "classificacao": classe,
            "resolucao": {"id_canonico": str(id_)} if classe == "real" and id_ is not None else None,
            "confianca": conf,
        })
    return citacoes


def process_documento(documento_id: str, texto: str, kb: KB) -> dict:
    return {"documento_id": documento_id, "citacoes": process_texto(texto, kb)}
