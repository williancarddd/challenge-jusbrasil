from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from challenge_jusbrasil.resolver.comum import Resolucao, por_quantidade, sem_acento

_RE = re.compile(
    r"[s5][uú]m(?:ula|\.)(?:\s+vinculante)?(?:\s+n[º°.o]*)?\s*(\d+)",
    flags=re.IGNORECASE,
)
_TRIBUNAL_RE = re.compile(r"\b(STF|STJ|TST|TSE|STM)\b", flags=re.IGNORECASE)
_NUMERO_NO_TEXTO_RE = re.compile(
    r"s[uú]mula(?:\s+vinculante)?(?:\s+n[º°.o]*)?\s*(\d+)",
    flags=re.IGNORECASE,
)
_VINCULANTE_RE = re.compile(r"vinculante", flags=re.IGNORECASE)


@dataclass(frozen=True)
class _Sumula:
    id: str
    numero: str
    tribunal: str | None
    vinculante: bool


class ResolvedorSumula:
    def __init__(self, itens: list[_Sumula]) -> None:
        self.itens = itens

    @classmethod
    def carregar(cls, con: sqlite3.Connection) -> ResolvedorSumula:
        itens: list[_Sumula] = []
        for doc_id, tribunal, texto in con.execute(
            "SELECT id, tribunal, texto FROM documentos WHERE natureza = 'sumula'"
        ):
            match = _NUMERO_NO_TEXTO_RE.search(texto)
            if match is None:
                continue
            itens.append(
                _Sumula(
                    id=str(doc_id),
                    numero=match.group(1).lstrip("0") or "0",
                    tribunal=(tribunal or "").upper() or None,
                    vinculante=_VINCULANTE_RE.search(texto) is not None,
                )
            )
        return cls(itens)

    def reconhece(self, trecho: str) -> bool:
        return re.search(r"[s5][uú]m(?:ula\b|\.)", trecho, flags=re.IGNORECASE) is not None

    def resolve(self, trecho: str) -> Resolucao:
        match = _RE.search(sem_acento(trecho))
        if match is None:
            return Resolucao("incompleta")
        numero = match.group(1).lstrip("0") or "0"
        vinculante = _VINCULANTE_RE.search(trecho) is not None
        tribunal_match = _TRIBUNAL_RE.search(trecho)
        tribunal = tribunal_match.group(1).upper() if tribunal_match else None
        candidatos = [
            item
            for item in self.itens
            if item.numero == numero and item.vinculante == vinculante
        ]
        if tribunal:
            do_tribunal = [item for item in candidatos if item.tribunal == tribunal]
            if not do_tribunal:
                return Resolucao("inventada")
            candidatos = do_tribunal
        return por_quantidade([item.id for item in candidatos])
