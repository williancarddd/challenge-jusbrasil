from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from challenge_jusbrasil.resolver.comum import Resolucao, sem_acento, sem_datas, so_digitos

_CNJ_RE = re.compile(
    r"\d{1,7}\s*-\s*\d{2}\s*\.\s*\d{4}\s*\.\s*\d\s*\.\s*\d{2}\s*\.\s*\d{4}"
)
_BLOCO_RE = re.compile(r"\d(?:[\d.\-/]\s*)+\d|\d{4,}")
_BLOCO_CITACAO_RE = re.compile(
    r"\d(?:[\d.\-/\s]|[OolISgGB](?=[\d.\-/\s]|$))*(?:\d|[OolISgGB](?=[\d.\-/\s]|$))"
)
_OCR_DIGITOS = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "l": "1",
        "I": "1",
        "i": "1",
        "S": "5",
        "g": "9",
        "G": "9",
        "B": "8",
    }
)
_IGNORAR_RELATOR = {"min", "ministro", "ministra", "des", "desembargador", "relator"}


@dataclass(frozen=True)
class _Candidato:
    id: str
    relator: str
    texto_len: int
    cabecalho: str


class ResolvedorAcordao:
    def __init__(self, indice: dict[str, list[_Candidato]]) -> None:
        self.indice = indice

    @classmethod
    def carregar(cls, con: sqlite3.Connection) -> ResolvedorAcordao:
        indice: dict[str, list[_Candidato]] = {}
        for doc_id, tribunal, relator, texto, texto_len in con.execute(
            "SELECT id, tribunal, relator, texto, texto_len FROM documentos WHERE natureza = 'acordao'"
        ):
            candidato = _Candidato(
                str(doc_id),
                relator or "",
                int(texto_len or len(texto)),
                sem_acento(texto[:240]).lower(),
            )
            for numero in _numeros_cabecalho(tribunal or "", texto):
                indice.setdefault(numero, []).append(candidato)
        return cls(indice)

    def resolve(self, trecho: str, contexto: str) -> Resolucao:
        sequencias = _sequencias(trecho)
        if not sequencias:
            return Resolucao("incompleta")
        candidatos: list[_Candidato] = []
        for numero in sequencias:
            candidatos.extend(self.indice.get(numero, []))
        return _desempatar(candidatos, contexto)


def _numeros_cabecalho(tribunal: str, texto: str) -> list[str]:
    if tribunal == "TST":
        numeros: list[str] = []
        primeiro = _CNJ_RE.search(texto[:8000])
        if primeiro:
            numeros.append(so_digitos(primeiro.group(0)))
        ancora = re.search(r"PROCESSO\s+N[ºO°.]?\s*[:\-]?\s*.{0,90}", texto, flags=re.IGNORECASE)
        if ancora:
            processo = _CNJ_RE.search(ancora.group(0))
            if processo:
                digitos = so_digitos(processo.group(0))
                if digitos not in numeros:
                    numeros.append(digitos)
        return numeros
    janela = sem_datas(texto[:500])
    limite = 2 if tribunal == "STJ" else 1
    numeros: list[str] = []
    for match in _BLOCO_RE.finditer(janela):
        digitos = so_digitos(match.group(0))
        if not _numero_util(digitos) or digitos in numeros:
            continue
        numeros.append(digitos)
        if len(numeros) >= limite:
            break
    return numeros


def _sequencias(trecho: str) -> list[str]:
    plano = sem_datas(trecho)
    saida: list[str] = []
    for match in _BLOCO_CITACAO_RE.finditer(plano):
        digitos = so_digitos(match.group(0).translate(_OCR_DIGITOS))
        if _numero_util(digitos) and digitos not in saida:
            saida.append(digitos)
    return saida


def _numero_util(digitos: str) -> bool:
    if len(digitos) < 4:
        return False
    return not re.fullmatch(r"(19|20)\d{2}", digitos)


def _mesmo_feito(lista: list[_Candidato]) -> _Candidato | None:
    maior = max(item.texto_len for item in lista)
    if maior <= 0:
        return None
    if any(item.texto_len < maior * 0.98 for item in lista):
        return None
    return max(lista, key=lambda item: (item.texto_len, int(item.id)))


def _desempatar(candidatos: list[_Candidato], contexto: str) -> Resolucao:
    por_id = {item.id: item for item in candidatos}
    lista = list(por_id.values())
    if not lista:
        return Resolucao("inventada")
    if len(lista) == 1:
        return Resolucao("real", lista[0].id)
    mesmo = _mesmo_feito(lista)
    if mesmo is not None:
        return Resolucao("real", mesmo.id)
    por_cabecalho = _por_cabecalho(lista, contexto)
    if por_cabecalho is not None:
        return Resolucao("real", por_cabecalho.id)
    ctx = sem_acento(contexto).lower()
    achados = [item for item in lista if _relator_no_contexto(item.relator, ctx)]
    if len(achados) == 1:
        return Resolucao("real", achados[0].id)
    return Resolucao("incompleta")


def _por_cabecalho(lista: list[_Candidato], contexto: str) -> _Candidato | None:
    tokens = set(re.findall(r"[a-z]{4,}", sem_acento(contexto).lower()))
    if not tokens:
        return None
    pontuados = [(len(tokens & set(re.findall(r"[a-z]{4,}", item.cabecalho))), item) for item in lista]
    melhor = max(pontuacao for pontuacao, _item in pontuados)
    if melhor == 0:
        return None
    escolhidos = [item for pontuacao, item in pontuados if pontuacao == melhor]
    if len(escolhidos) == 1:
        return escolhidos[0]
    return None


def _relator_no_contexto(relator: str, contexto: str) -> bool:
    partes = [
        parte
        for parte in sem_acento(relator).lower().split()
        if len(parte) > 3 and parte not in _IGNORAR_RELATOR
    ]
    return bool(partes) and any(parte in contexto for parte in partes)
