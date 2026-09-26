"""Leitura do gabarito e dos documentos de entrada.

Os dados vêm da versão final do dataset (Kaggle, 26/09/2026), em `data/final/`. O
gabarito passou de `.xlsx` para `goldenset_offsets.csv`, que abre com BOM — sem
`utf-8-sig` a primeira coluna vira `\\ufeffnivel`. As linhas sem `id_canonico` trazem a
célula vazia.

Os nomes de coluna do gabarito e do contrato de submissão são em português
(`inicio`, `fim`, `trecho`, `tipo`, `classificacao`, `id_canonico`). Eles ficam
confinados à fronteira de leitura e serialização; dentro do código os campos são
`start`, `end`, `excerpt`, `kind`, `label`, `canonical_id`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "final"
INPUT_DIR = DATA_DIR / "txt"
GOLDENSET_PATH = DATA_DIR / "goldenset_offsets.csv"


@dataclass(frozen=True)
class Citation:
    level: int
    document_id: str
    citation_id: str
    start: int
    end: int
    excerpt: str
    kind: str
    label: str
    canonical_id: str | None


def load_goldenset(path: Path = GOLDENSET_PATH) -> list[Citation]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            Citation(
                level=int(record["nivel"]),
                document_id=record["documento_id"],
                citation_id=record["citacao_id"],
                start=int(record["inicio"]),
                end=int(record["fim"]),
                excerpt=record["trecho"],
                kind=record["tipo"],
                label=record["classificacao"],
                # Desde o e-mail de 28/08 o campo é um doc_id único, não mais conjunto.
                canonical_id=record["id_canonico"] or None,
            )
            for record in csv.DictReader(handle)
            if record["documento_id"]
        ]


def load_documents(directory: Path = INPUT_DIR) -> dict[str, str]:
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(directory.glob("*.txt"))
    }


def literal_excerpt(document: str, start: int, end: int) -> str:
    """O `trecho` da submissão sai daqui — do arquivo cru, nunca da saída da LLM.

    O gabarito define `trecho` como cópia literal de `texto[inicio:fim]`, e 59 dos 225
    trechos contêm quebra de linha. No texto normalizado essa quebra virou espaço, então
    copiar da resposta da LLM produziria um `trecho` diferente do esperado.
    """
    return document[start:end]
