"""Isola o efeito da decodificação: amostragem e modo de raciocínio, um de cada vez.

Ligar `--generation-config=vllm` e desligar o raciocínio ao mesmo tempo derrubou o
recall de ~182 para ~172 sem dizer qual das duas mudanças foi responsável. Aqui cada
variável anda sozinha, e cada configuração roda duas vezes para separar efeito de ruído.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import httpx

from cacador_alucinacoes.extraction import (
    build_request,
    default_workers,
    parse_response,
    verify,
)
from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.preprocessing import usable_blocks
from cacador_alucinacoes.span_recovery import (
    intersection_over_union,
    locate,
    portuguese_tokenizer,
)

ENDPOINT = "http://localhost:8000/v1/chat/completions"
IOU_THRESHOLD = 0.5

GREEDY = {"temperature": 0.0, "top_p": 1.0, "top_k": -1, "seed": 0}
QWEN_DEFAULT = {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "seed": 0}

SETTINGS = [
    ("greedy, sem raciocínio", GREEDY, False),
    ("greedy, com raciocínio", GREEDY, True),
    ("amostrado (0.6), sem raciocínio", QWEN_DEFAULT, False),
    ("amostrado (0.6), com raciocínio", QWEN_DEFAULT, True),
]


def score(sampling: dict, thinking: bool, nlp, documents, expected) -> tuple[int, int]:
    def call(args):
        block, client = args
        payload = build_request(block, sampling=sampling, thinking=thinking)
        # O raciocínio do Qwen3 consome centenas de tokens antes do JSON; com 800 a
        # resposta é truncada no meio da string e não parseia.
        payload["max_tokens"] = 3000 if thinking else 800
        response = client.post(ENDPOINT, json=payload)
        response.raise_for_status()
        try:
            candidates = parse_response(response.json())
        except (ValueError, KeyError):
            candidates = []  # resposta truncada conta como bloco sem citação
        return block, verify(block, candidates)

    jobs, owners = [], []
    with httpx.Client(timeout=300) as client:
        for document_id, document in documents.items():
            for block in usable_blocks(document):
                jobs.append((block, client))
                owners.append(document_id)
        with ThreadPoolExecutor(max_workers=default_workers()) as pool:
            results = list(pool.map(call, jobs))

    found = defaultdict(list)
    for (block, extraction), document_id in zip(results, owners):
        texts = sorted({c.text for c in extraction.verified})
        if texts:
            located, _ = locate(block, texts, nlp)
            found[document_id].extend(located)

    hits = predictions = 0
    for document_id, citations in expected.items():
        candidates = found[document_id]
        predictions += len(candidates)
        used = set()
        for citation in citations:
            best = None
            for index, candidate in enumerate(candidates):
                if index in used:
                    continue
                value = intersection_over_union(
                    (candidate.start, candidate.end), (citation.start, citation.end)
                )
                if value >= IOU_THRESHOLD and (best is None or value > best[1]):
                    best = (index, value)
            if best is not None:
                used.add(best[0])
                hits += 1
    return hits, predictions


def main() -> None:
    goldenset = load_goldenset()
    documents = load_documents()
    nlp = portuguese_tokenizer()
    expected = defaultdict(list)
    for citation in goldenset:
        expected[citation.document_id].append(citation)

    print(f"{'configuração':<34} {'recall (2 execuções)':<26} precisão")
    for label, sampling, thinking in SETTINGS:
        runs = [score(sampling, thinking, nlp, documents, expected) for _ in range(2)]
        recalls = " / ".join(f"{hits}" for hits, _ in runs)
        precisions = " / ".join(
            f"{100 * hits / predictions:.0f}%" if predictions else "-"
            for hits, predictions in runs
        )
        print(f"{label:<34} {recalls + ' de 225':<26} {precisions}")


if __name__ == "__main__":
    main()
