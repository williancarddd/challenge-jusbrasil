from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from challenge_jusbrasil.resolver.comum import Resolucao, por_quantidade, sem_acento, so_digitos

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


_LEI_NUM_RE = re.compile(
    r"lei(?:\s+complementar)?(?:\s+n[º°.o]*)?\s*([\d.]+)\s*/\s*(\d{4})",
    flags=re.IGNORECASE,
)
_ALIASES_LEI = {
    ("13105", "2015"): "cpc",
    ("8078", "1990"): "cdc",
    ("10406", "2002"): "cc",
    ("3689", "1941"): "cpp",
}
_JANELA_DIPLOMA = 500


def tipo_de(trecho: str) -> str:
    if _LEI_RE.search(trecho):
        return "lei"
    return "jurisprudencia"


def _numero(bruto: str) -> str:
    return so_digitos(bruto).lstrip("0") or "0"


def _base(texto: str) -> str:
    return " ".join(sem_acento(texto).lower().split())


def diploma_do_documento(texto: str) -> str | None:
    trecho = _base(texto[:_JANELA_DIPLOMA])
    if "administracao militar" in trecho:
        return "cpm"
    if "sao inelegiveis" in trecho:
        return "lc64"
    if "tribunais eleitorais" in trecho or "eleicoes federais" in trecho:
        return "ce"
    if "fornecedor" in trecho and "consumidor" in trecho:
        return "cdc"
    if "prisao preventiva" in trecho:
        return "cpp"
    if (
        "tribunal superior do trabalho" in trecho
        or "reclamante" in trecho
        or "contrato de trabalho" in trecho
    ):
        return "clt"
    if (
        "estatuto da magistratura" in trecho
        or "brasileiros e aos estrangeiros" in trecho
        or "trabalhadores urbanos e rurais" in trecho
        or "desta constituicao" in trecho
    ):
        return "cf"
    if "onus da prova" in trecho and "ao autor" in trecho:
        return "cpc"
    if "ato ilicito" in trecho:
        return "cc"
    return None


def diploma_do_trecho(trecho: str) -> str | None:
    base = _base(trecho)
    match = _LEI_NUM_RE.search(base)
    if match is not None:
        numero = _numero(match.group(1))
        ano = match.group(2)
        if "complementar" in base and (numero, ano) == ("64", "1990"):
            return "lc64"
        alias = _ALIASES_LEI.get((numero, ano))
        if alias is not None:
            return alias
        return f"lei-{numero}-{ano}"
    if "codigo de processo civil" in base or re.search(r"\bcpc\b", base):
        return "cpc"
    if "codigo de processo penal" in base or re.search(r"\bcpp\b", base):
        return "cpp"
    if "codigo de defesa do consumidor" in base or re.search(r"\bcdc\b", base):
        return "cdc"
    if "codigo civil" in base:
        return "cc"
    if "codigo eleitoral" in base:
        return "ce"
    if "penal militar" in base or re.search(r"\bcpm\b", base):
        return "cpm"
    if "consolidacao das leis do trabalho" in base or re.search(r"\bclt\b", base):
        return "clt"
    if "constitui" in base or re.search(r"\bcf\b", base):
        return "cf"
    return None


@dataclass(frozen=True)
class _Dispositivo:
    id: str
    numero: str
    diploma: str | None


class ResolvedorLei:
    def __init__(self, itens: list[_Dispositivo]) -> None:
        self.itens = itens

    @classmethod
    def carregar(cls, con: sqlite3.Connection) -> ResolvedorLei:
        itens: list[_Dispositivo] = []
        for doc_id, texto in con.execute(
            "SELECT id, texto FROM documentos WHERE natureza = 'dispositivo'"
        ):
            match = _ARTIGO_NO_TEXTO_RE.search(texto)
            if match is None:
                continue
            itens.append(
                _Dispositivo(
                    id=str(doc_id),
                    numero=match.group(1).lstrip("0") or "0",
                    diploma=diploma_do_documento(texto),
                )
            )
        return cls(itens)

    def reconhece(self, trecho: str) -> bool:
        return tipo_de(trecho) == "lei"

    def resolve_campos(self, numero: str, diploma: str | None) -> Resolucao:
        if not diploma:
            return Resolucao("incompleta")
        digitos = so_digitos(numero)
        if not digitos:
            return Resolucao("incompleta")
        numero = digitos.lstrip("0") or "0"
        ids = [
            item.id
            for item in self.itens
            if item.numero == numero and item.diploma == diploma
        ]
        return por_quantidade(ids)

    def resolve(self, trecho: str) -> Resolucao:
        match = _ARTIGO_RE.search(trecho)
        if match is None:
            return Resolucao("incompleta")
        return self.resolve_campos(match.group(1), diploma_do_trecho(trecho))
