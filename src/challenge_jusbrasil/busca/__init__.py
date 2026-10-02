from __future__ import annotations

from pathlib import Path
import os

from challenge_jusbrasil.busca.base import Busca, BuscaSemBase
from challenge_jusbrasil.busca.regex import BuscaRegex
from challenge_jusbrasil.resolver import Resolver
from challenge_jusbrasil.settings import BUSCA, ROOT

_MODOS = {"regex": BuscaRegex}


def criar_busca(modo: str | None = None, db_path: Path | None = None) -> Busca:
    nome = (modo or BUSCA).strip().lower()
    if nome not in _MODOS:
        raise ValueError(f"busca desconhecida: {nome}")
    caminho = os.getenv('DB_PATH', db_path)
    caminho = Path(caminho) if not isinstance(caminho, Path) else caminho
    # caminho = db_path if db_path is not None else ROOT / "data" / "desafio1_bracis.db"
    if not caminho.exists():
        return BuscaSemBase(nome)
    return _MODOS[nome](Resolver.carregar(caminho))
