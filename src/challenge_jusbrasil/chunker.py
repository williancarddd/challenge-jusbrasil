from __future__ import annotations

from dataclasses import dataclass

_SEPARADORES = ("\n\n", "\n", " ")


@dataclass(frozen=True)
class Janela:
    start: int
    text: str


class Chunker:
    def __init__(self, orcamento: int, sobreposicao: int = 200) -> None:
        if orcamento <= sobreposicao:
            raise ValueError("orcamento deve ser maior que a sobreposicao")
        self.orcamento = orcamento
        self.sobreposicao = sobreposicao

    def janelas(self, texto: str) -> list[Janela]:
        if len(texto) <= self.orcamento:
            return [Janela(0, texto)]
        saida: list[Janela] = []
        inicio = 0
        tamanho = len(texto)
        while inicio < tamanho:
            fim = min(inicio + self.orcamento, tamanho)
            if fim < tamanho:
                fim = self._corte(texto, inicio, fim)
            saida.append(Janela(inicio, texto[inicio:fim]))
            if fim >= tamanho:
                break
            proximo = max(fim - self.sobreposicao, inicio + 1)
            if proximo <= inicio:
                proximo = fim
            inicio = proximo
        return saida

    def _corte(self, texto: str, inicio: int, fim: int) -> int:
        trecho = texto[inicio:fim]
        minimo = max(self.sobreposicao + 1, len(trecho) // 2)
        for separador in _SEPARADORES:
            pos = trecho.rfind(separador)
            if pos >= minimo:
                return inicio + pos
        return fim
