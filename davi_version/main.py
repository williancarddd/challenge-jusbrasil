# -*- coding: utf-8 -*-
"""Contrato de execução: python main.py --input <dir .txt> --output <dir .json>

Determinístico, offline, sem GPU/rede — só lê o .txt e consulta a base SQLite
local (desafio1_bracis.db) via kb/kb.json + fallback FTS."""
import argparse
import json
from pathlib import Path

from pipeline import process_documento
from resolve import KB

HERE = Path(__file__).resolve().parent
DEFAULT_DB = HERE.parent / "desafio1_bracis.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="diretório com os .txt de entrada")
    ap.add_argument("--output", required=True, help="diretório onde escrever os .json")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="desafio1_bracis.db (fallback FTS)")
    args = ap.parse_args()

    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    kb = KB(db_path=args.db)
    try:
        arquivos = sorted(in_dir.glob("*.txt"))
        for arq in arquivos:
            documento_id = arq.stem
            texto = arq.read_text(encoding="utf-8")
            doc = process_documento(documento_id, texto, kb)
            (out_dir / f"{documento_id}.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[main] {len(arquivos)} documentos processados -> {out_dir}")
    finally:
        kb.close()


if __name__ == "__main__":
    main()
