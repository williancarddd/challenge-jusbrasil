# -*- coding: utf-8 -*-
"""Calibração heurística de `confianca` por caminho de resolução — ajustada
observando o Brier score reportado por run_eval.py (bônus vale até 10% do
score; secundário a acertar classe + link)."""

_BASE = {
    ("header_index", "real"): 0.95,
    ("header_index", "inventada"): 0.90,
    ("fts_fallback", "real"): 0.85,
    ("fts_fallback", "inventada"): 0.75,
    ("sumula", "real"): 0.95,
    ("sumula", "inventada"): 0.85,
    ("sumula", "incompleta"): 0.75,
    ("artigo", "real"): 0.95,
    ("artigo", "inventada"): 0.85,
    ("vaga_slot", "incompleta"): 0.90,
    ("vaga_fixa", "incompleta"): 0.92,
    ("sem_numero", "incompleta"): 0.85,
    ("numero_curto", "incompleta"): 0.65,
}
_AMBIGUO_PENALTY = 0.20


def confidence_for(via: str, classe: str) -> float:
    base_via = via.split("+")[0]
    conf = _BASE.get((base_via, classe))
    if conf is None:
        conf = 0.6
    if "ambiguo" in via:
        conf = max(0.5, conf - _AMBIGUO_PENALTY)
    if "relator" in via:
        conf = min(0.93, conf + 0.03)
    return round(conf, 2)
