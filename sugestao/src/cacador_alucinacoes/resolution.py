"""Fase 2: resolver a citação contra a cobertura congelada e decidir a classe.

A regra de classe é a do enunciado, e ela é sobre **cardinalidade da consulta**:

    exatamente 1 candidato  -> real        (`id_canonico` = coluna `id` do registro)
    0 candidatos            -> inventada   (buscável, mas não existe na cobertura)
    2 ou mais candidatos    -> incompleta  (buscável, sem critério de desempate)
    consulta não formulável -> incompleta  ("a jurisprudência pacífica desta Corte")

O que faz a nota não é resolver — é acertar as três classes. Medido sobre as 225 do
gabarito, os dois erros que mais custam são simétricos e vêm do mesmo lugar: devolver
candidato quando não devia (uma `inventada` vira `real` e dispara a penalidade τ) e não
devolver quando devia (uma `real` vira `inventada`).

Há **três caminhos de resolução**, porque a base guarda três coisas diferentes:

- **acórdão** (998 registros): busca de frase no índice FTS pelo número normalizado. É o
  caminho medido — acha o registro certo em 77 de 77 das citações `real` do gabarito.
- **dispositivo** (13) e **súmula** (5): não se resolvem por busca. Ver `CATALOGUE`.

O `tipo` do contrato sai da coluna `tipo` do registro quando há resolução; quando não há,
é inferido da forma da citação, que é o único sinal disponível.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from cacador_alucinacoes.goldenset import ROOT

DATABASE = ROOT / "data" / "desafio1_bracis.db"

# Confusões de OCR que a especificação enumera (0<->O, 1<->l, 5<->S) mais as observadas
# no gabarito (g->9). A garantia do ruído é que dígito nunca vira outro dígito — só
# vira letra —, então desfazer a troca é seguro.
OCR_LOOKALIKES = {
    "O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "s": "5",
    "g": "9", "q": "9", "B": "8", "Z": "2", "G": "6",
}

# O rabo do número CNJ é sempre DD.AAAA.J.TR.OOOO = 2+4+1+2+4. O sequencial à esquerda
# varia de 3 a 7 dígitos — os processos eleitorais usam sequencial curto —, então a
# segmentação tem que ser ancorada à direita. Agrupar de três em três, como a
# especificação sugere, só vale para número de STJ.
CNJ_TAIL = 13

# Um ano não é número de processo. Sem esta guarda, `Rcl de 2021, Rel. Min. Rosa Weber`
# — que o enunciado nomeia como `incompleta` — vira uma busca pela frase "2 021", devolve
# um único candidato por acidente e sai classificada `real`. Medido: 19 das 65
# `incompleta` do gabarito caíam nisso.
YEAR = re.compile(r"^(?:19|20)\d{2}$")

# O inverso de OCR_LOOKALIKES. A restauração dígito->letra existe para **reconhecer a
# palavra**, não o número: `5úmula 211 do STJ` não casava com o detector de súmula e a
# citação — que é `real` — saía `incompleta`. Só se aplica onde o dígito está dentro de
# uma palavra, e `º`/`ª` não contam como letra, senão `art. 5º` viraria `art. Sº`.
LETTER_LOOKALIKES = {"0": "o", "1": "l", "5": "S", "8": "B", "6": "G", "9": "g", "2": "Z"}

_SUMMARY = re.compile(r"s[úu]m(?:ula|\.)|verbete", re.IGNORECASE)
_BINDING = re.compile(r"vinculante", re.IGNORECASE)
_STATUTE = re.compile(r"\bart(?:igo|\.|\b)", re.IGNORECASE)
_COURT = re.compile(r"\b(STF|STJ|TST|TSE|STM)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Resolution:
    """O que a fase 2 decidiu, nos campos do contrato."""

    label: str
    canonical_id: str | None
    kind: str
    candidates: int


# ---------------------------------------------------------------- normalização do número


def restore_digits(text: str) -> str:
    """Desfaz letra sósia de OCR **dentro** do número.

    A condição é posicional: o caractere anterior é dígito e o seguinte não é letra.
    Sem ela a troca come a UF (`/SP` -> `/5P`, e o `5` entra no número) e a sigla do
    tribunal (`TST` -> `T5T`). Medido: a versão sem a condição quebrava 11 citações que
    já funcionavam, para consertar 4.
    """
    out = list(text)
    for index, char in enumerate(out):
        if char not in OCR_LOOKALIKES:
            continue
        before = text[index - 1] if index else ""
        after = text[index + 1] if index + 1 < len(text) else ""
        if before.isdigit() and not after.isalpha():
            out[index] = OCR_LOOKALIKES[char]
    return "".join(out)


def number_phrase(text: str) -> str | None:
    """A frase que o FTS indexou para este número, ou `None` se não houver número.

    O tokenizador `unicode61` quebra em qualquer caractere não alfanumérico, então
    `1.741.784` está no índice como três tokens e só casa por busca de frase. Reconstruir
    a sequência de tokens é o passo 1 do §5 da especificação.
    """
    runs = re.findall(r"\d[\d.\-/\s\xa0]*\d", restore_digits(text))
    if not runs:
        return None
    run = max(runs, key=lambda candidate: len(re.sub(r"\D", "", candidate)))
    digits = re.sub(r"\D", "", run)

    if len(digits) >= CNJ_TAIL + 1:
        head, tail = digits[:-CNJ_TAIL], digits[-CNJ_TAIL:]
        return " ".join([head, tail[:2], tail[2:6], tail[6:7], tail[7:9], tail[9:]])
    if YEAR.match(digits) or len(digits) < 4:
        return None

    groups = []
    while len(digits) > 3:
        groups.append(digits[-3:])
        digits = digits[:-3]
    groups.append(digits)
    return " ".join(reversed(groups))


def query_text(document: str, start: int, end: int) -> str:
    """O texto que vai à consulta: o span, estendido se ele cortou um número ao meio.

    A fase 1 devolveu `AgInt no RESP 21737` onde o documento traz `21737l8` — o span
    passa no IoU >= 0,5 e casa com o gabarito, mas o número truncado não resolve e a
    citação, que é `real`, sai `inventada`.

    Estender aqui é legítimo e não mexe em span nenhum: o `inicio`/`fim` submetido
    continua sendo o da fase 1. É a mesma licença que o projeto já reconhece para a fase
    2 — com a posição registrada, o texto pode ser canonizado à vontade para consultar.
    """
    while end < len(document) and (
        document[end].isdigit() or document[end] in OCR_LOOKALIKES
    ):
        end += 1
    while start > 0 and (
        document[start - 1].isdigit() or document[start - 1] in OCR_LOOKALIKES
    ):
        start -= 1
    return document[start:end]


def restore_letters(text: str) -> str:
    """Desfaz dígito sósia de OCR **dentro de uma palavra**, para reconhecê-la.

    Espelha `restore_digits`, e a condição é a simétrica: o caractere seguinte é letra e
    o anterior não é dígito. `º` e `ª` não valem como letra — sem isso `art. 5º` viraria
    `art. Sº` e o número do artigo se perderia.
    """
    out = list(text)
    for index, char in enumerate(out):
        if char not in LETTER_LOOKALIKES:
            continue
        before = text[index - 1] if index else ""
        after = text[index + 1] if index + 1 < len(text) else ""
        if after.isalpha() and after not in "ºª" and not before.isdigit():
            out[index] = LETTER_LOOKALIKES[char]
    return "".join(out)


def small_number(text: str) -> int | None:
    """O número de uma súmula ou de um artigo — o primeiro do trecho.

    Aceita o separador de milhar: `art. 1.134` é o artigo 1134, não o artigo 1. Sem
    isso a citação era resolvida pelo número errado.
    """
    match = re.search(r"\d{1,3}(?:\.\d{3})*", text)
    return int(match.group().replace(".", "")) if match else None


# ---------------------------------------------------------------------------- catálogo

# Os 18 registros que não são acórdão não se resolvem por busca, e o motivo é estrutural:
#
# - **súmula**: o registro NÃO contém o próprio número. O texto é o enunciado
#   ("Não se conhece do recurso especial pela divergência...") e não há coluna que
#   guarde "83". Buscar "Súmula 83" no acervo devolve os acórdãos que a mencionam,
#   nunca a súmula.
# - **dispositivo**: o texto começa com `Art. N`, mas nada diz de qual código. `art. 818`
#   e `art. 373` são ambos "O ônus da prova incumbe" — um é CLT, o outro CPC.
#
# Logo a ligação número -> registro é conhecimento que a base não carrega. Esta tabela é
# o único lugar do projeto com informação de fora dela. Ela é pequena e fechada porque a
# cobertura é congelada: são 5 súmulas e 13 dispositivos, e o enunciado garante que toda
# citação `real` resolve dentro da cobertura — inclusive no conjunto cego.
#
# Ela também é o que protege contra o erro grave. Sem ela, `Súmula 979 do STF`
# (inventada) resolveria pelo tribunal para a única súmula do STF da base e viraria
# `real`, disparando τ. Com ela, 979 não está no catálogo e a citação sai `inventada`,
# que é a classe certa.
SUMMARY_CATALOGUE = {
    ("STJ", 83): 1289710642,
    ("STJ", 211): 1289710776,
    ("STJ", 443): 1289711022,
    ("STF", 10): 1289712966,   # Súmula Vinculante 10
    ("TST", 331): 1431369957,
}

# Apelidos de código como aparecem nas citações -> chave do catálogo de dispositivos.
CODE_ALIASES = {
    "constituicao": "CF", "cf": "CF", "crfb": "CF",
    "codigo de processo civil": "CPC", "cpc": "CPC",
    "codigo de processo penal": "CPP", "cpp": "CPP",
    "codigo penal militar": "CPM", "cpm": "CPM",
    "codigo civil": "CC", "cc": "CC",
    "codigo de defesa do consumidor": "CDC", "cdc": "CDC",
    "consolidacao das leis do trabalho": "CLT", "clt": "CLT",
    "codigo eleitoral": "CE",
    "lei complementar": "LC64", "lc": "LC64",
}

STATUTE_CATALOGUE = {
    ("CE", 276): 10577194,
    ("CPM", 290): 10590194,
    ("CDC", 14): 10606184,
    ("CF", 93): 10626510,
    ("CLT", 896): 10637358,
    ("CF", 7): 10641213,
    ("CF", 5): 10641516,
    ("CLT", 818): 10647746,
    ("CPP", 312): 10652044,
    ("CLT", 477): 10710324,
    ("CC", 186): 10718759,
    ("LC64", 1): 11304039,
    ("CPC", 373): 28893055,
}


# O mesmo código citado pelo número da lei que o instituiu. Não é conhecimento novo — é
# a outra forma de nomear os 13 registros que já estão em STATUTE_CATALOGUE.
STATUTE_NUMBERS = {
    "13105": "CPC", "5869": "CPC", "10406": "CC", "8078": "CDC",
    "5452": "CLT", "3689": "CPP", "1001": "CPM", "4737": "CE", "64": "LC64",
}

# Lei nomeada por número que não é nenhum dos códigos da cobertura. É consulta
# formulável — o participante sabe exatamente o que procurar —, e não existe registro,
# então a classe é `inventada`. Sem esta distinção, `art 189 da Lei nº 9.504/1997` saía
# `incompleta`, que é a classe de quem não consegue nem formular a busca.
OUTSIDE_COVERAGE = "__fora_da_cobertura__"

_LAW_NUMBER = re.compile(
    r"lei\s+(?:complementar\s+)?n?[ºo°.]*\s*([\d.]+)", re.IGNORECASE
)


def _fold(text: str) -> str:
    """Minúsculas, sem acento e com espaço colapsado.

    O colapso não é cosmético: `Código\\nde Processo Penal` traz quebra de linha no meio
    do nome do código, e sem normalizar o apelido não casa — a citação, que é `real`,
    saía `incompleta`.
    """
    import unicodedata

    stripped = unicodedata.normalize("NFD", text.lower())
    without_marks = "".join(c for c in stripped if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", without_marks).strip()


def code_of(text: str) -> str | None:
    """O código citado: pelo apelido, pelo número da lei, ou `OUTSIDE_COVERAGE`."""
    folded = _fold(text)
    for alias, code in sorted(CODE_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if alias in folded:
            return code
    match = _LAW_NUMBER.search(folded)
    if match:
        return STATUTE_NUMBERS.get(match.group(1).replace(".", ""), OUTSIDE_COVERAGE)
    return None


def court_of(text: str) -> str | None:
    match = _COURT.search(text)
    return match.group().upper() if match else None


# Família da classe processual. O número sozinho não identifica o feito: `Reclamação nº
# 22.357/PE` — que é `inventada` — casa com dois registros que citam `MS 22.357`, mesmo
# número e classe diferente. O que importa é o núcleo da classe, não a cadeia recursal:
# `AgRg no REsp 1.234` e `REsp 1.234` são o mesmo registro, porque o agravo é interposto
# *no* recurso especial.
FAMILIES = {
    "resp": r"recurso especial|resp\b|respe\b",
    "aresp": r"agravo em recurso especial|aresp\b",
    "rcl": r"reclamacao|rcl\b",
    "hc": r"habeas corpus|hc\b",
    "ms": r"mandado de seguranca|\bms\b",
    "rms": r"recurso em mandado de seguranca|rms\b",
    "re": r"recurso extraordinario|\bre\b",
    "apl": r"apelacao|apl\b",
    "ai": r"agravo de instrumento|\bai\b",
    "arr": r"recurso de revista|\barr\b|\brr\b",
    "ed": r"embargos",
}

# Quanto do registro se olha antes do número para ler a classe. Medido: 40 e 80 dão o
# mesmo resultado, então fica o menor.
CLASS_LOOKBACK = 40


def families_of(text: str) -> set[str]:
    folded = _fold(text)
    return {name for name, pattern in FAMILIES.items() if re.search(pattern, folded)}


# ---------------------------------------------------------------------------- resolvedor


class Resolver:
    """Resolve uma citação contra a base. Abre o SQLite uma vez e reusa."""

    def __init__(
        self,
        database: Path = DATABASE,
        header_tiebreak: bool = True,
        header_limit: int | None = None,
    ):
        self.connection = sqlite3.connect(database, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.header_tiebreak = header_tiebreak
        self.header_limit = header_limit

    def resolve(self, text: str) -> Resolution:
        # A cópia com dígito sósia desfeito serve para **reconhecer a família** e ler o
        # número de súmula ou artigo. O caminho do acórdão continua no texto original:
        # lá o dígito é o dado, e converter estragaria o número (`6G.838` -> `GG.838`).
        readable = restore_letters(text)
        if _SUMMARY.search(readable):
            return self._resolve_summary(readable)
        if _STATUTE.search(readable):
            return self._resolve_statute(readable)
        return self._resolve_judgment(text)

    # -- súmula ---------------------------------------------------------------------

    def _resolve_summary(self, text: str) -> Resolution:
        number = small_number(text)
        court = court_of(text)
        if number is None:
            return Resolution("incompleta", None, "jurisprudencia", 0)
        # "Súmula Vinculante N" não nomeia tribunal: por definição é do STF.
        if court is None and _BINDING.search(text):
            court = "STF"
        if court is None:
            return Resolution("incompleta", None, "jurisprudencia", 0)
        found = SUMMARY_CATALOGUE.get((court, number))
        if found is None:
            return Resolution("inventada", None, "jurisprudencia", 0)
        return Resolution("real", str(found), "jurisprudencia", 1)

    # -- dispositivo ----------------------------------------------------------------

    def _resolve_statute(self, text: str) -> Resolution:
        number = small_number(text)
        code = code_of(text)
        if number is None or code is None:
            # `as normas de regência da matéria`, `artigo correspondente do CPC` — falta
            # o número ou falta o diploma, e sem os dois não há consulta a formular. É o
            # ramo (a) de `incompleta`.
            return Resolution("incompleta", None, "lei", 0)
        if code is OUTSIDE_COVERAGE:
            # Lei nomeada por número que não está na cobertura congelada: a consulta é
            # formulável e não acha nada, que é a definição de `inventada`.
            return Resolution("inventada", None, "lei", 0)
        found = STATUTE_CATALOGUE.get((code, number))
        if found is None:
            return Resolution("inventada", None, "lei", 0)
        return Resolution("real", str(found), "lei", 1)

    # -- acórdão --------------------------------------------------------------------

    def _resolve_judgment(self, text: str) -> Resolution:
        phrase = number_phrase(text)
        if phrase is None:
            return Resolution("incompleta", None, "jurisprudencia", 0)

        rows = list(
            self.connection.execute(
                "select d.id, d.texto from documentos_fts f "
                "join documentos d on d.rowid = f.rowid "
                "where documentos_fts match ?",
                (f'"{phrase}"',),
            )
        )
        if not rows:
            return Resolution("inventada", None, "jurisprudencia", 0)

        rows = self._same_class(rows, phrase, text)
        if not rows:
            # O número existe no acervo, mas em feitos de outra classe — quem o traz
            # apenas o cita. Consulta formulável sem registro correspondente: `inventada`.
            return Resolution("inventada", None, "jurisprudencia", 0)
        if len(rows) == 1:
            return Resolution("real", str(rows[0]["id"]), "jurisprudencia", 1)

        if self.header_tiebreak:
            winner = self._by_position(rows, phrase)
            if winner is not None:
                return Resolution("real", str(winner), "jurisprudencia", len(rows))
        return Resolution("incompleta", None, "jurisprudencia", len(rows))

    def _same_class(self, rows, phrase: str, text: str):
        """Mantém só os candidatos cuja classe processual bate com a da citação.

        A classe é lida no registro, imediatamente antes da ocorrência do número — é lá
        que ela está tanto no cabeçalho (`RECURSO ESPECIAL Nº 1.741.784`) quanto na
        menção de passagem (`MS 22.357`). Quando a citação não nomeia classe nenhuma a
        verificação é pulada: sem classe para comparar, filtrar só custaria recall.

        Medido nas 225: leva de 64 para 67 as `real` que resolvem sem ambiguidade, de 13
        para 10 as que precisam de desempate, e tira uma `inventada` que casava. Nenhuma
        `real` é perdida.
        """
        wanted = families_of(text)
        if not wanted:
            return rows
        pattern = re.compile(r"\W*".join(re.escape(token) for token in phrase.split()))
        kept = []
        for row in rows:
            match = pattern.search(row["texto"])
            if match is None:
                continue
            before = row["texto"][max(0, match.start() - CLASS_LOOKBACK):match.start()]
            if families_of(before) & wanted:
                kept.append(row)
        return kept

    def _by_position(self, rows, phrase: str) -> int | None:
        """Passo 2 do §5: quem traz o número no cabeçalho **é** o processo.

        Acórdãos citam uns aos outros o tempo todo, então o FTS devolve todo mundo que
        menciona o número. O sinal que separa é a posição: no registro que é o processo,
        o número está nas primeiras dezenas de caracteres; nos que apenas citam, no corpo.
        """
        pattern = re.compile(r"\W*".join(re.escape(token) for token in phrase.split()))
        placed = []
        for row in rows:
            match = pattern.search(row["texto"])
            if match:
                placed.append((match.start(), row["id"]))
        if not placed:
            return None
        placed.sort()
        return placed[0][1]
