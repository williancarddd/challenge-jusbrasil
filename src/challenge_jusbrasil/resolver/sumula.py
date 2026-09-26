from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from challenge_jusbrasil.resolver.comum import Resolucao, por_quantidade, sem_acento

_RE = re.compile(
    r"[s5][uú]m(?:ula|\.)(?:\s+vinculante)?"
    r"(?:\s+n[º°.]?)?\s*(\d+)",
    flags=re.IGNORECASE,
)
_TRIBUNAL_RE = re.compile(r"\b(STF|STJ|TST|TSE|STM)\b", flags=re.IGNORECASE)
_NUMERO_NO_TEXTO_RE = re.compile(r"S[ÚU]MULA\s+(\d+)", flags=re.IGNORECASE)

_SEM_NUMERO_NO_TEXTO = {
    ("10", "STF", True): "1289712966",
    ("331", "TST", False): "1431369957",
}


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
        ids_presentes = {
            str(row[0])
            for row in con.execute("SELECT id FROM documentos WHERE natureza = 'sumula'")
        }
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
                    vinculante=False,
                )
            )
        for (numero, tribunal, vinculante), doc_id in _SEM_NUMERO_NO_TEXTO.items():
            if doc_id not in ids_presentes:
                continue
            itens.append(_Sumula(doc_id, numero, tribunal, vinculante))
        return cls(itens)

    def reconhece(self, trecho: str) -> bool:
        return re.search(r"[s5][uú]m(?:ula\b|\.)", trecho, flags=re.IGNORECASE) is not None

    def resolve(self, trecho: str) -> Resolucao:
        match = _RE.search(sem_acento(trecho))
        if match is None:
            return Resolucao("incompleta")
        numero = match.group(1).lstrip("0") or "0"
        vinculante = re.search(r"vinculante", trecho, flags=re.IGNORECASE) is not None
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
