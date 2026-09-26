from __future__ import annotations

from typing import Any

from challenge_jusbrasil.pipeline import executar


def _jsonable(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {str(chave): _jsonable(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_jsonable(item) for item in valor]
    if isinstance(valor, float):
        return float(valor)
    if hasattr(valor, "item"):
        return _jsonable(valor.item())
    return valor


def main() -> dict[str, Any]:
    resultados = _jsonable(executar())
    print()
    for nome, item in resultados.items():
        avaliacao = item["avaliacao"]
        print(f"{item['role']} {nome}")
        for nivel, detalhe in sorted(avaliacao["niveis"].items(), key=lambda par: int(par[0])):
            f1 = {classe: round(valor, 3) for classe, valor in detalhe["f1_por_classe"].items()}
            print(
                f"  nivel {nivel}: score={detalhe['score']:.4f} "
                f"macro_f1={detalhe['macro_f1']:.4f} tau={detalhe['tau']:.3f} "
                f"bonus={detalhe['b']:.4f} f1={f1}"
            )
        print(f"  SCORE FINAL: {avaliacao['score_final']:.4f}")
    return resultados


if __name__ == "__main__":
    main()
