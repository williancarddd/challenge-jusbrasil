"""Banco de ensaio da fusão — NÃO altera o pipeline.

A pergunta: quando regex e LLM cobrem a mesma citação com sobreposição ABAIXO do
limiar, hoje eles não pareiam e viram duas predições. Uma acerta, a outra é falso
positivo automático. Absorver qualquer sobreposição resolveria isso, mas muda o
significado de `agreed` — passaria a ser "os dois viram algo aqui" em vez de "os dois
concordam na borda", e é esse acordo que hoje sustenta a faixa de confiança 1,000.

A LLM roda **uma vez** e a saída fica em cache. Todas as variantes são avaliadas sobre
essa mesma saída, então a comparação entre elas é exata — a variância da LLM não entra.

Uso: `uv run python scripts/experiment_merge.py [--refresh]`
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from cacador_alucinacoes.extraction import default_workers, extract
from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.preprocessing import usable_blocks
from cacador_alucinacoes.regex_extraction import find
from cacador_alucinacoes.span_recovery import (
    Found,
    intersection_over_union,
    locate,
    portuguese_tokenizer,
)

CACHE = Path("data/llm_spans_cache.json")
IOU_THRESHOLD = 0.5


def capture(documents) -> dict[str, list[dict]]:
    """Uma passada da LLM sobre os 26 documentos, guardada em disco."""
    nlp = portuguese_tokenizer()

    def call(args):
        block, client = args
        return block, extract(block, client)

    jobs, owners = [], []
    with httpx.Client(timeout=300) as client:
        for document_id, document in documents.items():
            for block in usable_blocks(document):
                jobs.append((block, client))
                owners.append(document_id)
        with ThreadPoolExecutor(max_workers=default_workers()) as pool:
            results = list(pool.map(call, jobs))

    captured = defaultdict(list)
    for (block, extraction), document_id in zip(results, owners):
        confidence_of = {c.text: c.confidence for c in extraction.verified}
        texts = sorted(confidence_of)
        if not texts:
            continue
        located, _ = locate(block, texts, nlp)
        for span in located:
            captured[document_id].append(
                {
                    "start": span.start,
                    "end": span.end,
                    "text": span.text,
                    "block_index": span.block_index,
                    "confidence": confidence_of.get(span.text, 1.0),
                }
            )
    return dict(captured)


def merge_variant(llm, regex, threshold: float, keep: str):
    """Fusão parametrizada: limiar de pareamento e qual span sobrevive.

    `keep` decide o span quando os dois pareiam: "llm", "longest" ou "shortest".
    """
    left = sorted(llm, key=lambda c: (c["start"], c["end"]))
    right = sorted(regex, key=lambda m: (m.start, m.end))
    out = []
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i], right[j]
        overlap = intersection_over_union((a["start"], a["end"]), (b.start, b.end))
        if overlap > 0 and overlap >= threshold:
            if keep == "llm":
                span = (a["start"], a["end"])
            elif keep == "longest":
                span = max(
                    (a["start"], a["end"]), (b.start, b.end), key=lambda s: s[1] - s[0]
                )
            else:
                span = min(
                    (a["start"], a["end"]), (b.start, b.end), key=lambda s: s[1] - s[0]
                )
            out.append((span, True))
            i += 1
            j += 1
        elif (a["start"], a["end"]) <= (b.start, b.end):
            out.append(((a["start"], a["end"]), False))
            i += 1
        else:
            out.append(((b.start, b.end), False))
            j += 1
    out.extend((((a["start"], a["end"]), False) for a in left[i:]))
    out.extend((((b.start, b.end), False) for b in right[j:]))
    return sorted(out)


def score(cached, documents, expected, threshold: float, keep: str):
    hits = predictions = 0
    agreed_total = agreed_right = 0
    for document_id, document in documents.items():
        merged = merge_variant(cached.get(document_id, []), find(document), threshold, keep)
        predictions += len(merged)
        used = set()
        for citation in expected[document_id]:
            best = None
            for index, (span, _) in enumerate(merged):
                if index in used:
                    continue
                value = intersection_over_union(span, (citation.start, citation.end))
                if value >= IOU_THRESHOLD and (best is None or value > best[1]):
                    best = (index, value)
            if best is not None:
                used.add(best[0])
                hits += 1
        for index, (_, agreed) in enumerate(merged):
            if agreed:
                agreed_total += 1
                agreed_right += index in used
    precision = hits / predictions if predictions else 0.0
    recall = hits / 225
    tier = agreed_right / agreed_total if agreed_total else 0.0
    return precision, recall, predictions - hits, agreed_total, tier


def main() -> None:
    documents = load_documents()
    expected = defaultdict(list)
    for citation in load_goldenset():
        expected[citation.document_id].append(citation)

    if CACHE.exists() and "--refresh" not in sys.argv:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        print(f"usando cache de {CACHE} (--refresh para recapturar)\n")
    else:
        print("capturando uma passada da LLM...", flush=True)
        cached = capture(documents)
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cached, indent=1), encoding="utf-8")
        print(f"cache salvo em {CACHE}\n")

    print(f"{'variante':<40} {'P':>7} {'R':>7} {'F1':>7} {'FP':>5} {'acordo':>8} {'prec.':>7}")
    print("-" * 84)
    variants = [
        ("atual (limiar 0,5, span da LLM)", 0.5, "llm"),
        ("limiar 0,3", 0.3, "llm"),
        ("limiar 0,1", 0.1, "llm"),
        ("absorve qualquer sobreposição", 0.0, "llm"),
        ("absorve, mantém o mais longo", 0.0, "longest"),
        ("absorve, mantém o mais curto", 0.0, "shortest"),
    ]
    for label, threshold, keep in variants:
        precision, recall, false_positives, agreed, tier = score(
            cached, documents, expected, threshold, keep
        )
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        print(
            f"{label:<40} {precision:>7.3f} {recall:>7.3f} {f1:>7.3f} "
            f"{false_positives:>5} {agreed:>8} {tier:>7.3f}"
        )


if __name__ == "__main__":
    main()
