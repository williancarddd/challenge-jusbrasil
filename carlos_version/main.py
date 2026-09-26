"""Executa o pipeline inteiro: .txt → citações classificadas → submission.csv.

    uv run main.py --data data/final --input data/final/txt

Na primeira execução baixa os pesos do modelo (revisão fixa) para `models/`. Depois
disso tudo roda offline: o vLLM é subido como subprocesso e derrubado no fim.

`--data` é a pasta com a base canônica (`desafio1_bracis.db`). Se ela trouxer também o
gabarito (`goldenset_offsets.csv`), a submissão é pontuada pela métrica oficial.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import httpx
import pandas as pd

from cacador_alucinacoes.extraction import default_workers, extract
from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.hybrid import Citation, merge
from cacador_alucinacoes.kaggle_metric import avaliar
from cacador_alucinacoes.llm_server import MODEL_DIR, ensure_weights, serving
from cacador_alucinacoes.preprocessing import usable_blocks
from cacador_alucinacoes.regex_extraction import find
from cacador_alucinacoes.resolution import Resolver, query_text
from cacador_alucinacoes.self_reference import drop_self_references
from cacador_alucinacoes.span_recovery import Found, locate, portuguese_tokenizer
from cacador_alucinacoes.submission import solution_frame, write_contract

DATABASE_NAME = "desafio1_bracis.db"
GOLDENSET_NAME = "goldenset_offsets.csv"

def recognise_with_llm(documents: dict[str, str]) -> dict[str, list[Found]]:
    """Uma passada da LLM sobre todos os blocos úteis, com o span recuperado no cru."""
    nlp = portuguese_tokenizer()
    jobs = [
        (document_id, block)
        for document_id, document in documents.items()
        for block in usable_blocks(document)
    ]
    # Timeout largo: as requisições esperam na fila atrás das poucas que o KV cache
    # comporta ao mesmo tempo, e 300 s já estourou numa passada inteira.
    with httpx.Client(timeout=1800) as client, ThreadPoolExecutor(
        max_workers=default_workers()
    ) as pool:
        extractions = list(pool.map(lambda job: extract(job[1], client), jobs))

    found = defaultdict(list)
    for (document_id, block), extraction in zip(jobs, extractions):
        logprob = {c.text: c.logprob for c in extraction.verified}
        if logprob:
            located, _ = locate(block, sorted(logprob), nlp)
            found[document_id].extend(
                replace(span, confidence=logprob.get(span.text)) for span in located
            )
    return dict(found)


def resolve_all(document: str, citations: list[Citation], resolver: Resolver) -> list[Citation]:
    """Fase 2: classe, link e tipo; a confiança é a do reconhecimento."""
    out = []
    for citation in citations:
        # O span vai para a submissão como a fase 1 o entregou; o que se estende é só o
        # texto da consulta, quando o span cortou um número ao meio.
        found = resolver.resolve(query_text(document, citation.start, citation.end))
        out.append(
            replace(
                citation,
                kind=found.kind,
                label=found.label,
                canonical_id=found.canonical_id,
                confidence=citation.recognition_confidence,
            )
        )
    return out


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline completo do Caça-Alucinações.")
    parser.add_argument("--data", type=Path, required=True, help="pasta com a base canônica")
    parser.add_argument("--input", type=Path, required=True, help="pasta com os .txt")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--model", type=Path, default=MODEL_DIR, help="pasta dos pesos")
    return parser.parse_args()


def main() -> None:
    args = arguments()
    database = args.data / DATABASE_NAME
    if not database.exists():
        sys.exit(f"base canônica não encontrada em {database}")
    documents = load_documents(args.input)
    if not documents:
        sys.exit(f"nenhum .txt em {args.input}")

    contract_dir = args.output / "contrato"
    submission = args.output / "submission.csv"
    contract_dir.mkdir(parents=True, exist_ok=True)
    for stale in contract_dir.glob("*.json"):
        stale.unlink()

    started = time.monotonic()
    with serving(ensure_weights(args.model), args.output / "vllm.log"):
        ready = time.monotonic()
        llm_spans = recognise_with_llm(documents)
    recognised_at = time.monotonic()

    resolver = Resolver(database=database)
    total = 0
    for document_id, document in documents.items():
        recognised = drop_self_references(
            document, merge(llm_spans.get(document_id, []), find(document))
        )
        citations = resolve_all(document, recognised, resolver)
        total += len(citations)
        write_contract(contract_dir, document_id, document, citations)

    converter = subprocess.run(
        [sys.executable, "-m", "cacador_alucinacoes.json_to_submission",
         str(contract_dir), str(submission)],
        capture_output=True, text=True,
    )
    if converter.returncode != 0:
        sys.exit(f"json_to_submission falhou:\n{converter.stderr}")
    finished = time.monotonic()

    count = len(documents)
    print(f"\n{count} documentos, {total} citações → {submission}")
    print(f"partida do vLLM:   {ready - started:7.1f} s")
    print(f"LLM (fase 1):      {recognised_at - ready:7.1f} s")
    print(f"regex + fase 2:    {finished - recognised_at:7.1f} s")
    print(f"total:             {finished - started:7.1f} s  "
          f"= {(finished - started) / count:.1f} s/documento (limite 60)")

    goldenset_path = args.data / GOLDENSET_NAME
    if goldenset_path.exists():
        report = avaliar(solution_frame(load_goldenset(goldenset_path)), pd.read_csv(submission))
        for level, result in sorted(report["niveis"].items()):
            print(f"nível {level}: macro-F1 {result['macro_f1']:.4f}  score {result['score']:.4f}")
        print(f"score_final = {report['score_final']:.4f}  (máximo 1,1000)")


if __name__ == "__main__":
    main()
