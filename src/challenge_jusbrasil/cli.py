from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
# import pandas as pd


_IGNORAR_JSON = {"meta.json", "resumo.json"}


def executar_pipeline(db_path: str, txt_dir: str, arquivo_saida: str) -> None:
    os.environ['TXT_DIR'] = txt_dir
    os.environ['DB_PATH'] = db_path
    # os.environ['OUTPUT'] = arquivo_saida

    from challenge_jusbrasil.main import main_compat
    from challenge_jusbrasil.utils.json_to_submission import converter

    resultados = main_compat()

    extract_value = next(iter(resultados.values()))['extract']
    extract = Path(extract_value)
    converter(pasta=extract, destino=arquivo_saida)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ponto de entrada único para a pipeline de extração de citações jurídicas."
    )
    parser.add_argument(
        "caminho_db",
        type=str,
        help="Caminho para o ficheiro .db ou .csv de referência",
    )
    parser.add_argument(
        "pasta_txt",
        type=str,
        help="Diretório contendo os ficheiros .txt para processamento",
    )
    parser.add_argument(
        "arquivo_saida", type=str, help="Caminho do ficheiro CSV de saída"
    )

    args = parser.parse_args()
    executar_pipeline(args.caminho_db, args.pasta_txt, args.arquivo_saida)


if __name__ == "__main__":
    main()
