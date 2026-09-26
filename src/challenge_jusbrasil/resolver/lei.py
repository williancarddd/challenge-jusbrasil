from __future__ import annotations

import re
import sqlite3
from collections import defaultdict

from challenge_jusbrasil.resolver.comum import Resolucao, por_quantidade, so_digitos

_ARTIGO_RE = re.compile(
    r"art(?:igo)?s?\.?\s*(\d[\d.]*)",
    flags=re.IGNORECASE,
)
_ARTIGO_NO_TEXTO_RE = re.compile(r"Art\.?\s*(\d+)", flags=re.IGNORECASE)
_LEI_RE = re.compile(
    r"\bart(?:igo)?s?\.?\s*(?:\d|correspondente)|"
    r"\blei\b|"
    r"\bc[oó]digos?\b|"
    r"constitui[cç]|"
    r"\b(?:CLT|CPC|CPP|CPM|CDC|CF)\b|"
    r"\bdispositivo\b|"
    r"\blegisla[cç]|"
    r"\bnormas?\s+de\s+reg[eê]ncia",
    flags=re.IGNORECASE,
)


def tipo_de(trecho: str) -> str:
    if _LEI_RE.search(trecho):
        return "lei"
    return "jurisprudencia"


class ResolvedorLei:
    def __init__(self, por_numero: dict[str, list[str]]) -> None:
        self.por_numero = por_numero

    @classmethod
    def carregar(cls, con: sqlite3.Connection) -> ResolvedorLei:
        por_numero: dict[str, list[str]] = defaultdict(list)
        for doc_id, texto in con.execute(
            "SELECT id, texto FROM documentos WHERE natureza = 'dispositivo'"
        ):
            match = _ARTIGO_NO_TEXTO_RE.search(texto)
            if match is None:
                continue
            numero = match.group(1).lstrip("0") or "0"
            por_numero[numero].append(str(doc_id))
        return cls(dict(por_numero))

    def reconhece(self, trecho: str) -> bool:
        return tipo_de(trecho) == "lei"

    def resolve(self, trecho: str) -> Resolucao:
        match = _ARTIGO_RE.search(trecho)
        if match is None:
            return Resolucao("incompleta")
        numero = so_digitos(match.group(1)).lstrip("0") or "0"
        return por_quantidade(self.por_numero.get(numero, []))
