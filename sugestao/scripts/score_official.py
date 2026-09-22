"""Fecha o laço: fase 1 -> contrato -> submission.csv -> score da métrica oficial.

Até aqui todo número do projeto era o proxy de recall da fase 1. Este script produz o
primeiro score pelo `kaggle_metric.py`, que é outra coisa: macro-F1 de três classes,
penalidade do erro grave (τ) e bônus de calibração, com o nível 2 pesando 2x.

`--control` troca a fase 2 por um piso: tudo rotulado `incompleta`, sem resolução.
`incompleta` é a única das três classes que o contrato aceita sem `id_canonico`, então é
a única que fecha o laço sem resolvedor. Serve de referência — foi 0,1220 quando o laço
fechou pela primeira vez, contra 1,0470 da fase 2 completa.

Os spans da fase 1 saem do cache de `experiment_merge.py` — uma passada da LLM já
gravada em `data/llm_spans_cache.json`. Assim o laço fecha **sem ocupar a GPU** e o
número não carrega o não-determinismo do vLLM: repetir este script dá o mesmo resultado.

A conversão JSON -> CSV é feita pelo `json_to_submission.py` da organização, chamado como
subprocesso e sem modificação — o objetivo é exercitar o caminho real, não uma imitação.

Uso: `uv run python scripts/score_official.py`
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

from cacador_alucinacoes.goldenset import (
    ROOT,
    literal_excerpt,
    load_documents,
    load_goldenset,
)
from cacador_alucinacoes.hybrid import Citation, merge
from cacador_alucinacoes.kaggle_metric import ParticipantVisibleError, avaliar
from cacador_alucinacoes.regex_extraction import find
from cacador_alucinacoes.resolution import Resolver, query_text
from cacador_alucinacoes.self_reference import drop_self_references
from cacador_alucinacoes.span_recovery import Found, intersection_over_union
from cacador_alucinacoes.submission import solution_frame, write_contract

CACHE = ROOT / "data" / "llm_spans_cache.json"
OUTPUT = ROOT / "output"
JSON_DIR = OUTPUT / "contrato"
SUBMISSION = OUTPUT / "submission.csv"
SOLUTION = OUTPUT / "solution.csv"

# O contrato exige `tipo` em toda citação, mas a métrica não o pontua — o
# `json_to_submission` sequer o carrega para o CSV. Enquanto a fase 2 não decide de onde
# ele sai, vai um valor fixo, explicitamente provisório.
PLACEHOLDER_KIND = "jurisprudencia"


def cached_spans(path: Path = CACHE) -> dict[str, list[Found]]:
    if not path.exists():
        sys.exit(
            f"cache ausente em {path}.\n"
            "Ele é uma passada da LLM gravada em disco; para recriá-lo (ocupa a GPU):\n"
            "  uv run python scripts/experiment_merge.py --refresh"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        document_id: [
            Found(
                start=span["start"],
                end=span["end"],
                text=span["text"],
                block_index=span["block_index"],
            )
            for span in spans
        ]
        for document_id, spans in raw.items()
    }


def label_everything_incompleta(citations: list[Citation]) -> list[Citation]:
    """O controle no lugar da fase 2: reconhece, não classifica e não resolve.

    Sem confiança de propósito. O bônus é `0,10 · (1 − brier)` e nunca é negativo, então
    mandar confiança só pode ajudar — mas aqui o objetivo é isolar o piso de
    reconhecimento + classificação, sem o bônus por cima.
    """
    return [
        replace(
            citation,
            kind=PLACEHOLDER_KIND,
            label="incompleta",
            canonical_id=None,
            confidence=None,
        )
        for citation in citations
    ]


# Confiança por caminho de decisão. NÃO é calibração — é um primeiro corte, ordenado
# pelo que cada caminho tem de evidência. O bônus é `0,10 · (1 − brier)` e nunca fica
# negativo, então mandar um valor grosseiro já domina não mandar nada; afinar isto é
# trabalho de calibração, contra o gabarito, e ainda não foi feito.
PATH_CONFIDENCE = {
    ("real", 1): 0.95,      # candidato único: a busca não deixou dúvida
    ("real", 0): 0.75,      # desempatado por posição entre vários
    ("inventada", 0): 0.85,
    ("incompleta", 0): 0.85,
}


def resolve_all(
    document: str, citations: list[Citation], resolver: Resolver
) -> list[Citation]:
    """Fase 2 sobre os spans reconhecidos: classe, link e tipo, um a um."""
    out = []
    for citation in citations:
        # O span vai para a submissão como a fase 1 o entregou; o que se estende é só o
        # texto da consulta, quando o span cortou um número ao meio.
        found = resolver.resolve(query_text(document, citation.start, citation.end))
        single = 1 if found.candidates == 1 else 0
        out.append(
            replace(
                citation,
                kind=found.kind,
                label=found.label,
                canonical_id=found.canonical_id,
                confidence=PATH_CONFIDENCE.get((found.label, single), 0.75),
            )
        )
    return out


def overlapping_pairs(citations: list[Citation]) -> list[tuple[Citation, Citation]]:
    """Pares que a métrica rejeita como duplicata (IoU >= 0,5 entre duas predições)."""
    pairs = []
    for a in range(len(citations)):
        for b in range(a + 1, len(citations)):
            first, second = citations[a], citations[b]
            overlap = intersection_over_union(
                (first.start, first.end), (second.start, second.end)
            )
            if overlap >= 0.5:
                pairs.append((first, second))
    return pairs


def main() -> None:
    control = "--control" in sys.argv
    resolver = None if control else Resolver(header_tiebreak="--no-tiebreak" not in sys.argv)

    # `--cache <arquivo>` aponta para a saída de uma variante de `experiment_prompt.py`,
    # para comparar prompts sobre o mesmo pipeline de fase 2.
    chosen = CACHE
    if "--cache" in sys.argv:
        chosen = Path(sys.argv[sys.argv.index("--cache") + 1])

    documents = load_documents()
    goldenset = load_goldenset()
    cache = cached_spans(chosen)

    JSON_DIR.mkdir(parents=True, exist_ok=True)
    for stale in JSON_DIR.glob("*.json"):
        stale.unlink()

    total = 0
    duplicates = []
    for document_id, document in documents.items():
        recognised = drop_self_references(
            document, merge(cache.get(document_id, []), find(document))
        )
        citations = (
            label_everything_incompleta(recognised)
            if control
            else resolve_all(document, recognised, resolver)
        )
        total += len(citations)
        for first, second in overlapping_pairs(citations):
            duplicates.append((document_id, first, second))
        write_contract(JSON_DIR, document_id, document, citations)

    print(f"{len(documents)} documentos, {total} citações reconhecidas.")

    if duplicates:
        print(f"\n{len(duplicates)} par(es) que a métrica rejeita como duplicata:")
        for document_id, first, second in duplicates:
            print(f"  {document_id}: {first.text[:44]!r} || {second.text[:44]!r}")

    converter = subprocess.run(
        [sys.executable, "-m", "cacador_alucinacoes.json_to_submission",
         str(JSON_DIR), str(SUBMISSION)],
        capture_output=True,
        text=True,
    )
    if converter.returncode != 0:
        sys.exit(f"json_to_submission falhou:\n{converter.stderr}")
    print(f"\n{converter.stdout.strip()}")

    solution = solution_frame(goldenset)
    solution.to_csv(SOLUTION, index=False)
    submission = pd.read_csv(SUBMISSION)

    try:
        report = avaliar(solution, submission)
    except ParticipantVisibleError as error:
        sys.exit(f"\nA métrica rejeitou a submissão:\n  {error}")

    title = (
        "controle: tudo `incompleta`, sem resolução"
        if control
        else f"fase 2 completa (desempate por posição: {resolver.header_tiebreak})"
    )
    print()
    print("=" * 72)
    print(f"SCORE OFICIAL — {title}")
    print("=" * 72)
    header = f"{'':<10}" + "".join(f"{c:>13}" for c in ("real", "inventada", "incompleta"))
    print(f"{header}{'macroF1':>10}{'τ':>7}{'bônus':>8}{'score':>9}")
    for level, result in sorted(report["niveis"].items()):
        cells = "".join(
            f"{result['f1_por_classe'].get(c, 0.0):>13.4f}"
            for c in ("real", "inventada", "incompleta")
        )
        print(
            f"nível {level}  {cells}"
            f"{result['macro_f1']:>10.4f}{result['tau']:>7.2f}"
            f"{result['b']:>8.4f}{result['score']:>9.4f}"
        )
    print("-" * 72)
    print(f"score_final = (1·N1 + 2·N2) / 3 = {report['score_final']:.4f}")
    print("\n(uma submissão perfeita com confianca=1.0 vale 1.1000)")


if __name__ == "__main__":
    main()
