"""Pré-processamento da fase 1: partir o documento em blocos ancorados e normalizar.

Regra que governa o módulo inteiro: **nenhuma transformação pode alterar os spans**.
O gabarito cobra `inicio`/`fim` em codepoints do arquivo cru, então toda normalização
aqui é 1:1 — mesmo número de codepoints na entrada e na saída — e o offset de um trecho
no texto normalizado vale, sem conversão, no texto original.

Quem quiser aplicar transformação que mude comprimento (juntar `1.741. 784`, expandir
abreviação) faz isso na fase 2, sobre a citação já extraída, onde não há span a preservar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Separador de bloco. São 360 ocorrências de `\n\n` e 26 de `\n\n\n` nos 26 documentos —
# `split("\n\n")` literal deixaria um `\n` órfão na cabeça de 26 blocos.
BLOCK_SEPARATOR = re.compile(r"\n{2,}")

# Índices tratados como preâmbulo. O predicado de descarte só é consultado nestes;
# nunca é usado como detector solto sobre o documento (aplicado globalmente ele
# dispararia em 186 dos 412 blocos e comeria citações do corpo).
PREAMBLE_INDICES = (0, 1)

# Substituições 1:1 sem contraindicação: unificam caractere invisível ou visualmente
# quase idêntico, sem apagar sinal que a LLM possa usar.
SAFE_TRANSLATION = str.maketrans(
    {
        " ": " ",  # espaço não-quebrável
        "°": "º",  # ° (grau) -> º (ordinal); o gabarito usa os dois
        "—": "-",  # travessão
        "–": "-",  # meia-risca
    }
)

_KEY_VALUE_LINE = re.compile(r"^[^:\n]{1,50}:\s*\S")
_KEY_NUMBER_LINE = re.compile(
    r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ]{0,30}n[ºo°.]\s*\S", re.IGNORECASE
)


class SpanShifted(ValueError):
    """Uma normalização mudou o comprimento do texto e invalidaria os offsets."""


@dataclass(frozen=True)
class Block:
    """Um bloco do documento, ancorado no texto original.

    Invariante: ``len(text) == end - start``. É ela que permite somar um offset obtido
    dentro de `text` ao `start` e obter a posição no arquivo cru.
    """

    index: int
    start: int
    end: int
    text: str
    discarded: bool

    def __post_init__(self) -> None:
        if len(self.text) != self.end - self.start:
            raise SpanShifted(
                f"bloco {self.index}: texto tem {len(self.text)} codepoints, "
                f"mas o span cobre {self.end - self.start}"
            )

    def absolute_position(self, local_offset: int) -> int:
        """Converte um offset dentro de `text` para posição no documento original."""
        return self.start + local_offset


def _guard_length(original: str, transformed: str, label: str) -> str:
    if len(transformed) != len(original):
        raise SpanShifted(
            f"{label} mudou o comprimento ({len(original)} -> {len(transformed)}); "
            "isso quebraria os offsets"
        )
    return transformed


def normalize(text: str) -> str:
    """Normalização segura: caracteres equivalentes e quebra de linha simples.

    Dentro de um bloco toda quebra de linha é simples — as duplas viraram separador —
    então trocá-las por espaço não apaga limite de parágrafo nenhum.
    """
    result = text.translate(SAFE_TRANSLATION).replace("\n", " ")
    return _guard_length(text, result, "normalize")


def strip_accents(text: str) -> str:
    """Normalização opcional: tira acento mantendo 1:1.

    Desligada por padrão. Neutraliza o til espúrio do nível 2 (`Magãlhães` e
    `Magalhães` colidem), mas achata 15% das ocorrências de palavra do corpus para
    consertar ruído em 2,8% das formas. A decisão depende de ablação medindo recall
    por nível, não de argumento.
    """
    decomposed = unicodedata.normalize("NFD", text)
    result = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return _guard_length(text, result, "strip_accents")


def uppercase_predominates(text: str) -> bool:
    """Assinatura do bloco de endereçamento."""
    letters = [c for c in text if c.isalpha() and c not in "ºª°"]
    if not letters:
        return False
    return sum(c.isupper() for c in letters) > sum(c.islower() for c in letters)


def key_value_predominates(text: str) -> bool:
    """Assinatura do bloco de dados do processo.

    Duas formas de linha convivem: `Rótulo: valor` (`Apelante: FULANO`) e
    `Rótulo nº valor` (`Autos nº 8416083-51...`). Predominância, não unanimidade —
    exigir que todas as linhas casem falha nos três memoriais, onde aparece um
    `Sessão de julgamento designada para a pauta subsequente` solto.

    Roda sobre o texto CRU do bloco, antes de `\\n` virar espaço.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return False
    matching = sum(
        1
        for line in lines
        if _KEY_VALUE_LINE.match(line) or _KEY_NUMBER_LINE.match(line)
    )
    return matching > len(lines) / 2


def is_preamble(text: str) -> bool:
    """Se o bloco tem cara de endereçamento ou de ficha de processo."""
    return uppercase_predominates(text) or key_value_predominates(text)


def _block_spans(document: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    position = 0
    for separator in BLOCK_SEPARATOR.finditer(document):
        if separator.start() > position:
            spans.append((position, separator.start()))
        position = separator.end()
    if position < len(document):
        spans.append((position, len(document)))
    return [(start, end) for start, end in spans if document[start:end].strip()]


def blocks(document: str, *, normalization=normalize) -> list[Block]:
    """Parte o documento em blocos ancorados, marcando o preâmbulo como descartado.

    Devolve todos os blocos, inclusive os descartados — nada some em silêncio, e quem
    chama pode auditar o que foi cortado. O descarte é conjunção de posição e
    assinatura: um bloco de índice 0 ou 1 que não pareça preâmbulo é preservado, o que
    faz o erro cair do lado da precisão em vez do recall.
    """
    result: list[Block] = []
    for index, (start, end) in enumerate(_block_spans(document)):
        raw = document[start:end]
        discarded = index in PREAMBLE_INDICES and is_preamble(raw)
        result.append(
            Block(
                index=index,
                start=start,
                end=end,
                text=normalization(raw),
                discarded=discarded,
            )
        )
    return result


def usable_blocks(document: str, *, normalization=normalize) -> list[Block]:
    """Só os blocos que vão para a LLM."""
    return [b for b in blocks(document, normalization=normalization) if not b.discarded]
