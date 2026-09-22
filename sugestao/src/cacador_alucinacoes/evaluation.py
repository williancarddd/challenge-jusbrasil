"""Uma execução completa da fase 1, medida contra o gabarito.

Separado dos scripts porque a mesma execução serve a dois propósitos: relatar o
resultado de uma rodada e alimentar o estudo de variância entre rodadas.
"""

from __future__ import annotations

import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import httpx

from cacador_alucinacoes.extraction import default_workers, extract
from cacador_alucinacoes.goldenset import Citation, load_documents, load_goldenset
from cacador_alucinacoes.hybrid import merge
from cacador_alucinacoes.regex_extraction import find
from cacador_alucinacoes.preprocessing import usable_blocks
from cacador_alucinacoes.span_recovery import (
    intersection_over_union,
    locate,
    portuguese_tokenizer,
)

IOU_THRESHOLD = 0.5


@dataclass(frozen=True)
class Result:
    blocks: int
    seconds: float
    request_errors: int
    rewritten: int
    hits: int
    predictions: int
    hits_by_level: dict[int, int] = field(default_factory=dict)
    total_by_level: dict[int, int] = field(default_factory=dict)
    # A faixa de acordo entre os dois ramos: é dela que sai a confiança calibrada.
    agreed: int = 0
    agreed_correct: int = 0

    @property
    def agreement_precision(self) -> float:
        return self.agreed_correct / self.agreed if self.agreed else 0.0

    @property
    def recall(self) -> float:
        wanted = sum(self.total_by_level.values())
        return self.hits / wanted if wanted else 0.0

    @property
    def precision(self) -> float:
        return self.hits / self.predictions if self.predictions else 0.0

    @property
    def weighted_score(self) -> float:
        """Proxy do score oficial: nível 2 pesa 2x, como na nota final.

        Não é o score do regulamento — falta a classificação, que é fase 2, e o bônus de
        calibração. Serve para estudar variação relativa com o peso certo entre níveis.
        """
        earned = sum(level * self.hits_by_level.get(level, 0) for level in (1, 2))
        possible = sum(level * self.total_by_level.get(level, 0) for level in (1, 2))
        return earned / possible if possible else 0.0


def _group_by_document(goldenset: list[Citation]) -> dict[str, list[Citation]]:
    grouped = defaultdict(list)
    for citation in goldenset:
        grouped[citation.document_id].append(citation)
    return grouped


def run_once(nlp=None, goldenset=None, documents=None) -> Result:
    """Roda os 26 documentos e alinha as predições ao gabarito por IoU >= 0,5.

    Os argumentos existem para reaproveitar tokenizador e dados entre execuções
    repetidas — carregá-los 50 vezes seria puro desperdício.
    """
    nlp = nlp or portuguese_tokenizer()
    goldenset = goldenset if goldenset is not None else load_goldenset()
    documents = documents if documents is not None else load_documents()
    expected = _group_by_document(goldenset)

    def call(args):
        block, client = args
        try:
            return block, extract(block, client), None
        except Exception as error:  # noqa: BLE001 - o erro vira linha do relatório
            return block, None, error

    jobs, owners = [], []
    with httpx.Client(timeout=300) as client:
        for document_id, document in documents.items():
            for block in usable_blocks(document):
                jobs.append((block, client))
                owners.append(document_id)
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=default_workers()) as pool:
            results = list(pool.map(call, jobs))
        elapsed = time.monotonic() - started

    found = defaultdict(list)
    rewritten = errors = 0
    for (block, extraction, error), document_id in zip(results, owners):
        if error is not None:
            errors += 1
            continue
        rewritten += extraction.transcription_failures
        texts = sorted({c.text for c in extraction.verified})
        if texts:
            located, _ = locate(block, texts, nlp)
            found[document_id].extend(located)

    hits_by_level: dict[int, int] = defaultdict(int)
    total_by_level: dict[int, int] = defaultdict(int)
    hits = predictions = agreed = agreed_correct = 0
    for document_id, citations in expected.items():
        # O ramo determinístico entra aqui: o que vai para a métrica é o híbrido, não a
        # saída da LLM sozinha.
        candidates = merge(found[document_id], find(documents[document_id]))
        predictions += len(candidates)
        used = set()
        for citation in citations:
            total_by_level[citation.level] += 1
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
                hits_by_level[citation.level] += 1
                hits += 1
        for index, candidate in enumerate(candidates):
            if candidate.agreed:
                agreed += 1
                agreed_correct += index in used

    return Result(
        blocks=len(jobs),
        seconds=elapsed,
        request_errors=errors,
        rewritten=rewritten,
        hits=hits,
        predictions=predictions,
        hits_by_level=dict(hits_by_level),
        total_by_level=dict(total_by_level),
        agreed=agreed,
        agreed_correct=agreed_correct,
    )
