# -*- coding: utf-8 -*-
"""Roda o pipeline nos 26 .txt do dev set, monta o submission.csv, chama a
métrica oficial (kaggle_metric.py, sem modificar) e imprime o score por
nível/classe + um diff FN/FP por documento para orientar a iteração."""
import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
PARENT_DIR = HERE.parent
sys.path.insert(0, str(PARENT_DIR))
sys.path.insert(0, str(HERE))

import kaggle_metric as km  # noqa: E402
from make_solution import build_solution_df  # noqa: E402
from pipeline import process_documento  # noqa: E402
from resolve import KB  # noqa: E402


def encode_citacoes(citas):
    partes = []
    for c in citas:
        resol = c.get("resolucao") or {}
        id_canonico = str(resol.get("id_canonico", "") or "").strip() or "-"
        conf = c.get("confianca")
        conf_s = "-" if conf is None else f"{float(conf):.4f}"
        partes.append(f"{int(c['inicio'])},{int(c['fim'])},{c['classificacao']},"
                      f"{id_canonico},{conf_s}")
    return "|".join(partes) if partes else "-"


def run_pipeline(txt_dir: Path, db_path: Path):
    kb = KB(db_path=db_path)
    docs = {}
    try:
        for arq in sorted(txt_dir.glob("*.txt")):
            texto = arq.read_text(encoding="utf-8")
            doc = process_documento(arq.stem, texto, kb)
            docs[arq.stem] = doc
    finally:
        kb.close()
    return docs


def print_diff(doc_id, golds, preds):
    pares, g_sem, p_sem = km._casar(golds, preds)
    problemas = []
    for gi, pi in pares:
        g, p = golds[gi], preds[pi]
        if g["classe"] != p["classe"]:
            problemas.append(f"  classe: gold={g['classe']} pred={p['classe']} "
                              f"span=({g['inicio']},{g['fim']})")
        elif g["classe"] == "real" and p["id_canonico"] not in g["doc_ids"]:
            problemas.append(f"  link errado: span=({g['inicio']},{g['fim']}) "
                              f"esperado={sorted(g['doc_ids'])} obtido={p['id_canonico']}")
    for gi in g_sem:
        g = golds[gi]
        problemas.append(f"  FN (não extraído): ({g['inicio']},{g['fim']}) classe={g['classe']}")
    matched_golds = [golds[gi] for gi, _ in pares]
    for pi in p_sem:
        p = preds[pi]
        if any(km._contida(p, g) for g in matched_golds):
            continue
        problemas.append(f"  FP (espúrio): ({p['inicio']},{p['fim']}) classe={p['classe']}")
    if problemas:
        print(f"[{doc_id}]")
        for p in problemas:
            print(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--txt", default=str(PARENT_DIR / "txt"))
    ap.add_argument("--db", default=str(PARENT_DIR / "desafio1_bracis.db"))
    ap.add_argument("--goldenset", default=str(PARENT_DIR / "goldenset_offsets.csv"))
    ap.add_argument("--quiet", action="store_true", help="não imprime o diff por documento")
    args = ap.parse_args()

    docs = run_pipeline(Path(args.txt), Path(args.db))

    sub_rows = [{"documento_id": doc_id, "citacoes": encode_citacoes(doc["citacoes"])}
                for doc_id, doc in docs.items()]
    submission = pd.DataFrame(sub_rows)
    solution = build_solution_df(args.goldenset)

    resultado = km.avaliar(solution, submission)
    print("=" * 70)
    for nivel, r in sorted(resultado["niveis"].items()):
        print(f"Nível {nivel}: score={r['score']:.4f}  macro_f1={r['macro_f1']:.4f}  "
              f"tau={r['tau']:.3f}  bonus={r['b']:.4f}")
        print(f"           f1_por_classe={ {k: round(v,3) for k,v in r['f1_por_classe'].items()} }")
    print(f"SCORE FINAL: {resultado['score_final']:.4f}")
    print("=" * 70)

    if not args.quiet:
        sol_idx = solution.set_index("documento_id")
        sub_idx = submission.set_index("documento_id")
        for doc_id in sol_idx.index:
            golds = km._parse_solution_cell(sol_idx.loc[doc_id, "citacoes"], doc_id)
            preds = km._parse_submission_cell(sub_idx.loc[doc_id, "citacoes"], doc_id)
            print_diff(doc_id, golds, preds)


if __name__ == "__main__":
    main()
