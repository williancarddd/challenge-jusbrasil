"""Fronteira de serialização: da `Citation` interna para os arquivos do desafio.

Aqui — e só aqui — os nomes em português do contrato aparecem (`inicio`, `fim`,
`trecho`, `tipo`, `classificacao`, `id_canonico`, `confianca`). Dentro do código eles
são `start`, `end`, `excerpt`, `kind`, `label`, `canonical_id`, `confidence`.

Duas exigências do contrato que são fáceis de errar em silêncio:

- o `trecho` sai do **arquivo cru pelo span** (`literal_excerpt`), nunca do texto que a
  LLM devolveu — 59 dos 225 trechos do gabarito contêm quebra de linha que a
  normalização converteu em espaço, e copiar da resposta produziria trecho diferente;
- o `id_canonico` é a coluna `id` da base — o doc_id do Jusbrasil, um inteiro —, **não**
  o `documento_id` (`doc_0201`), que é só a chave interna do acervo. A especificação
  destaca isso: entregar um no lugar do outro derruba a citação mesmo com a classe certa.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from cacador_alucinacoes.goldenset import Citation as GoldCitation
from cacador_alucinacoes.goldenset import literal_excerpt
from cacador_alucinacoes.hybrid import Citation


def contract_citation(document: str, citation: Citation) -> dict:
    """Uma citação no formato do contrato (schema 1.2)."""
    return {
        "inicio": citation.start,
        "fim": citation.end,
        "trecho": literal_excerpt(document, citation.start, citation.end),
        "tipo": citation.kind,
        "classificacao": citation.label,
        "resolucao": {"id_canonico": citation.canonical_id},
        "confianca": citation.confidence,
    }


def contract_document(
    document_id: str, document: str, citations: list[Citation]
) -> dict:
    """O JSON de um documento: um por `.txt` processado, uma entrada por citação."""
    return {
        "documento_id": document_id,
        "citacoes": [contract_citation(document, c) for c in citations],
    }


def write_contract(
    directory: Path, document_id: str, document: str, citations: list[Citation]
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{document_id}.json"
    path.write_text(
        json.dumps(
            contract_document(document_id, document, citations),
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return path


def _solution_cell(citations: list[GoldCitation]) -> str:
    """Célula `citacoes` do gabarito: `inicio,fim,classe,doc_ids` separados por `|`.

    `doc_ids` é o conjunto aceito, separado por `:`. Desde o e-mail de 28/08 cada
    citação `real` resolve para um id único, então o conjunto tem sempre um elemento —
    mas o formato continua sendo o de conjunto, e a métrica o lê como `frozenset`.
    """
    parts = []
    for citation in sorted(citations, key=lambda c: (c.start, c.end)):
        doc_ids = citation.canonical_id or "-"
        parts.append(f"{citation.start},{citation.end},{citation.label},{doc_ids}")
    return "|".join(parts) if parts else "-"


def solution_frame(goldenset: list[GoldCitation]) -> pd.DataFrame:
    """O `solution.csv` que a métrica espera, derivado do gabarito da amostra.

    É a nossa reconstrução do arquivo que fica com a organização. O `Usage`
    (Public/Private) não entra: ele só existe no conjunto final, e `score()` o descarta
    quando presente.
    """
    grouped: dict[str, list[GoldCitation]] = {}
    levels: dict[str, int] = {}
    for citation in goldenset:
        grouped.setdefault(citation.document_id, []).append(citation)
        levels[citation.document_id] = citation.level

    return pd.DataFrame(
        [
            {
                "documento_id": document_id,
                "nivel": levels[document_id],
                "citacoes": _solution_cell(citations),
            }
            for document_id, citations in sorted(grouped.items())
        ]
    )
