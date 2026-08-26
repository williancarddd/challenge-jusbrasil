# -*- coding: utf-8 -*-
"""Normalização determinística de identificadores (o coração do nível 2).

Garantia do desafio: um dígito nunca é trocado por outro. Todo ruído
(abreviação, pontuação, separador de UF, OCR, quebra de linha) é recuperável.
"""
import re
import unicodedata

# Confusões de OCR — só as seguras (nunca dígito->dígito).
_OCR = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5"})

def so_digitos(s: str) -> str:
    return re.sub(r"\D", "", s)

def reagrupa_milhar(digits: str) -> str:
    """1996496 -> '1.996.496' (de três em três a partir da direita)."""
    if not digits:
        return ""
    partes = []
    while len(digits) > 3:
        partes.insert(0, digits[-3:])
        digits = digits[:-3]
    partes.insert(0, digits)
    return ".".join(partes)

def normaliza_uf(s: str):
    """Extrai a UF de /PR, - PR, (PR). Retorna None se ausente."""
    m = re.search(r"[/\-(]\s*([A-Z]{2})\s*\)?\s*$", s.strip())
    return m.group(1) if m else None

def is_cnj(digits: str) -> bool:
    """Número CNJ tem 20 dígitos: NNNNNNN DD AAAA J TR OOOO."""
    return len(digits) == 20

def cnj_formatado(digits: str) -> str:
    d = digits
    return f"{d[0:7]}-{d[7:9]}.{d[9:13]}.{d[13:14]}.{d[14:16]}.{d[16:20]}"

def frase_fts(trecho: str) -> str:
    """Reconstrói a forma canônica buscável por frase no FTS unicode61.

    Junta a quebra de linha no meio do identificador, corrige OCR fora dos
    dígitos e reagrupa o número. Retorna a string a usar em MATCH '"..."'.
    """
    limpo = trecho.replace("\n", " ")
    # separa a parte numérica
    digits = so_digitos(limpo)
    if is_cnj(digits):
        return cnj_formatado(digits)
    if digits:
        return reagrupa_milhar(digits)
    return limpo.strip()
