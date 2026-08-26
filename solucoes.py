# -*- coding: utf-8 -*-
"""Registro de soluções do desafio Caça-Alucinações.

Cada solução é uma função `fn(texto, doc_id, ctx) -> list[citacao]`, onde cada
citacao é um dict no formato do contrato (inicio, fim, trecho, tipo,
classificacao, resolucao). `ctx` carrega o Resolvedor (consulta ao .db).

Atualmente há uma única solução: o baseline principal (regra completa).
"""
import os
import re
import sys

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_BASE, "baseline_regra"))

from extrair import extrair            # noqa: E402


def _entrada(c, classe, idc):
    e = {"inicio": c["inicio"], "fim": c["fim"], "trecho": c["trecho"],
         "tipo": c["tipo"], "classificacao": classe}
    e["resolucao"] = {"id_canonico": idc} if classe == "real" and idc else None
    return e


# --- Baseline principal: regra completa (extração + resolução) --------------
def baseline_regra(texto, doc_id, ctx):
    rv = ctx["resolvedor"]
    out = []
    for c in extrair(texto):
        if c["_vaga"]:
            classe, idc = "incompleta", None
        elif c["tipo"] == "lei":
            classe, idc = rv.resolver_lei(c["trecho"])
        elif re.search(r"s(ú|u)mula", c["trecho"], re.IGNORECASE):
            classe, idc = rv.resolver_sumula(c["trecho"])
        else:
            classe, idc = rv.resolver_juris(c["trecho"])
        out.append(_entrada(c, classe, idc))
    return out


REGISTRO = [
    ("baseline_regra", baseline_regra,
     "Baseline principal: extração + normalização + consulta ao .db + regra de feitos"),
]
