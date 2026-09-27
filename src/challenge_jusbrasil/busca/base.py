from __future__ import annotations

from typing import Any, Protocol

from challenge_jusbrasil.resolver.comum import Resolucao

CONTEXTO = 250


class Busca(Protocol):
    nome: str

    def aplicar(self, texto: str, citacoes: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


def gravar(cit: dict[str, Any], tipo: str, resultado: Resolucao) -> None:
    cit["tipo"] = tipo
    cit["classificacao"] = resultado.classificacao
    cit["resolucao"] = (
        {"id_canonico": resultado.id_canonico}
        if resultado.classificacao == "real" and resultado.id_canonico
        else None
    )


def contexto_de(texto: str, cit: dict[str, Any]) -> str:
    inicio = int(cit["inicio"])
    fim = int(cit["fim"])
    return texto[max(0, inicio - CONTEXTO) : fim + CONTEXTO]


class BuscaSemBase:
    def __init__(self, nome: str) -> None:
        self.nome = nome

    def aplicar(self, texto: str, citacoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        del texto
        for cit in citacoes:
            if cit["classificacao"] == "real":
                cit["classificacao"] = "incompleta"
            cit["resolucao"] = None
        return citacoes
