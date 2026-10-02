from __future__ import annotations

from challenge_jusbrasil.pipeline import buscar, extrair, imprimir_avaliacao, salvar_avaliacao


def main() -> None:
    pastas = extrair()
    resultados = buscar(pastas)
    imprimir_avaliacao(resultados)
    salvar_avaliacao(resultados)

def main_compat() -> None:
    pastas = extrair()
    resultados = buscar(pastas)
    imprimir_avaliacao(resultados)
    salvar_avaliacao(resultados)

    return resultados


if __name__ == "__main__":
    main()
