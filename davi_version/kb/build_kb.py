# -*- coding: utf-8 -*-
"""Constrói kb.json: índice offline de cabeçalhos de acórdão + leis/súmulas.

Uso: python kb/build_kb.py [--db ../desafio-jusbrasil-bracis-2026/desafio1_bracis.db]
     [--goldenset ../desafio-jusbrasil-bracis-2026/goldenset.csv]

Roda uma vez; o resultado (kb.json) é lido em runtime por resolve.py sem reabrir
o índice de cabeçalhos (a conexão sqlite só fica viva para o fallback de FTS).
"""
import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from normalize import only_digits, strip_dates, extract_number_token  # noqa: E402
import leis_sumulas  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_DB = HERE.parent.parent / "desafio-jusbrasil-bracis-2026" / "desafio1_bracis.db"
DEFAULT_GOLD = HERE.parent.parent / "desafio-jusbrasil-bracis-2026" / "goldenset.csv"

# janela de cabeçalho (chars) e regex de número por tribunal.
_NUM_TOKEN = r"[\d][\d.\-\/ ]{1,40}\d|\d"


def _candidate_numbers(window: str):
    """Sequências candidatas a número de processo numa janela de texto (datas
    DD/MM/AAAA já removidas antes de chamar)."""
    out = []
    for m in re.finditer(_NUM_TOKEN, window):
        raw = m.group(0)
        digits = only_digits(raw)
        if len(digits) >= 3:
            out.append(digits)
    return out


_TST_AUTOS_RE = re.compile(r"estes autos de[^.]{0,220}?n[ºO°]\s*([A-Za-z0-9.\- ]+)")
_TST_PROCESSO_RE = re.compile(r"PROCESSO N[ºO°]\s*[:\-]?\s*([A-Za-z0-9.\- ]+)")
_TST_FALLBACK_RE = re.compile(r"\b[A-Z]{2,8}-\d[\d.\-]{3,30}\d\b")


def _header_numbers(tribunal: str, texto: str):
    """Retorna a lista de sequências de dígitos que identificam o processo,
    para o tribunal dado, a partir do texto integral do acórdão."""
    if tribunal == "TST":
        # o número aparece longe do início (ementas longas) — sem posição
        # fixa. Duas âncoras textuais cobrem quase todo o corpus: a sentença
        # "estes autos de ... nº <CLASSE>-<CNJ>" (maioria) e "PROCESSO Nº
        # <CLASSE>-<CNJ>" (o resto, salvo ~2%).
        m = _TST_AUTOS_RE.search(texto) or _TST_PROCESSO_RE.search(texto)
        if m:
            tok = extract_number_token(m.group(1)) or ""
            digits = only_digits(tok)
            return [digits] if len(digits) >= 4 else []
        m = _TST_FALLBACK_RE.search(texto[:3000])
        if not m:
            return []
        tok = extract_number_token(m.group(0)) or ""
        digits = only_digits(tok)
        return [digits] if len(digits) >= 4 else []

    window = strip_dates(texto[:400])
    nums = _candidate_numbers(window)
    if not nums:
        return []
    # STJ traz um segundo número de registro entre parênteses, ex. (2018/0116304-1)
    out = [nums[0]]
    if tribunal == "STJ" and len(nums) > 1:
        out.append(nums[1])
    return out


def build_header_index(con):
    cur = con.cursor()
    cur.execute(
        "SELECT documento_id, id, tribunal, ano, relator, texto "
        "FROM documentos WHERE natureza='acordao'"
    )
    index = defaultdict(list)
    n_sem_numero = 0
    for documento_id, doc_id, tribunal, ano, relator, texto in cur.fetchall():
        nums = _header_numbers(tribunal, texto)
        if not nums:
            n_sem_numero += 1
            continue
        entry = {"id": doc_id, "documento_id": documento_id, "tribunal": tribunal,
                  "ano": ano, "relator": relator}
        for n in nums:
            index[n].append(entry)
    print(f"[header_index] {len(index)} chaves; {n_sem_numero} acórdãos sem número extraído")
    return index


def build_sumulas(con):
    cur = con.cursor()
    cur.execute(
        "SELECT documento_id, id, tribunal, texto FROM documentos WHERE natureza='sumula'"
    )
    sumulas = []
    for documento_id, doc_id, tribunal, texto in cur.fetchall():
        m = re.search(r"S[ÚU]MULA\s+(\d+)", texto, flags=re.IGNORECASE)
        if m:
            sumulas.append({"tribunal": tribunal, "numero": m.group(1),
                             "vinculante": False, "id": doc_id, "documento_id": documento_id})
            continue
        found = False
        for (trib_key, num_key), fixed_id in leis_sumulas.SUMULAS_FIXAS.items():
            if fixed_id == doc_id:
                vinc = num_key.startswith("VINCULANTE")
                numero = num_key.replace("VINCULANTE", "")
                sumulas.append({"tribunal": trib_key, "numero": numero,
                                 "vinculante": vinc, "id": doc_id, "documento_id": documento_id})
                found = True
                break
        if not found:
            print(f"[AVISO] súmula {documento_id} (id={doc_id}, tribunal={tribunal}) "
                  f"sem número identificado — adicione em leis_sumulas.SUMULAS_FIXAS")
    return sumulas


def build_dispositivos(con):
    cur = con.cursor()
    cur.execute(
        "SELECT documento_id, id, texto FROM documentos WHERE natureza='dispositivo'"
    )
    by_id = {doc_id: (documento_id, texto) for documento_id, doc_id, texto in cur.fetchall()}
    dispositivos = []
    for (numero, codigo), doc_id in leis_sumulas.DISPOSITIVOS.items():
        if doc_id not in by_id:
            print(f"[AVISO] dispositivo id={doc_id} ({numero}/{codigo}) não encontrado no banco")
            continue
        documento_id, _ = by_id[doc_id]
        dispositivos.append({"numero": numero, "codigo": codigo, "id": doc_id,
                              "documento_id": documento_id})
    faltando = set(by_id) - set(leis_sumulas.DISPOSITIVOS.values())
    if faltando:
        print(f"[AVISO] dispositivos no banco sem entrada na tabela estática: {faltando}")
    return dispositivos


def validar_contra_goldenset(gold_path: Path, header_index, sumulas, dispositivos):
    if not gold_path.exists():
        print(f"[validação] goldenset não encontrado em {gold_path}, pulando")
        return
    sumula_by_key = {(s["tribunal"], s["numero"]): s["id"] for s in sumulas}
    disp_by_key = {(d["numero"], d["codigo"]): d["id"] for d in dispositivos}
    ok, falhas = 0, []
    with gold_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["classificacao"] != "real":
                continue
            esperado = row["id_canonico"].strip()
            trecho = row["trecho"].replace("\\n", "\n")
            if row["tipo"] == "jurisprudencia":
                if re.search(r"[s5][uú]mula", trecho, flags=re.IGNORECASE):
                    m = re.search(r"[s5][uú]mula\w*\s+(?:vinculante\s+)?(\d+)", trecho,
                                  flags=re.IGNORECASE)
                    numero = m.group(1) if m else None
                    achou = any(str(s["id"]) == esperado and s["numero"] == numero
                                for s in sumulas)
                    if achou:
                        ok += 1
                    else:
                        falhas.append((row["documento_id"], row["citacao_id"], trecho,
                                        esperado, "sumula"))
                    continue
                tok = extract_number_token(trecho)
                digits = only_digits(tok) if tok else ""
                cands = header_index.get(digits)
                if cands and len(cands) == 1 and str(cands[0]["id"]) == esperado:
                    ok += 1
                else:
                    falhas.append((row["documento_id"], row["citacao_id"], trecho, esperado,
                                    "ambiguo" if cands else "nao_encontrado"))
            else:
                # lei: tentativa best-effort de achar (numero, codigo) no texto do gabarito
                falhas_lei = True
                m = re.search(r"(\d+)", trecho)
                if m:
                    numero = m.group(1)
                    for (num, cod), doc_id in disp_by_key.items():
                        if num == numero and str(doc_id) == esperado:
                            falhas_lei = False
                            ok += 1
                            break
                if falhas_lei:
                    falhas.append((row["documento_id"], row["citacao_id"], trecho, esperado, "lei"))
    print(f"[validação] {ok} citações 'real' resolvidas corretamente pela KB")
    if falhas:
        print(f"[validação] {len(falhas)} falhas (revisar regex de cabeçalho / tabela estática):")
        for f_ in falhas[:30]:
            print("   ", f_)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--goldenset", default=str(DEFAULT_GOLD))
    ap.add_argument("--out", default=str(HERE / "kb.json"))
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.text_factory = lambda b: b.decode("utf-8", "replace")

    header_index = build_header_index(con)
    sumulas = build_sumulas(con)
    dispositivos = build_dispositivos(con)
    con.close()

    validar_contra_goldenset(Path(args.goldenset), header_index, sumulas, dispositivos)

    kb = {"header_index": header_index, "sumulas": sumulas, "dispositivos": dispositivos}
    Path(args.out).write_text(json.dumps(kb, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"[build_kb] escrito {args.out}")


if __name__ == "__main__":
    main()
