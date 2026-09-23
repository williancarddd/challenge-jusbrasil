# -*- coding: utf-8 -*-
"""Tabela estática dos 13 `dispositivo` + 5 `sumula` da base canônica.

A base é uma cobertura congelada (mesmo .db no treino e na avaliação final),
então esta tabela vale para os dois. Os 3 números de súmula do STJ são
extraídos por regex do próprio `texto` (ver build_kb.build_sumulas) porque o
registro os contém literalmente ("(SÚMULA 83, ...)"); STF e TST não trazem o
número no corpo, por isso ficam fixos aqui — a identificação foi feita lendo
o `texto` de cada um dos 5 registros de natureza `sumula` e comparando com o
teor conhecido das súmulas (STF: Súmula Vinculante 10, reserva de plenário;
TST: Súmula 331, terceirização) e confirmada contra o `id_canonico` dos `real`
de nível 1/2 do goldenset.

DISPOSITIVOS: chave (numero_artigo, codigo) -> id canônico.
"""

DISPOSITIVOS = {
    ("276", "CE"): 10577194,
    ("290", "CPM"): 10590194,
    ("14", "CDC"): 10606184,
    ("93", "CF"): 10626510,
    ("896", "CLT"): 10637358,
    ("7", "CF"): 10641213,
    ("5", "CF"): 10641516,
    ("818", "CLT"): 10647746,
    ("312", "CPP"): 10652044,
    ("477", "CLT"): 10710324,
    ("186", "CC"): 10718759,
    ("1", "LC64"): 11304039,
    ("373", "CPC"): 28893055,
}

# súmulas sem número explícito no próprio texto (fixas)
SUMULAS_FIXAS = {
    ("STF", "VINCULANTE10"): 1289712966,
    ("TST", "331"): 1431369957,
}
