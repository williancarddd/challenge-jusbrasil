"""Descarte de autorreferência: a peça citando a si mesma.

A fase 1 marca como citação o recurso que a própria peça está interpondo, a decisão de
que ela recorre e o tribunal que a proferiu. Nenhum deles é citação de fonte externa —
é o processo em curso —, e nenhum está no gabarito. Medido nos 26 documentos: **10 das
13 predições espúrias** são disto.

Não é o mesmo distrator que o pré-processamento já trata. O descarte de blocos cobre o
**cabeçalho** (número dos autos, valor da causa) e a regra do `verify` cobre o **título
isolado**. Estes aqui aparecem no meio do corpo, dentro de um bloco com texto legítimo
em volta, e por isso passam pelas duas:

    '…vem, respeitosamente, … interpor o presente AGRAVO INTERNO contra a decisão…'

`AGRAVO INTERNO` também é o bloco 2 inteiro do mesmo documento, mas quem a LLM marcou
foi a ocorrência do corpo. A regra "candidato igual ao bloco" não tinha por que disparar.

O sinal é sintático e vem do português forense, não do vocabulário jurídico: ou a
expressão se diz do processo em curso (`recorrido`, `em referência`), ou a oração que a
introduz apresenta a peça (`o presente`, `Cuida-se de`, `inconformado com`). É por isso
que o filtro olha uma janela **antes** do span, e não só o span.

Medido: derruba 0 das 225 citações do gabarito.
"""

from __future__ import annotations

import re

from cacador_alucinacoes.hybrid import Citation

# A expressão diz, dela mesma, que a fonte é a deste processo.
INSIDE = re.compile(
    r"recorrid[oa]|em refer[êe]ncia|impugnad[oa]|combatid[oa]|guerread[oa]|"
    r"ora agravad|em ep[íi]grafe",
    re.IGNORECASE,
)

# A oração imediatamente anterior apresenta a peça que está sendo escrita. Os `$` são o
# que dá precisão: o marcador precisa estar colado no span, não solto no parágrafo.
BEFORE = re.compile(
    r"(?:o|a)\s+presente\s*$|vem\s+interpor\s*$|interpor\s+o?\s*$|"
    r"cuida-se\s+de\s*$|inconformad[oa]\s+com\s+[oa]?\s*$|"
    r"n[ãa]o\s+se\s+conformando\s+com\s+[oa]?\s*(?:ac[óo]rd[ãa]o\s+proferido\s+pel[oa]?\s*)?$",
    re.IGNORECASE,
)

# Quanto do texto anterior entra na janela. 60 caracteres cobrem a oração introdutória
# inteira (`não se conformando com o acórdão proferido pelo`) sem alcançar a frase
# anterior, que traria marcador de outro contexto.
WINDOW = 60


def is_self_reference(document: str, start: int, end: int) -> bool:
    """O span aponta para o próprio processo em vez de para uma fonte externa?"""
    if INSIDE.search(document[start:end]):
        return True
    # A quebra de linha vira espaço só para casar o marcador — o documento não é alterado
    # e nenhum offset se move.
    before = document[max(0, start - WINDOW):start].replace("\n", " ")
    return bool(BEFORE.search(before))


def drop_self_references(document: str, citations: list[Citation]) -> list[Citation]:
    return [c for c in citations if not is_self_reference(document, c.start, c.end)]
