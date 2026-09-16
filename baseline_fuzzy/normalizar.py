# -*- coding: utf-8 -*-
"""Normalização com OCR de letras que imitam dígitos (nunca dígito→dígito)."""
import re

_OCR_TOKEN = [
    str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "G": "6", "g": "9"}),
    str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "G": "6", "g": "6"}),
    str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5"}),
]


def _aplica_ocr(tok, tabela):
    if not re.search(r"\d", tok):
        return tok
    return tok.translate(tabela)


def so_digitos(s: str, tabela=None) -> str:
    if tabela is None:
        tabela = _OCR_TOKEN[0]
    partes = []
    for tok in re.split(r"(\s+)", s.replace("\n", " ")):
        partes.append(_aplica_ocr(tok, tabela))
    return re.sub(r"\D", "", "".join(partes))


def hipoteses_digitos(s: str):
    visto = []
    for tab in _OCR_TOKEN:
        d = so_digitos(s, tab)
        if d and d not in visto:
            visto.append(d)
    cru = re.sub(r"\D", "", s)
    if cru and cru not in visto:
        visto.append(cru)
    return visto


def reagrupa_milhar(digits: str) -> str:
    if not digits:
        return ""
    partes = []
    while len(digits) > 3:
        partes.insert(0, digits[-3:])
        digits = digits[:-3]
    partes.insert(0, digits)
    return ".".join(partes)


def is_cnj(digits: str) -> bool:
    return len(digits) == 20


def cnj_formatado(digits: str) -> str:
    d = digits
    return f"{d[0:7]}-{d[7:9]}.{d[9:13]}.{d[13:14]}.{d[14:16]}.{d[16:20]}"


def frases_busca(digits: str):
    out = []
    if is_cnj(digits):
        out.append(cnj_formatado(digits))
    agrup = reagrupa_milhar(digits)
    if agrup:
        out.append(agrup)
    out.append(digits)
    visto, uniq = set(), []
    for f in out:
        if f and f not in visto:
            visto.add(f)
            uniq.append(f)
    return uniq
