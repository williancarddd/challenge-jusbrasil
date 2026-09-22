# -*- coding: utf-8 -*-
"""Matching fuzzy via RapidFuzz (Levenshtein + ratio) para ruído/OCR."""
import re
import unicodedata

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein


def normaliza(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    if s[:1] == "5" and len(s) > 2 and s[1:].isalpha():
        s = "s" + s[1:]
    return s


def score(a: str, b: str) -> float:
    return fuzz.ratio(normaliza(a), normaliza(b))


def proximo(tok: str, alvo: str, max_dist=None) -> bool:
    a, b = normaliza(tok), normaliza(alvo)
    if len(b) < 4:
        return a == b
    if max_dist is None:
        max_dist = 1 if len(b) < 10 else 2
    if abs(len(a) - len(b)) > max_dist + 1:
        return False
    if Levenshtein.distance(a, b) <= max_dist:
        return True
    if Levenshtein.distance(a.replace("rn", "m"), b) <= max_dist:
        return True
    return fuzz.ratio(a, b) >= 86


def iter_proximos(texto: str, alvos, max_dist=None):
    alvos_n = [(alvo, normaliza(alvo)) for alvo in alvos]
    for m in re.finditer(r"[0-9A-Za-zÀ-ÿ]+", texto):
        tok = m.group()
        nt = normaliza(tok)
        if len(nt) < 3:
            continue
        for alvo, an in alvos_n:
            if len(an) < 4:
                if nt == an:
                    yield m.start(), m.end(), alvo
                    break
                continue
            if proximo(tok, alvo, max_dist=max_dist):
                yield m.start(), m.end(), alvo
                break


def melhor_rotulo(consulta: str, rotulos, corte=80):
    from rapidfuzz import process

    if not consulta or not rotulos:
        return None
    hit = process.extractOne(
        normaliza(consulta),
        {k: normaliza(k) for k in rotulos},
        scorer=fuzz.partial_ratio,
        score_cutoff=corte,
    )
    if not hit:
        return None
    rotulo, sc, _ = hit
    return rotulo, sc
