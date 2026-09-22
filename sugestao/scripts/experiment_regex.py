"""Banco de ensaio do ramo determinístico — NÃO altera o pipeline.

Testa variantes do extrator por regex sem tocar em `regex_extraction.py`. Cada variante
soma uma mudança à anterior, para separar a contribuição de cada uma.

Roda em segundos, só CPU, sem a LLM no ar. E é **determinístico**: o regex não varia
entre execuções, então cada número aqui é exato, não uma amostra.

Uso: `uv run python scripts/experiment_regex.py`
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.preprocessing import usable_blocks
from cacador_alucinacoes.regex_extraction import (
    PRECEDENT_SUMMARY,
    VAGUE_STATUTE,
    _APPEAL_CHAIN,
    _APPEAL_CLASSES,
    _CNJ_NUMBER,
    _GROUPED_NUMBER,
    _STATE,
    _STATUTE_TAIL,
    _TRIM,
)
from cacador_alucinacoes.regex_extraction import CASE_LAW_WITH_NUMBER as CURRENT_CASE_LAW
from cacador_alucinacoes.regex_extraction import STATUTE as CURRENT_STATUTE
from cacador_alucinacoes.regex_extraction import VAGUE_CASE_LAW as CURRENT_VAGUE
from cacador_alucinacoes.span_recovery import intersection_over_union

IOU_THRESHOLD = 0.5


# ---------------------------------------------------------------- as mudanças

# (a) A cadeia recursal também vem por extenso: o gabarito traz "Embargos de Declaração
#     no Agravo Interno no Agravo em Recurso Especial nº 1904603/TO", e a cadeia atual
#     só cobre as siglas.
CHAIN_SPELLED_OUT = (
    r"(?:(?:EDcl|EDv|ED|AgInt|AgRg|AgR|"
    r"Embargos\s+de\s+Declara(?:ç|c)(?:ã|a)o|Embargos\s+de\s+Diverg(?:ê|e)ncia|"
    r"Agravo\s+Interno|Agravo\s+Regimental)"
    r"\s+n?[oa]s?\s+)*"
)

# (b) O rabo do dispositivo parava em 60 caracteres e não atravessava parágrafo: o
#     gabarito continua com "§ 1º-A, da CLT" e "da Lei Complementar nº 64/1990".
STATUTE_TAIL_WIDER = r"(?:[^.,;\n]|\.(?=\d))"
STATUTE_WIDER = re.compile(
    r"art(?:igo)?\.?\s*\d+(?:\.\d+)*[ºo°]?"
    r"(?:\s*,?\s*[IVXLC]+)?"
    r"(?:\s*,?\s*§\s*\d+[ºo°]?(?:\s*-\s*[A-Z])?)?"
    r"(?:\s*,?\s*(?:inciso|al(?:í|i)nea)\s*\S+)?"
    rf"(?:\s*,?\s*d[oae]\s+{STATUTE_TAIL_WIDER}{{2,90}})?",
    re.IGNORECASE,
)

# (c) O número CNJ vem partido pelo ruído do nível 2: hífen duplicado, quebra de linha e
#     espaço no meio ("7220273--\n23.2018.7.00.0000/ RS").
CNJ_NOISY = r"\d{1,7}\s*-{0,2}\s*\d{2}\s*\.\s*\d{4}\s*\.\s*\d\s*\.\s*\d{2}\s*\.\s*\d{4}"

# (d) O rabo do padrão vago leva o comentário junto ("jurisprudência pacífica desta
#     Corte, de resto amplamente conhecida no foro"). 80 -> 25 corta antes da vírgula
#     que abre o comentário.
def vague_with_tail(size: int) -> re.Pattern:
    return re.compile(
        r"(?:julgado|precedente|ac(?:ó|o)rd(?:ã|a)o|entendimento|Reclama(?:ç|c)(?:ã|a)o|"
        r"Agravo\s+em\s+Recurso\s+Especial|jurisprud(?:ê|e)ncia)\b[^.]{0,60}?"
        r"(?:do\s+ST[FMJ]|desta\s+Corte|sumulad[oa]|pac(?:í|i)fica|"
        rf"proferid[oa]\s+em\s+\d{{4}}|de\s+\d{{4}})[^.]{{0,{size}}}",
        re.IGNORECASE,
    )


def case_law(chain: str, cnj: str) -> re.Pattern:
    return re.compile(
        rf"{chain}(?:{_APPEAL_CLASSES})\s*(?:n[ºo°.]*\s*)?(?:{cnj}|{_GROUPED_NUMBER}){_STATE}",
        re.IGNORECASE,
    )


# ---------------------------------------------------------------- a avaliação


@dataclass(frozen=True)
class Variant:
    label: str
    patterns: tuple
    on_normalized: bool


def trimmed(text: str, start: int, end: int):
    while end > start and text[end - 1] in _TRIM:
        end -= 1
    while start < end and text[start] in _TRIM:
        start += 1
    return (start, end) if end - start >= 3 else None


def spans_for(document: str, variant: Variant) -> list[tuple[int, int]]:
    """Acha spans, do texto cru ou do texto normalizado do bloco.

    A normalização é 1:1, então um offset dentro do bloco normalizado somado ao
    `start` do bloco vale no arquivo original sem conversão nenhuma.
    """
    found = set()
    if variant.on_normalized:
        for block in usable_blocks(document):
            for pattern in variant.patterns:
                for match in pattern.finditer(block.text):
                    span = trimmed(block.text, match.start(), match.end())
                    if span:
                        found.add(
                            (block.absolute_position(span[0]), block.absolute_position(span[1]))
                        )
    else:
        windows = [(b.start, b.end) for b in usable_blocks(document)]
        for pattern in variant.patterns:
            for match in pattern.finditer(document):
                span = trimmed(document, match.start(), match.end())
                if span and any(lo <= span[0] and span[1] <= hi for lo, hi in windows):
                    found.add(span)
    return sorted(found)


def score(variant: Variant, documents, expected) -> tuple[float, float, int, int]:
    hits = predictions = boundary = 0
    for document_id, document in documents.items():
        spans = spans_for(document, variant)
        predictions += len(spans)
        used = set()
        for citation in expected[document_id]:
            best = None
            for index, span in enumerate(spans):
                if index in used:
                    continue
                value = intersection_over_union(span, (citation.start, citation.end))
                if value >= IOU_THRESHOLD and (best is None or value > best[1]):
                    best = (index, value)
            if best is not None:
                used.add(best[0])
                hits += 1
        for index, span in enumerate(spans):
            if index in used:
                continue
            if any(
                intersection_over_union(span, (c.start, c.end)) > 0
                for c in expected[document_id]
            ):
                boundary += 1
    precision = hits / predictions if predictions else 0.0
    return precision, hits / 225, predictions - hits, boundary


def main() -> None:
    documents = load_documents()
    expected = defaultdict(list)
    for citation in load_goldenset():
        expected[citation.document_id].append(citation)

    current = (CURRENT_CASE_LAW, PRECEDENT_SUMMARY, CURRENT_STATUTE, CURRENT_VAGUE, VAGUE_STATUTE)
    chain_only = case_law(CHAIN_SPELLED_OUT, _CNJ_NUMBER)
    chain_and_cnj = case_law(CHAIN_SPELLED_OUT, CNJ_NOISY)

    variants = [
        Variant("atual (texto cru)", current, False),
        Variant("+ sobre texto normalizado", current, True),
        Variant(
            "+ cadeia recursal por extenso",
            (chain_only, PRECEDENT_SUMMARY, CURRENT_STATUTE, CURRENT_VAGUE, VAGUE_STATUTE),
            True,
        ),
        Variant(
            "+ rabo do dispositivo (§, 90)",
            (chain_only, PRECEDENT_SUMMARY, STATUTE_WIDER, CURRENT_VAGUE, VAGUE_STATUTE),
            True,
        ),
        Variant(
            "+ CNJ tolerante a ruído",
            (chain_and_cnj, PRECEDENT_SUMMARY, STATUTE_WIDER, CURRENT_VAGUE, VAGUE_STATUTE),
            True,
        ),
    ]
    for size in (50, 25, 10):
        variants.append(
            Variant(
                f"+ rabo do vago = {size}",
                (
                    chain_and_cnj,
                    PRECEDENT_SUMMARY,
                    STATUTE_WIDER,
                    vague_with_tail(size),
                    VAGUE_STATUTE,
                ),
                True,
            )
        )

    print(f"{'variante':<32} {'P':>7} {'R':>7} {'F1':>7} {'FP':>5} {'borda':>7}")
    print("-" * 70)
    for variant in variants:
        precision, recall, false_positives, boundary = score(variant, documents, expected)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        print(
            f"{variant.label:<32} {precision:>7.3f} {recall:>7.3f} {f1:>7.3f} "
            f"{false_positives:>5} {boundary:>7}"
        )


if __name__ == "__main__":
    main()
