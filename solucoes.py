# -*- coding: utf-8 -*-
"""Registro de soluções do desafio Caça-Alucinações.

Cada solução é uma função `fn(texto, doc_id, ctx) -> list[citacao]`, onde cada
citacao é um dict no formato do contrato (inicio, fim, trecho, tipo,
classificacao, resolucao). `ctx` carrega o Resolvedor (consulta ao .db).
"""
import os
import re
import sys

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_BASE, "baseline_regra"))

from extrair import extrair            # noqa: E402
from baseline_fuzzy.extrair import extrair as extrair_fuzzy  # noqa: E402
from baseline_fuzzy.resolver import Resolvedor as ResolvedorFuzzy  # noqa: E402
from baseline_gliner.extrair import extrair as extrair_gliner  # noqa: E402


def _entrada(c, classe, idc):
    e = {"inicio": c["inicio"], "fim": c["fim"], "trecho": c["trecho"],
         "tipo": c["tipo"], "classificacao": classe}
    e["resolucao"] = {"id_canonico": idc} if classe == "real" and idc else None
    return e


def _pipeline(texto, ctx, extrator, rv, rx_sumula):
    out = []
    for c in extrator(texto):
        if c.get("_vaga"):
            classe, idc = "incompleta", None
        elif c["tipo"] == "lei":
            classe, idc = rv.resolver_lei(c["trecho"])
        elif rx_sumula.search(c["trecho"]):
            classe, idc = rv.resolver_sumula(c["trecho"])
        else:
            classe, idc = rv.resolver_juris(c["trecho"])
        out.append(_entrada(c, classe, idc))
    return out


def baseline_regra(texto, doc_id, ctx):
    return _pipeline(
        texto, ctx, extrair, ctx["resolvedor"],
        re.compile(r"s(ú|u)mula", re.IGNORECASE),
    )


def baseline_fuzzy(texto, doc_id, ctx):
    rv = ctx.get("resolvedor_fuzzy")
    if rv is None:
        rv = ResolvedorFuzzy(cx=ctx["resolvedor"].cx)
        ctx["resolvedor_fuzzy"] = rv
    return _pipeline(
        texto, ctx, extrair_fuzzy, rv,
        re.compile(r"(?:[5s][uú]m(?:ula|\.)|s[uú]m\.)", re.IGNORECASE),
    )


def baseline_gliner(texto, doc_id, ctx):
    rv = ctx.get("resolvedor_fuzzy")
    if rv is None:
        rv = ResolvedorFuzzy(cx=ctx["resolvedor"].cx)
        ctx["resolvedor_fuzzy"] = rv
    return _pipeline(
        texto, ctx, extrair_gliner, rv,
        re.compile(r"(?:[5s][uú]m(?:ula|\.)|s[uú]m\.)", re.IGNORECASE),
    )


REGISTRO = [
    ("baseline_regra", baseline_regra,
     "Baseline principal: extração + normalização + consulta ao .db + regra de feitos"),
    ("baseline_fuzzy", baseline_fuzzy,
     "Baseline fuzzy: RapidFuzz (Levenshtein) + OCR letra↔dígito + consulta ao .db"),
    ("baseline_gliner", baseline_gliner,
     "Baseline GLiNER: extração com GLiNER fine-tuned em GPU + resolução fuzzy/db"),
]
