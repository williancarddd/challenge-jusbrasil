"""Estima a distribuição do resultado entre execuções idênticas.

O regulamento re-executa as submissões top-N e desclassifica se o score cair mais de 5%
em termos **relativos**. A regra é assimétrica: subir não penaliza. Logo o que importa
não é a dispersão média, é a cauda inferior — e reportar a melhor execução é justamente
o que maximiza a exposição a ela.

Este script roda N vezes a mesma configuração e responde duas perguntas:
  1. a variação observada cabe nos 5%?
  2. qual valor é seguro reportar, dado que a re-execução é um sorteio da distribuição?
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from cacador_alucinacoes.evaluation import run_once
from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.span_recovery import portuguese_tokenizer

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 50
LIMIT = 0.05
OUTPUT = Path("data/variance_runs.json")


def relative_drop(reported: float, observed: float) -> float:
    return (reported - observed) / reported if reported else 0.0


def describe(name: str, values: list[float], as_percent: bool = True) -> None:
    scale = 100 if as_percent else 1
    unit = "%" if as_percent else ""
    ordered = sorted(values)
    print(
        f"{name:<22} "
        f"min {scale * ordered[0]:.1f}{unit}  "
        f"p10 {scale * ordered[int(0.10 * len(ordered))]:.1f}{unit}  "
        f"mediana {scale * statistics.median(ordered):.1f}{unit}  "
        f"média {scale * statistics.mean(ordered):.1f}{unit}  "
        f"max {scale * ordered[-1]:.1f}{unit}  "
        f"dp {scale * statistics.pstdev(ordered):.2f}{unit}"
    )


def main() -> None:
    nlp = portuguese_tokenizer()
    goldenset = load_goldenset()
    documents = load_documents()

    results = []
    for index in range(1, RUNS + 1):
        result = run_once(nlp=nlp, goldenset=goldenset, documents=documents)
        results.append(result)
        print(
            f"  execução {index:>2}/{RUNS}: "
            f"recall {result.hits}/225  "
            f"score-proxy {100 * result.weighted_score:.2f}%  "
            f"precisão {100 * result.precision:.1f}%  "
            f"{result.seconds:.0f}s",
            flush=True,
        )

    scores = [r.weighted_score for r in results]
    recalls = [float(r.hits) for r in results]

    print()
    print("=" * 78)
    print(f"DISTRIBUIÇÃO EM {RUNS} EXECUÇÕES IDÊNTICAS")
    print("=" * 78)
    describe("score ponderado", scores)
    describe("recall (citações)", recalls, as_percent=False)
    describe("precisão", [r.precision for r in results])
    describe("precisão do acordo", [r.agreement_precision for r in results])
    describe("spans em acordo", [float(r.agreed) for r in results], as_percent=False)
    print(f"{'tempo':<22} mediana {statistics.median(r.seconds for r in results):.0f}s")

    print()
    print("=" * 78)
    print("RISCO DE REPRODUTIBILIDADE — queda relativa contra o limite de 5%")
    print("=" * 78)
    worst = min(scores)
    print(f"pior execução observada: {100 * worst:.2f}%\n")
    print(f"{'se reportar...':<26} {'queda no pior caso':<22} {'veredito'}")
    candidates = {
        "o máximo": max(scores),
        "a média": statistics.mean(scores),
        "a mediana": statistics.median(scores),
        "o p10": sorted(scores)[int(0.10 * len(scores))],
        "o mínimo": worst,
    }
    for label, reported in candidates.items():
        drop = relative_drop(reported, worst)
        verdict = "passa" if drop <= LIMIT else "DESCLASSIFICA"
        print(f"{label:<26} {100 * drop:>6.2f}%{'':<15} {verdict}")

    spread = (max(scores) - min(scores)) / max(scores) if max(scores) else 0
    print()
    print(f"amplitude relativa da distribuição: {100 * spread:.2f}%")
    print(
        "  (é o pior caso possível: reportar o topo e ser re-executado no fundo)"
    )

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            [
                {
                    "hits": r.hits,
                    "predictions": r.predictions,
                    "weighted_score": r.weighted_score,
                    "precision": r.precision,
                    "hits_by_level": r.hits_by_level,
                    "seconds": r.seconds,
                    "rewritten": r.rewritten,
                    "request_errors": r.request_errors,
                    "agreed": r.agreed,
                    "agreed_correct": r.agreed_correct,
                }
                for r in results
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nbruto salvo em {OUTPUT}")


if __name__ == "__main__":
    main()
