from __future__ import annotations

import sys
from pathlib import Path

from challenge_jusbrasil.pipeline import buscar, imprimir_avaliacao


def main() -> None:
    pastas = [Path(argumento) for argumento in sys.argv[1:]] or None
    imprimir_avaliacao(buscar(pastas))


if __name__ == "__main__":
    main()
