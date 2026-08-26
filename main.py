# -*- coding: utf-8 -*-
"""Executa o baseline principal, avalia contra o goldenset (IoU>=0.5) e produz
a tabela de resultados + saídas em results/.

Uso:
    python main.py

Layout de saída (results/):
    results/<solucao>/<doc>.json   submissão no formato do contrato, por documento
    results/tabela.csv             métricas por solução e nível
    results/tabela.md              a mesma tabela em Markdown
    results/resumo.json            tudo em JSON (para pós-processamento)
"""
import csv
import glob
import json
import os
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "baseline_regra"))

from resolver import Resolvedor          # noqa: E402
import solucoes                          # noqa: E402

IOU_MIN = 0.5


def iou(a0, a1, b0, b1):
    inter = max(0, min(a1, b1) - max(a0, b0))
    union = (a1 - a0) + (b1 - b0) - inter
    return inter / union if union else 0.0


def carregar_golden(path):
    g = defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        g[r["documento_id"]].append({
            "inicio": int(r["inicio"]), "fim": int(r["fim"]),
            "tipo": r["tipo"], "classificacao": r["classificacao"],
            "id_canonico": set(r["id_canonico"].split()) if r["id_canonico"] else set(),
            "nivel": int(r["nivel"]),
        })
    return g


def alinhar(preds, golds):
    pares = []
    for i, p in enumerate(preds):
        for j, g in enumerate(golds):
            v = iou(p["inicio"], p["fim"], g["inicio"], g["fim"])
            if v >= IOU_MIN:
                pares.append((v, i, j))
    pares.sort(reverse=True)
    up, ug, matches = set(), set(), []
    for v, i, j in pares:
        if i in up or j in ug:
            continue
        up.add(i); ug.add(j); matches.append((i, j))
    return matches, [i for i in range(len(preds)) if i not in up], \
                    [j for j in range(len(golds)) if j not in ug]


def avaliar(preds_por_doc, golden):
    stat = {1: defaultdict(int), 2: defaultdict(int)}
    for doc, preds in preds_por_doc.items():
        nivel = 1 if "_n1_" in doc else 2
        gold = golden.get(doc, [])
        matches, fp, fn = alinhar(preds, gold)
        s = stat[nivel]
        s["gold"] += len(gold); s["pred"] += len(preds)
        s["fp"] += len(fp); s["fn"] += len(fn); s["tp_span"] += len(matches)
        for i, j in matches:
            if preds[i]["classificacao"] == gold[j]["classificacao"]:
                s["classe_ok"] += 1
            if gold[j]["classificacao"] == "real":
                s["real_total"] += 1
                idc = (preds[i].get("resolucao") or {}).get("id_canonico")
                if preds[i]["classificacao"] == "real" and idc and idc in gold[j]["id_canonico"]:
                    s["id_ok"] += 1
    linhas, notas = {}, {}
    for nv in (1, 2):
        s = stat[nv]
        P = s["tp_span"] / s["pred"] if s["pred"] else 0.0
        R = s["tp_span"] / s["gold"] if s["gold"] else 0.0
        F1 = 2*P*R/(P+R) if (P+R) else 0.0
        cls = s["classe_ok"] / s["tp_span"] if s["tp_span"] else 0.0
        idr = s["id_ok"] / s["real_total"] if s["real_total"] else 0.0
        linhas[nv] = dict(span_P=P, span_R=R, span_F1=F1, classe=cls, id_real=idr)
        notas[nv] = F1 * cls
    ponderada = (1*notas[1] + 2*notas[2]) / 3
    return linhas, ponderada


def main():
    golden = carregar_golden(os.path.join(BASE, "goldenset.csv"))
    ctx = {"resolvedor": Resolvedor(os.path.join(BASE, "desafio1_bracis.db"))}

    docs = sorted(glob.glob(os.path.join(BASE, "txt", "*.txt")))
    resultados, resumo = {}, {}
    for nome, fn, desc in solucoes.REGISTRO:
        preds_por_doc = {}
        outdir = os.path.join(BASE, "results", nome)
        os.makedirs(outdir, exist_ok=True)
        for txt_path in docs:
            doc = os.path.splitext(os.path.basename(txt_path))[0]
            texto = open(txt_path, encoding="utf-8").read()
            cits = fn(texto, doc, ctx)
            preds_por_doc[doc] = cits
            json.dump({"documento_id": doc, "citacoes": cits},
                      open(os.path.join(outdir, f"{doc}.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        linhas, ponderada = avaliar(preds_por_doc, golden)
        resultados[nome] = (linhas, ponderada, desc)
        resumo[nome] = {"descricao": desc, "nivel_1": linhas[1],
                        "nivel_2": linhas[2], "nota_ponderada": ponderada}

    # ---- tabela ----
    cab = ["solucao", "nivel", "span_P", "span_R", "span_F1", "classe@match",
           "id@real", "nota_ponderada"]
    rows = []
    for nome, (linhas, ponderada, desc) in resultados.items():
        for nv in (1, 2):
            L = linhas[nv]
            rows.append([nome, nv, f"{L['span_P']:.3f}", f"{L['span_R']:.3f}",
                         f"{L['span_F1']:.3f}", f"{L['classe']:.3f}",
                         f"{L['id_real']:.3f}",
                         f"{ponderada:.3f}" if nv == 1 else ""])

    os.makedirs(os.path.join(BASE, "results"), exist_ok=True)
    with open(os.path.join(BASE, "results", "tabela.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cab); w.writerows(rows)
    with open(os.path.join(BASE, "results", "tabela.md"), "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(cab) + " |\n")
        f.write("|" + "|".join(["---"]*len(cab)) + "|\n")
        for r in rows:
            f.write("| " + " | ".join(str(x) for x in r) + " |\n")
    json.dump(resumo, open(os.path.join(BASE, "results", "resumo.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=2)

    # ---- imprime ----
    larg = [18, 5, 6, 6, 7, 12, 7, 8]
    print("  ".join(h.ljust(w) for h, w in zip(cab, larg)))
    for r in rows:
        print("  ".join(str(x).ljust(w) for x, w in zip(r, larg)))
    print("\nresultados salvos em results/  (tabela.csv, tabela.md, resumo.json, "
          "e <solucao>/<doc>.json)")


if __name__ == "__main__":
    main()
