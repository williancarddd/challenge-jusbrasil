# -*- coding: utf-8 -*-
"""Catálogo de regex de extração de citações + distratores.

extract_citacoes(texto) -> list[dict] com inicio, fim, trecho, tipo e, quando
aplicável, o já pré-classificado ("incompleta" para as frases vagas) ou os
campos crus (numero, codigo, tribunal etc.) que resolve.py usa para decidir a
classe.
"""
import difflib
import re

from normalize import NUM_TOKEN_RE, only_digits, strip_accents

# --------------------------------------------------------------- distratores

_DISTRACTOR_ANYWHERE_RE = re.compile(
    r"\bOAB[/\s]*\w{0,2}\s*[\d.]{4,}\b"
    r"|\bProtocolo\s*n?[º°.]?\s*[\d.\-]{4,}\b"
    r"|\bfls\.?\s*\d{1,5}\s*/\s*\d{1,5}\b"
    r"|R\$\s*[\d.,]{3,}"
    r"|\bMemorial\s*n?[º°.]?\s*[\d./\-]{3,}\b",
    flags=re.IGNORECASE,
)

_ALLCAPS_TITLE_RE = re.compile(r"^[ \t]*[A-ZÀ-Ú0-9][A-ZÀ-Ú0-9 \-,ºª.]{1,90}[ \t]*$")


def find_header_end(texto: str) -> int:
    """Fim da zona de cabeçalho (letterhead, partes, autos, protocolo) —
    nenhuma citação de jurisprudência aparece antes disso nos documentos do
    desafio. É o fim do primeiro bloco (separado por linha em branco) que:
    não é o primeiro bloco do documento (esse é sempre o letterhead/vara) e
    é uma linha curta toda em maiúsculas (o título da peça: MEMORIAL,
    PARECER, AGRAVO REGIMENTAL..., CONTRARRAZÕES...)."""
    pos = 0
    for i, bloco in enumerate(texto[:1200].split("\n\n")):
        bloco_end = pos + len(bloco)
        if i > 0 and _ALLCAPS_TITLE_RE.match(bloco.strip()):
            return bloco_end
        pos = bloco_end + 2  # os dois '\n' do separador
    return min(len(texto), 300)


def _distractor_spans(texto: str):
    return [m.span() for m in _DISTRACTOR_ANYWHERE_RE.finditer(texto)]


def _overlaps(span, spans):
    s0, s1 = span
    for a0, a1 in spans:
        if s0 < a1 and a0 < s1:
            return True
    return False


# --------------------------------------------------------------- jurisprudência numerada

_CAND_NUM_RE = NUM_TOKEN_RE

_TRIGGER_WORDS = {
    "resp", "aresp", "are", "re", "rhc", "rms", "hc", "ms", "rcl", "reclamacao",
    "apl", "apelacao", "rse", "recurso", "agravo", "embargos", "edcl", "agrg",
    "agint", "agr", "habeas", "corpus", "mandado", "seguranca", "suspensao",
    "liminar", "sentenca", "especial", "extraordinario", "ordinario",
    "eleitoral", "revista", "instrumento", "interno", "regimental",
    "declaracao", "infringentes", "nulidade", "processo", "autos", "tst",
    "airr", "arr", "rr", "ed", "eds", "classe", "estrito", "sentido", "execucao",
    "cautelar", "regressiva", "rec", "ar", "esp", "recl", "agresp", "tema",
    "repercussao", "respe", "int", "r", "rp",
}
# prefixos de formas fusionadas (sem espaço) que carregam um gatilho —
# ex.: "AREspEI", "AgRESP" — checados por startswith, não por igualdade.
_TRIGGER_PREFIXES = ("aresp", "agr", "agint", "agrg", "edcl", "resp", "recl")
_CONNECTOR_WORDS = {"no", "na", "nos", "nas", "de", "do", "da", "dos", "das",
                     "em", "com", "e"}
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]+")
_UF_SUFFIX_RE = re.compile(
    r"\s*[\-\/(]\s*([A-Za-zÀ-ÿ]{2}|[A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+){0,3})\)?"
)


_SKIP_WORDS = {"n"}  # resíduo de "nº"/"n°"/"n." após a quebra de tokenização


def _looks_like_abbrev(word: str) -> bool:
    """Abreviações processuais (AgR, AI, EDs, RESPE, H, C, ARR...) não cabem
    num vocabulário fechado — mas quase sempre têm maiúscula fora da
    primeira posição, ou são bem curtas e começam maiúsculas."""
    if len(word) <= 4 and word[0].isupper():
        return True
    return bool(re.search(r"[A-Z]", word[1:]))


def _prefix_start(texto: str, num_start: int):
    """Anda para trás a partir de `num_start` juntando palavras-gatilho,
    conectores e abreviações contíguas; retorna o início do trecho (ou None
    se não achar nenhuma palavra-gatilho — não é citação, é só um número
    solto)."""
    window_start = max(0, num_start - 160)
    words = list(_WORD_RE.finditer(texto, window_start, num_start))
    if not words:
        return None
    i = len(words) - 1
    found_trigger = False
    start = num_start
    while i >= 0:
        w = words[i]
        gap = texto[w.end():start]
        if len(gap) > 3:  # distância grande demais: não é mais o mesmo rótulo
            break
        raw = w.group(0)
        key = strip_accents(raw).lower()
        if key in _TRIGGER_WORDS or (len(key) > 4 and key.startswith(_TRIGGER_PREFIXES)):
            found_trigger = True
            start = w.start()
        elif key in _CONNECTOR_WORDS or key in _SKIP_WORDS or _looks_like_abbrev(raw):
            start = w.start()
        else:
            break
        i -= 1
    return start if found_trigger else None


_REPERCUSSAO_GERAL_RE = re.compile(r"\s*d?[ae]?\s*repercuss[ãa]o\s+geral\b", re.IGNORECASE)


def extract_jurisprudencia_numeradas(texto: str, header_end: int, excl_spans):
    out = []
    for m in _CAND_NUM_RE.finditer(texto):
        ns, ne = m.span()
        if ns < header_end:
            continue
        digits = only_digits(m.group(0))
        if len(digits) < 4:
            continue
        start = _prefix_start(texto, ns)
        if start is None:
            continue
        end = ne
        uf = _UF_SUFFIX_RE.match(texto, ne)
        if uf:
            end = uf.end()
        else:
            rg = _REPERCUSSAO_GERAL_RE.match(texto, ne)
            if rg:
                end = rg.end()
        span = (start, end)
        if _overlaps(span, excl_spans):
            continue
        out.append({"inicio": start, "fim": end, "tipo": "jurisprudencia",
                     "via": "numero"})
    return out


# --------------------------------------------------------------- súmula

_SUMULA_RE = re.compile(
    r"[s5][uú]m(?:ula)?\.?\w*\s*(?P<vinc>vinculante\s*)?"
    r"n?[º°.]?\s*(?P<num>\d+)"
    r"(?:\s*(?:do|da)\s*(?P<trib>STF|STJ|TST|TSE|STM))?",
    flags=re.IGNORECASE,
)


def extract_sumulas(texto: str, header_end: int):
    out = []
    for m in _SUMULA_RE.finditer(texto):
        if m.start() < header_end:
            continue
        trib = m.group("trib")
        out.append({"inicio": m.start(), "fim": m.end(), "tipo": "jurisprudencia",
                     "via": "sumula", "numero": m.group("num"),
                     "vinculante": bool(m.group("vinc")), "tribunal": trib.upper() if trib else None})
    return out


# --------------------------------------------------------------- lei / artigo

_CODIGO_ALT = (
    r"C[óo0]digo\s+de\s+Processo\s+Civil|C[óo0]digo\s+Civil|"
    r"C[óo0]digo\s+de\s+Processo\s+Penal|C[óo0]digo\s+Penal\s+Militar|"
    r"C[óo0]digo\s+de\s+Defesa\s+do\s+Consumidor|C[óo0]digo\s+Eleitoral|"
    r"Consolida[çc][ãa]o\s+das\s+Leis\s+do\s+Trabalho|"
    r"CPC|CLT|CPP|CPM|CDC|"
    r"Constitui[çc][ãa]o(?:\s+\w+){0,3}|CF(?:/88)?|"
    r"Lei\s+Complementar\s*n?[º°.]?\s*\d+(?:/\d+)?|"
    r"Lei\s*n?[º°.]?\s*[\d.]+\s*/\s*\d{2,4}"
)

_LEI_ART_RE = re.compile(
    r"art(?:igo)?s?\.?\s*(?P<num>\d[\d.]*\d|\d)[º°]?"
    r"[\w\s,.'\"º°ª§\-]{0,40}?"
    r"(?:do|da)\s+(?P<codigo>" + _CODIGO_ALT + r")",
    flags=re.IGNORECASE,
)


def extract_lei_artigos(texto: str, header_end: int, excl_spans):
    out = []
    for m in _LEI_ART_RE.finditer(texto):
        span = (m.start(), m.end())
        if span[0] < header_end or _overlaps(span, excl_spans):
            continue
        out.append({"inicio": span[0], "fim": span[1], "tipo": "lei", "via": "artigo",
                     "numero": m.group("num"), "codigo": m.group("codigo")})
    return out


# --------------------------------------------------------------- vagas com slots (sempre incompleta)

_TRIB_ALT = r"STF|STJ|TST|TSE|STM"
_VAGUE_SLOT_PATTERNS = [
    re.compile(
        r"(?:julgado|ac[óo]rd[ãa]o|precedente)\s+d[oa]\s+(?:" + _TRIB_ALT + r")\b"
        r"(?:(?!\.\s[A-Z])[\s\S]){0,80}?(?:19|20)\d{2}"
        r"(?:(?!\.\s[A-Z])[\s\S]){0,60}?relat[oó]ria?\s+d[eac]\s+[A-ZÀ-Ú][\wÀ-ÿ.]*(?:\s+[A-ZÀ-Ú][\wÀ-ÿ.]*){0,4}",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?:Reclama[çc][ãa]o|Rcl)\b(?:\s+d[oa]\s+(?:" + _TRIB_ALT + r"))?,?\s*de\s+(?:19|20)\d{2},?"
        r"\s*Rel\.?\s*Min\.?\s*[A-ZÀ-Ú][\wÀ-ÿ.]*(?:\s+[A-ZÀ-Ú][\wÀ-ÿ.]*){0,4}",
        flags=re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:Agravo\s+em\s+Recurso\s+Especial|Recurso\s+em\s+Habeas\s+Corpus|APL|"
        r"Apela[çc][ãa]o|Embargos\s+de\s+Declara[çc][ãa]o)\s*"
        r"(?:d[oa]\s+(?:" + _TRIB_ALT + r"))?,?\s*"
        r"de\s+(?:19|20)\d{2},?\s*Rel\.?\s*Min\.?\s*[A-ZÀ-Ú][\wÀ-ÿ.]*(?:\s+[A-ZÀ-Ú][\wÀ-ÿ.]*){0,4}",
        flags=re.IGNORECASE | re.DOTALL,
    ),
]


def extract_vagas_slot(texto: str, header_end: int):
    out = []
    for pat in _VAGUE_SLOT_PATTERNS:
        for m in pat.finditer(texto):
            if m.start() < header_end:
                continue
            out.append({"inicio": m.start(), "fim": m.end(), "tipo": "jurisprudencia",
                        "via": "vaga_slot"})
    return out


# --------------------------------------------------------------- vagas fixas (sempre incompleta)

# cada template é uma sequência de palavras-alvo (já sem acento, minúsculas);
# casamento é por similaridade palavra-a-palavra (tolera ruído OCR tipo
# "entendirnento"/"entendimento") diretamente sobre o texto original, para
# nunca perder o alinhamento de offsets.
_VAGUE_FIXED_JURIS = [
    "jurisprudencia pacifica desta corte".split(),
    "jurisprudencia consolidada dos tribunais superiores".split(),
    "precedentes desta casa em situacoes analogas".split(),
    "entendimento sumulado sobre a materia".split(),
]
_VAGUE_FIXED_LEI = [
    "normas de regencia da materia".split(),
    "dispositivo legal de regencia".split(),
    "legislacao de regencia da materia".split(),
]
# "recente acórdão da <turma>" e "artigo correspondente do <código>" têm um
# slot de 1-2 palavras livres no meio — tratados à parte.
_VAGUE_FIXED_WITH_GAP = [
    (["recente", "acordao", "da"], ["turma"], "jurisprudencia"),
    (["artigo", "correspondente", "do", "codigo", "de"], [], "lei"),
]


def _word_sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _match_template(words, template, start_i):
    if start_i + len(template) > len(words):
        return False
    for j, target in enumerate(template):
        actual = strip_accents(words[start_i + j][0]).lower()
        if _word_sim(actual, target) < 0.92:
            return False
    return True


def extract_vagas_fixas(texto: str, header_end: int):
    words = [(m.group(0), m.start(), m.end()) for m in _WORD_RE.finditer(texto)]
    out = []
    for templates, tipo in ((_VAGUE_FIXED_JURIS, "jurisprudencia"),
                            (_VAGUE_FIXED_LEI, "lei")):
        for template in templates:
            for i in range(len(words)):
                if words[i][1] < header_end:
                    continue
                if _match_template(words, template, i):
                    span_start = words[i][1]
                    span_end = words[i + len(template) - 1][2]
                    out.append({"inicio": span_start, "fim": span_end, "tipo": tipo,
                                "via": "vaga_fixa"})
    for pre, post, tipo in _VAGUE_FIXED_WITH_GAP:
        n = len(pre)
        for i in range(len(words)):
            if words[i][1] < header_end:
                continue
            if not _match_template(words, pre, i):
                continue
            j = i + n
            end_idx = i + n - 1
            if post:
                # aceita até 2 palavras de gap antes do resto do molde
                matched = False
                for gap in range(0, 3):
                    if _match_template(words, post, j + gap):
                        end_idx = j + gap + len(post) - 1
                        matched = True
                        break
                if not matched:
                    continue
            span_start, span_end = words[i][1], words[end_idx][2]
            out.append({"inicio": span_start, "fim": span_end, "tipo": tipo,
                        "via": "vaga_fixa"})
    return out


# --------------------------------------------------------------- orquestração

def extract_raw(texto: str):
    header_end = find_header_end(texto)
    excl = _distractor_spans(texto)
    citas = []
    citas += extract_sumulas(texto, header_end)
    citas += extract_lei_artigos(texto, header_end, excl)
    vagas_slot = extract_vagas_slot(texto, header_end)
    citas += vagas_slot
    citas += extract_vagas_fixas(texto, header_end)
    # o "de <ANO>" das citações vagas com slot não pode virar "número de
    # processo" para o extrator de jurisprudência numerada
    excl_numero = excl + [(c["inicio"], c["fim"]) for c in vagas_slot]
    citas += extract_jurisprudencia_numeradas(texto, header_end, excl_numero)
    return _dedupe(citas)


def _iou(a, b):
    inter = max(0, min(a["fim"], b["fim"]) - max(a["inicio"], b["inicio"]))
    if inter == 0:
        return 0.0
    union = (a["fim"] - a["inicio"]) + (b["fim"] - b["inicio"]) - inter
    return inter / union


def _dedupe(citas):
    citas = sorted(citas, key=lambda c: (c["fim"] - c["inicio"]), reverse=True)
    kept = []
    for c in citas:
        if any(_iou(c, k) >= 0.5 for k in kept):
            continue
        kept.append(c)
    kept.sort(key=lambda c: c["inicio"])
    return kept
