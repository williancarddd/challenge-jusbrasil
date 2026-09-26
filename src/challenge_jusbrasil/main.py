from __future__ import annotations

from challenge_jusbrasil.pipeline import buscar, extrair, imprimir_avaliacao


def main() -> None:
    imprimir_avaliacao(buscar(extrair()))


if __name__ == "__main__":
    main()
