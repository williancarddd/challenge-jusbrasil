from __future__ import annotations

import sqlite3
from pathlib import Path

from challenge_jusbrasil.resolver.acordao import ResolvedorAcordao
from challenge_jusbrasil.resolver.comum import Resolucao
from challenge_jusbrasil.resolver.lei import ResolvedorLei
from challenge_jusbrasil.resolver.sumula import ResolvedorSumula


class Resolver:
    def __init__(
        self,
        sumula: ResolvedorSumula,
        lei: ResolvedorLei,
        acordao: ResolvedorAcordao,
    ) -> None:
        self.sumula = sumula
        self.lei = lei
        self.acordao = acordao

    @classmethod
    def carregar(cls, db_path: Path) -> Resolver:
        con = sqlite3.connect(str(db_path))
        con.text_factory = lambda b: b.decode("utf-8", "replace")
        try:
            return cls(
                ResolvedorSumula.carregar(con),
                ResolvedorLei.carregar(con),
                ResolvedorAcordao.carregar(con),
            )
        finally:
            con.close()

    def resolve(self, trecho: str, tipo: str, contexto: str = "") -> Resolucao:
        if tipo == "lei" or self.lei.reconhece(trecho):
            return self.lei.resolve(trecho)
        if self.sumula.reconhece(trecho):
            return self.sumula.resolve(trecho)
        return self.acordao.resolve(trecho, contexto)
