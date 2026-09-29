from __future__ import annotations

from typing import Any

from challenge_jusbrasil.busca.base import contexto_de, gravar
from challenge_jusbrasil.resolver import Resolver
from challenge_jusbrasil.resolver.lei import tipo_de


class BuscaRegex:
    nome = "regex"

    def __init__(self, resolver: Resolver) -> None:
        self.resolver = resolver

    def aplicar(self, texto: str, citacoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for cit in citacoes:
            trecho = cit["trecho"]
            tipo = tipo_de(trecho)
            contexto = contexto_de(texto, cit)
            resultado = self.resolver.resolve(trecho, tipo, contexto)
            gravar(cit, tipo, resultado, contexto)
        return citacoes
