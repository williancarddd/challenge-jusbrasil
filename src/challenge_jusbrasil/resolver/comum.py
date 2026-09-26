from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_DATA_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")


@dataclass(frozen=True)
class Resolucao:
    classificacao: str
    id_canonico: str | None = None


def sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto)
    return "".join(char for char in base if not unicodedata.combining(char))


def so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def sem_datas(texto: str) -> str:
    return _DATA_RE.sub(" ", texto)


def por_quantidade(ids: list[str]) -> Resolucao:
    unicos = list(dict.fromkeys(ids))
    if not unicos:
        return Resolucao("inventada")
    if len(unicos) == 1:
        return Resolucao("real", unicos[0])
    return Resolucao("incompleta")
