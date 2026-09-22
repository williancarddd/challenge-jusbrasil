"""Diagnostica o híbrido: o que ele perde e o que ele inventa.

Duas decisões de desenho aqui:

**Roda N vezes.** A execução não é determinística, então um erro visto uma vez pode ser
sorte. O relatório separa o que aparece em TODAS as execuções — problema estrutural, vale
atacar — do que aparece em algumas — instabilidade, que se ataca de outro jeito.

**Separa falso positivo por natureza.** Um span que toca uma citação do gabarito é erro
de borda; um que não toca nada é invenção. São problemas diferentes: o primeiro custa
recall e precisão ao mesmo tempo, o segundo só precisão.

Uso: `uv run python scripts/diagnose_phase1.py [execuções]`
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import httpx

from cacador_alucinacoes.extraction import default_workers, extract
from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.hybrid import merge
from cacador_alucinacoes.preprocessing import usable_blocks
from cacador_alucinacoes.regex_extraction import find
from cacador_alucinacoes.span_recovery import (
    intersection_over_union,
    locate,
    portuguese_tokenizer,
)

IOU_THRESHOLD = 0.5


def origin(citation) -> str:
    if citation.agreed:
        return "acordo"
    return "só LLM" if citation.from_llm else "só regex"


def one_run(nlp, documents, expected):
    """Devolve (perdidas, falsos_positivos) de uma execução do híbrido."""

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

    llm = defaultdict(list)
    for (block, extraction), document_id in zip(results, owners):
        texts = sorted({c.text for c in extraction.verified})
        if texts:
            located, _ = locate(block, texts, nlp)
            llm[document_id].extend(located)

    missed, false_positives = [], []
    for document_id, citations in expected.items():
        merged = merge(llm[document_id], find(documents[document_id]))
        used = set()
        for citation in citations:
            best = None
            for index, candidate in enumerate(merged):
                if index in used:
                    continue
                value = intersection_over_union(
                    (candidate.start, candidate.end), (citation.start, citation.end)
                )
                if value >= IOU_THRESHOLD and (best is None or value > best[1]):
                    best = (index, value)
            if best is None:
                nearest = max(
                    (
                        intersection_over_union(
                            (c.start, c.end), (citation.start, citation.end)
                        )
                        for c in merged
                    ),
                    default=0.0,
                )
                missed.append((citation, nearest))
            else:
                used.add(best[0])
        for index, candidate in enumerate(merged):
            if index in used:
                continue
            touching = max(
                (
                    intersection_over_union(
                        (candidate.start, candidate.end), (c.start, c.end)
                    )
                    for c in citations
                ),
                default=0.0,
            )
            false_positives.append((document_id, candidate, touching))
    return missed, false_positives


def main() -> None:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    nlp = portuguese_tokenizer()
    goldenset = load_goldenset()
    documents = load_documents()
    expected = defaultdict(list)
    for citation in goldenset:
        expected[citation.document_id].append(citation)

    missed_count: Counter = Counter()
    missed_detail = {}
    fp_count: Counter = Counter()
    fp_detail = {}

    for index in range(runs):
        missed, false_positives = one_run(nlp, documents, expected)
        for citation, nearest in missed:
            key = (citation.document_id, citation.citation_id)
            missed_count[key] += 1
            missed_detail[key] = (citation, nearest)
        for document_id, candidate, touching in false_positives:
            key = (document_id, candidate.text)
            fp_count[key] += 1
            fp_detail[key] = (candidate, touching)
        print(
            f"  execução {index + 1}/{runs}: "
            f"{len(missed)} perdidas, {len(false_positives)} falsos positivos",
            flush=True,
        )

    def section(title: str) -> None:
        print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")

    stable_missed = [k for k, n in missed_count.items() if n == runs]
    section(
        f"PERDIDAS EM TODAS AS {runs} EXECUÇÕES: {len(stable_missed)}"
        f"   (intermitentes: {len(missed_count) - len(stable_missed)})"
    )
    citations = [missed_detail[k] for k in stable_missed]
    print("por classe:", dict(Counter(c.label for c, _ in citations)))
    print("por nível: ", dict(Counter(c.level for c, _ in citations)))
    print()
    for citation, nearest in sorted(citations, key=lambda t: -t[1]):
        reason = (
            f"borda errada, IoU={nearest:.2f}" if nearest > 0 else "ninguém viu"
        )
        print(
            f"  n{citation.level} {citation.document_id:<12} {citation.label:<11}"
            f" {reason:<24} {citation.excerpt[:50]!r}"
        )

    stable_fp = [k for k, n in fp_count.items() if n == runs]
    boundary = [k for k in stable_fp if fp_detail[k][1] > 0]
    invented = [k for k in stable_fp if fp_detail[k][1] == 0]
    section(
        f"FALSOS POSITIVOS EM TODAS AS {runs} EXECUÇÕES: {len(stable_fp)}"
        f"   (intermitentes: {len(fp_count) - len(stable_fp)})"
    )
    print(f"  borda errada sobre citação real: {len(boundary)}")
    print(f"  invenção pura:                   {len(invented)}")
    print(
        "  por origem:",
        dict(Counter(origin(fp_detail[k][0]) for k in stable_fp)),
    )

    print("\n--- borda errada (o span existe, o limite está errado)")
    for key in sorted(boundary, key=lambda k: -fp_detail[k][1]):
        candidate, touching = fp_detail[key]
        print(f"  IoU={touching:.2f} [{origin(candidate):<8}] {key[0]:<12} {key[1][:62]!r}")

    print("\n--- invenção pura (não toca citação nenhuma)")
    for key in sorted(invented):
        candidate, _ = fp_detail[key]
        print(f"  [{origin(candidate):<8}] {key[0]:<12} {key[1][:62]!r}")


if __name__ == "__main__":
    main()
