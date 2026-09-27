from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from challenge_jusbrasil.pipeline import buscar, carregar_documentos, extrair, imprimir_avaliacao
from challenge_jusbrasil.settings import GOLDENSET_PATH, ROOT, TXT_DIR

from train.prata import gerar_prata
from train.treinar import ADAPTER_DIR, modelo_aluno, treinar


def origens_treino(txt_dir: Path) -> set[str]:
    manifesto = txt_dir / "manifest.jsonl"
    if not manifesto.is_file():
        raise SystemExit(f"manifesto ausente: {manifesto}")
    origens: set[str] = set()
    for linha in manifesto.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            origens.add(Path(json.loads(linha)["origem"]).stem)
    if not origens:
        raise SystemExit(f"manifesto sem origens: {manifesto}")
    return origens


def gold_sem(bloqueados: set[str], destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with GOLDENSET_PATH.open(encoding="utf-8-sig", newline="") as origem, destino.open(
        "w", encoding="utf-8", newline=""
    ) as saida:
        leitor = csv.DictReader(origem)
        escritor = csv.DictWriter(saida, fieldnames=leitor.fieldnames)
        escritor.writeheader()
        for linha in leitor:
            if linha["documento_id"] not in bloqueados:
                escritor.writerow(linha)
    return destino


def avaliar(adapter: Path, txt_treino: Path) -> None:
    os.environ["LORA_PATH"] = str(adapter)
    bloqueados = origens_treino(txt_treino)
    documentos = [
        (doc_id, texto)
        for doc_id, texto in carregar_documentos(TXT_DIR)
        if doc_id not in bloqueados
    ]
    if not documentos:
        raise SystemExit("nenhum documento restou para avaliação")
    print(
        f"avaliação sem treino: excluidos={sorted(bloqueados)} restantes={len(documentos)}",
        flush=True,
    )
    gold = gold_sem(bloqueados, ROOT / "results" / "train" / "gold_heldout.csv")
    imprimir_avaliacao(buscar(extrair([modelo_aluno()], documentos=documentos), goldenset_path=gold))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("etapa", nargs="?", choices=["prata", "treinar", "avaliar", "tudo"], default="tudo")
    parser.add_argument("--txt", type=Path, default=ROOT / "data" / "train")
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--adapter", type=Path, default=ADAPTER_DIR)
    args = parser.parse_args()
    jsonl = args.jsonl
    adapter = args.adapter
    if args.etapa in {"prata", "tudo"}:
        jsonl = gerar_prata(args.txt)
    if args.etapa in {"treinar", "tudo"}:
        if jsonl is None:
            raise SystemExit("informe --jsonl para treinar")
        adapter = treinar(jsonl, args.adapter)
    if args.etapa in {"avaliar", "tudo"}:
        avaliar(adapter, args.txt)


if __name__ == "__main__":
    main()
