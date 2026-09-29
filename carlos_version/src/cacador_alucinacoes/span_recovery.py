"""Recuperação de span: da string que a LLM devolveu para o offset no arquivo cru.

A âncora é o `token.idx` do spaCy — offset em caracteres do token dentro do `Doc`.
Como o `Doc` é criado a partir do texto do bloco, e o texto do bloco é 1:1 com a fatia
original, `block.start + span.start_char` é a posição no arquivo original. Não há
aritmética de string em lugar nenhum: o offset vem da estrutura.

O casamento é exato de propósito. A LLM foi instruída a devolver texto raw, e se ela
desviar disso queremos saber — não queremos que uma tolerância disfarce o desvio e
produza span aproximado em silêncio.
"""

from __future__ import annotations

from dataclasses import dataclass

import spacy
from spacy.language import Language
from spacy.matcher import PhraseMatcher
from spacy.util import filter_spans

from cacador_alucinacoes.preprocessing import Block


@dataclass(frozen=True)
class Found:
    """Uma citação localizada, já em coordenadas do arquivo original."""

    start: int
    end: int
    text: str
    # Probabilidade que a LLM deu aos tokens do trecho (média geométrica). Nula quando o
    # span não veio da LLM ou a resposta não trouxe logprobs.
    confidence: float | None = None


def portuguese_tokenizer() -> Language:
    """Só o tokenizador — o `PhraseMatcher` com ORTH não precisa do resto do pipeline."""
    return spacy.blank("pt")


def locate(
    block: Block, candidates: list[str], nlp: Language
) -> tuple[list[Found], list[str]]:
    """Localiza cada candidato dentro do bloco.

    Devolve `(encontrados, nao_encontrados)`. O segundo elemento não é detalhe: uma
    string que a LLM produziu e que não existe no bloco significa que ela reescreveu o
    texto, e isso precisa ser visível em vez de descartado.

    Sobreposição é resolvida por `filter_spans` — o mais longo vence. É a convenção do
    gabarito, cujos trechos trazem a cadeia recursal inteira (`EDcl nos EDcl no AgInt no
    Agravo em Recurso Especial ...`), e é seguro porque as 225 citações nunca se cruzam
    nem se aninham.
    """
    document = nlp(block.text)
    matcher = PhraseMatcher(nlp.vocab)
    patterns = {}
    for candidate in candidates:
        if not candidate.strip():
            continue
        key = f"c{len(patterns)}"
        patterns[key] = candidate
        matcher.add(key, [nlp.make_doc(candidate)])

    spans = [document[start:end] for _, start, end in matcher(document)]
    matched_text = set()
    found = []
    for span in filter_spans(spans):
        matched_text.add(span.text)
        found.append(
            Found(
                start=block.absolute_position(span.start_char),
                end=block.absolute_position(span.end_char),
                text=span.text,
            )
        )

    missing = [c for c in candidates if c.strip() and c not in matched_text]
    return found, missing


def intersection_over_union(
    first: tuple[int, int], second: tuple[int, int]
) -> float:
    """IoU de dois spans. O alinhamento oficial exige >= 0,5."""
    start = max(first[0], second[0])
    end = min(first[1], second[1])
    overlap = max(0, end - start)
    union = (first[1] - first[0]) + (second[1] - second[0]) - overlap
    return overlap / union if union else 0.0
