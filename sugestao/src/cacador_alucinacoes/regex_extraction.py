"""Extração de citações por regex — o ramo determinístico do híbrido.

Padrões adaptados do baseline determinístico do projeto `challenge-jusbrasil`
(`lib/extrair.py`), que mede P=0,890 / R=0,609 sozinho. Ele erra muito por omissão e
quase nada por invenção, o que é exatamente o perfil complementar ao da LLM: ela acha
mais (R=0,884) e inventa mais.

O filtro de cabeçalho do original foi trocado pelo nosso descarte de blocos, que é
medido (52/52 preâmbulos fora, 0 citações perdidas) em vez de heurístico por posição.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cacador_alucinacoes.preprocessing import usable_blocks

# A ordem importa: alternação em regex casa a primeira que serve, então as classes
# compostas vêm antes das que são prefixo delas — sem isso `Recurso Especial` casaria
# dentro de `Recurso Especial Eleitoral` e o número seguinte ficaria órfão.
_APPEAL_CLASSES = (
    r"AgRg\s+no\s+AREsp|AgInt\s+no\s+AREsp|AgRg\s+no\s+REsp|AgInt\s+no\s+REsp|"
    r"Recurso\s+Especial\s+Eleitoral|Recurso\s+em\s+Habeas\s+Corpus|"
    r"Recurso\s+em\s+Sentido\s+Estrito|Agravo\s+em\s+Recurso\s+Especial|"
    r"Recurso\s+Especial|Recurso\s+Ordin(?:á|a)rio|Recurso\s+de\s+Revista|"
    r"AgR-REspe|AREspEI|REspe|R-Rp|RMS|RHC|RSE|"
    # Classes do TST. `AgARR` antes de `ARR` pela mesma razão da ordem geral: a composta
    # tem de vir antes da que é prefixo dela.
    r"AgARR|ARR|AIRR|RR|"
    r"AgInt|AgRg|AREsp|REsp|Habeas\s+Corpus|HC|Reclama(?:ç|c)(?:ã|a)o|Rcl|RE\b|"
    r"APL|Apela(?:ç|c)(?:ã|a)o|AgProbatório"
)
# O sequencial do CNJ tem até 7 dígitos, mas os processos eleitorais usam menos —
# `2137-73.2014.6.21.0000`, `378-82.2016.6.05.0151`. Exigir 7 os deixava passar.
# E o ruído do nível 2 parte o número: hífen duplicado e espaço em volta dos pontos
# (`RSE Nº 7220273--\n23.2018.7.00.0000/ RS`). Tolerar isso vale 2 citações, medido.
_CNJ_NUMBER = (
    r"\d{1,7}\s*-{0,2}\s*\d{2}\s*\.\s*\d{4}\s*\.\s*\d\s*\.\s*\d{2}\s*\.\s*\d{4}"
)
# Aceita o número partido por espaço, que é o ruído do nível 2: "1.741. 784".
_GROUPED_NUMBER = r"\d[\d.\s]{2,}\d"
_STATE = r"(?:\s*[/\-(]\s*[A-Za-z]{2}\s*\)?)?"

# Cadeia recursal arbitrária antes da classe: o gabarito traz
# `EDcl nos EDcl no AgInt no Agravo em Recurso Especial ...` e sem isto o padrão
# começava na classe, deixando o prefixo de fora e derrubando o IoU.
# Também por extenso: o gabarito traz `Embargos de Declaração no Agravo Interno no
# Agravo em Recurso Especial nº 1904603/TO`, e só as siglas deixavam a cadeia de fora.
_APPEAL_CHAIN = (
    r"(?:(?:EDcl|EDv|ED|AgInt|AgRg|AgR|"
    r"Embargos\s+de\s+Declara(?:ç|c)(?:ã|a)o|Embargos\s+de\s+Diverg(?:ê|e)ncia|"
    r"Agravo\s+Interno|Agravo\s+Regimental)\s+n?[oa]s?\s+)*"
)

CASE_LAW_WITH_NUMBER = re.compile(
    # `[-\s]*` entre a classe e o número: o TST cola as duas com hífen
    # (`TST-AgARR-25823-78.2015.5.24.0091`) e com `\s*` a citação inteira escapava.
    rf"{_APPEAL_CHAIN}(?:{_APPEAL_CLASSES})[-\s]*(?:n[ºo°.]*\s*)?"
    rf"(?:{_CNJ_NUMBER}|{_GROUPED_NUMBER}){_STATE}",
    re.IGNORECASE,
)
PRECEDENT_SUMMARY = re.compile(
    r"S(?:ú|u)mula(?:\s+Vinculante)?\s+n?[ºo°.]*\s*\d+(?:\s+do\s+[A-Z]{2,4})?",
    re.IGNORECASE,
)
# `art(?:igo)?\.?` aceita "art", "art." e "artigo" — a forma sem ponto ocorre e o
# padrão original a rejeitava. E o rabo do dispositivo admite ponto quando seguido de
# dígito, senão "da Lei nº 13.467/2017" era cortado em "da Lei nº 13".
_STATUTE_TAIL = r"(?:[^.,;\n]|\.(?=\d))"
STATUTE = re.compile(
    # `\d+(?:\.\d+)*` porque o número do artigo tem separador de milhar:
    # `art. 1.134`, `artigo 1.143`. Com `\d+` o casamento parava em "art. 1".
    r"art(?:igo)?\.?\s*\d+(?:\.\d+)*[ºo°]?"
    r"(?:\s*,?\s*[IVXLC]+)?"
    # O parágrafo entra entre o inciso e o nome do código: `art. 896, § 1º-A, da CLT`.
    r"(?:\s*,?\s*§\s*\d+[ºo°]?(?:\s*-\s*[A-Z])?)?"
    r"(?:\s*,?\s*(?:inciso|al(?:í|i)nea)\s*\S+)?"
    # 60 caracteres não alcançavam `da Lei Complementar nº 64/1990`.
    rf"(?:\s*,?\s*d[oae]\s+{_STATUTE_TAIL}{{2,90}})?",
    re.IGNORECASE,
)
# A janela entre a cabeça da expressão e o qualificador era 120 e deixava o padrão
# atravessar a frase inteira ("acórdão recorrido diverge frontalmente do que
# assentado no precedente do STF"). 60 corta isso; 40 e 25 dão o mesmo resultado,
# então fica a menos restritiva.
# Confusões de OCR do nível 2. **Isto é lista fechada de direito**, e a distinção
# importa: o vocabulário de citação vaga é aberto — não há como enumerar os modos de
# referir jurisprudência sem número —, mas o ruído é substituição de caractere sobre um
# alfabeto finito, gerado pelo mesmo processo no conjunto cego. A especificação publica
# `0<->O`, `1<->l`, `5<->S` e `m<->rn`; as demais saem da mesma família de sósias
# tipográficos e valem nos dois sentidos.
#
# O que NÃO se codifica é a grafia — `entendirnento` e `jurisprudêneia` não entram como
# literais. Codifica-se a confusão, e toda palavra afetada passa a casar.
CONFUSIONS = {
    "m": ("m", "rn"),
    "e": ("e", "c"),
    "c": ("c", "e"),
    "o": ("o", "0"),
    "l": ("l", "1"),
    "i": ("i", "l", "1"),
    "s": ("s", "5"),
    "g": ("g", "9"),
    "b": ("b", "6"),
}


def noisy(word: str) -> str:
    """A palavra como regex tolerante às confusões de OCR, letra a letra."""
    return "".join(
        f"(?:{'|'.join(CONFUSIONS[letter])})" if letter in CONFUSIONS else re.escape(letter)
        for letter in word
    )


VAGUE_CASE_LAW = re.compile(
    rf"(?:{noisy('julgado')}|{noisy('precedente')}|ac(?:ó|o)rd(?:ã|a)o|"
    rf"{noisy('entendimento')}|Reclama(?:ç|c)(?:ã|a)o|"
    rf"Agravo\s+em\s+Recurso\s+Especial|{noisy('jurisprud')}(?:ê|e){noisy('ncia')})"
    r"\b[^.]{0,60}?"
    rf"(?:do\s+ST[FMJ]|desta\s+Corte|{noisy('sumulad')}[oa]|pac(?:í|i)fica|"
    rf"{noisy('proferid')}[oa]\s+em\s+\d{{4}}|de\s+\d{{4}})[^.]{{0,80}}",
    re.IGNORECASE,
)
VAGUE_STATUTE = re.compile(
    rf"(?:{noisy('normas')}?|{noisy('dispositivo')}|legisla(?:ç|c)(?:ã|a)o|"
    rf"{noisy('artigo')}\s+{noisy('correspondente')})"
    rf"[^.]{{0,60}}?(?:de\s+reg(?:ê|e)ncia|{noisy('constitucional')}|"
    rf"{noisy('correspondente')})[^.]{{0,50}}",
    re.IGNORECASE,
)

_PATTERNS = (
    (CASE_LAW_WITH_NUMBER, "jurisprudencia"),
    (PRECEDENT_SUMMARY, "jurisprudencia"),
    (STATUTE, "lei"),
    (VAGUE_CASE_LAW, "jurisprudencia"),
    (VAGUE_STATUTE, "lei"),
)

_TRIM = " .,;:"


@dataclass(frozen=True)
class RegexMatch:
    start: int
    end: int
    text: str
    kind: str


def _trimmed(document: str, start: int, end: int) -> tuple[int, int] | None:
    """Apara pontuação e espaço das bordas — o regex costuma engolir o ponto final."""
    while end > start and document[end - 1] in _TRIM:
        end -= 1
    while start < end and document[start] in _TRIM:
        start += 1
    return (start, end) if end - start >= 3 else None


def find(document: str) -> list[RegexMatch]:
    """Acha citações por padrão, buscando no texto normalizado de cada bloco útil.

    Buscar no bloco em vez do documento cru faz os dois ramos do híbrido lerem o mesmo
    texto: a quebra de linha dentro do identificador já virou espaço, o NBSP também, e o
    preâmbulo já saiu por uma regra medida em vez de heurística de posição.

    A normalização é 1:1, então um offset dentro do bloco somado ao `start` dele vale no
    arquivo original sem conversão. O `text` do resultado sai do documento **cru** pelo
    span, porque é o que o contrato de submissão cobra.
    """
    found: dict[tuple[int, int], RegexMatch] = {}
    for block in usable_blocks(document):
        for pattern, kind in _PATTERNS:
            for match in pattern.finditer(block.text):
                local = _trimmed(block.text, match.start(), match.end())
                if local is None:
                    continue
                span = (
                    block.absolute_position(local[0]),
                    block.absolute_position(local[1]),
                )
                found[span] = RegexMatch(
                    start=span[0], end=span[1], text=document[span[0] : span[1]], kind=kind
                )
    return sorted(found.values(), key=lambda m: m.start)
