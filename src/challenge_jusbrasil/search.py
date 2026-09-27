from __future__ import annotations

import sys
from pathlib import Path

from challenge_jusbrasil.pipeline import buscar, imprimir_avaliacao


def _argumentos(argv: list[str]) -> tuple[list[Path] | None, str | None]:
    modo = None
    pastas: list[Path] = []
    indice = 0
    while indice < len(argv):
        if argv[indice] == "--busca" and indice + 1 < len(argv):
            modo = argv[indice + 1]
            indice += 2
            continue
        pastas.append(Path(argv[indice]))
        indice += 1
    return pastas or None, modo


def main() -> None:
    pastas, modo = _argumentos(sys.argv[1:])
    imprimir_avaliacao(buscar(pastas, modo=modo))


if __name__ == "__main__":
    main()
