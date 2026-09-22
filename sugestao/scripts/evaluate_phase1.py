"""Roda a fase 1 inteira sobre os 26 documentos e mede contra o gabarito.

Mede o que a fase 1 pode perder: recall dos spans no IoU >= 0,5. Precisão entra junto
porque distrator extraído é falso positivo, mas a assimetria importa — citação não
extraída não tem como ser classificada depois, enquanto falso positivo só custa precisão.

O nível 2 pesa 2x na nota oficial, então os números vêm separados por nível.
"""

from __future__ import annotations

import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import httpx

from cacador_alucinacoes.extraction import default_workers, extract
from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.preprocessing import usable_blocks
from cacador_alucinacoes.span_recovery import (
    intersection_over_union,
    locate,
    portuguese_tokenizer,
)

IOU_THRESHOLD = 0.5
# O batching contínuo do vLLM torna a saída dependente de como as requisições se
# agrupam, mesmo com temperature=0. `WORKERS=1` serializa e devolve reprodutibilidade,
# ao custo de ~53s por documento contra os 0,9s do paralelo.
WORKERS = default_workers()


def run_block(args):
    block, client = args
    try:
        return block, extract(block, client), None
    except Exception as error:  # noqa: BLE001 - queremos o erro no relatório
        return block, None, error


def main() -> None:
    goldenset = load_goldenset()
    documents = load_documents()
    nlp = portuguese_tokenizer()

    expected = defaultdict(list)
    for citation in goldenset:
        expected[citation.document_id].append(citation)

    jobs = []
    with httpx.Client(timeout=180) as client:
        for document_id, document in documents.items():
            for block in usable_blocks(document):
                jobs.append(((block, client), document_id))

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(run_block, [job for job, _ in jobs]))
        elapsed = time.monotonic() - started

    found_by_document = defaultdict(list)
    rewritten = 0
    failures = []
    for (block, extraction, error), (_, document_id) in zip(results, jobs):
        if error is not None:
            failures.append((document_id, block.index, repr(error)))
            continue
        rewritten += extraction.transcription_failures
        texts = sorted({c.text for c in extraction.verified})
        if texts:
            located, _ = locate(block, texts, nlp)
            found_by_document[document_id].extend(located)

    matched = defaultdict(int)
    total = defaultdict(int)
    predictions = 0
    hits = 0
    for document_id, citations in expected.items():
        found = found_by_document[document_id]
        predictions += len(found)
        used = set()
        for citation in citations:
            total[citation.level] += 1
            best = None
            for index, candidate in enumerate(found):
                if index in used:
                    continue
                score = intersection_over_union(
                    (candidate.start, candidate.end), (citation.start, citation.end)
                )
                if score >= IOU_THRESHOLD and (best is None or score > best[1]):
                    best = (index, score)
            if best is not None:
                used.add(best[0])
                matched[citation.level] += 1
                hits += 1

    print(f"blocos processados:     {len(jobs)}")
    print(f"tempo total:            {elapsed:.0f}s ({elapsed / 26:.1f}s por documento)")
    print(f"erros de requisição:    {len(failures)}")
    print(f"trechos reescritos:     {rewritten}  (não existiam no bloco)")
    print()
    for level in (1, 2):
        recovered, wanted = matched[level], total[level]
        share = 100 * recovered / wanted if wanted else 0
        print(f"nível {level} (peso {level}x):  recall {recovered}/{wanted}  ({share:.1f}%)")
    print(f"recall geral:           {hits}/{len(goldenset)}  ({100 * hits / len(goldenset):.1f}%)")
    print(f"predições emitidas:     {predictions}")
    if predictions:
        print(f"precisão:               {100 * hits / predictions:.1f}%")
    for failure in failures[:10]:
        print("   erro:", failure)


if __name__ == "__main__":
    main()
