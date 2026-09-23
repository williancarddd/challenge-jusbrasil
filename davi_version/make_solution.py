# -*- coding: utf-8 -*-
"""goldenset.csv -> DataFrame `solution` no formato exigido por
kaggle_metric.avaliar(): documento_id, nivel, citacoes
(célula "inicio,fim,classe,doc_ids", doc_ids separados por ':')."""
import csv
from collections import defaultdict
from pathlib import Path

import pandas as pd


def build_solution_df(goldenset_path) -> pd.DataFrame:
    por_doc = defaultdict(list)
    nivel_por_doc = {}
    with open(goldenset_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            doc = row["documento_id"]
            nivel_por_doc[doc] = int(row["nivel"])
            classe = row["classificacao"]
            doc_ids = row["id_canonico"].strip() if classe == "real" else ""
            campo_ids = doc_ids if doc_ids else "-"
            por_doc[doc].append(f"{row['inicio']},{row['fim']},{classe},{campo_ids}")
    linhas = []
    for doc, blocos in por_doc.items():
        linhas.append({"documento_id": doc, "nivel": nivel_por_doc[doc],
                        "citacoes": "|".join(blocos) if blocos else "-"})
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    import sys
    HERE = Path(__file__).resolve().parent
    default_gold = HERE.parent / "goldenset_offsets.csv"
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else default_gold
    df = build_solution_df(src)
    print(df.to_csv(index=False))
