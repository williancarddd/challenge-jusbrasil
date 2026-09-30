from __future__ import annotations

from challenge_jusbrasil.pipeline import buscar, extrair, imprimir_avaliacao, salvar_avaliacao


def main() -> None:
    pastas = extrair()
    resultados = buscar(pastas)
    imprimir_avaliacao(resultados)
    salvar_avaliacao(resultados)


if __name__ == "__main__":
    main()
