# -*- coding: utf-8 -*-
"""Extração de spans por cadeia de classes flexível + número ruidoso (OCR, quebra)."""
import re

from .fuzzy import iter_proximos

INCIDENTES = [
    "Embargos de Declaracao",
    "Agravo em Recurso Especial",
    "Recurso em Mandado de Seguranca",
    "Recurso em Habeas Corpus",
    "Recurso em Sentido Estrito",
    "Recurso Especial Eleitoral",
    "Suspensao de Liminar e de Sentenca",
    "Agravo de Instrumento",
    "Agravo Regimental",
    "Agravo Interno",
    "Recurso Especial",
    "Habeas Corpus",
    "Mandado de Seguranca",
    "Reclamacao",
    "Apelacao",
    "AREspEI",
    "AgR-REspe",
    "AGR-RESPE",
    "AgR-AI",
    "AgREsp",
    "AREsp",
    "A.REsp",
    "REspe",
    "REsp",
    "RESP",
    "ARESP",
    "Rec. Esp",
    "R.Esp",
    "Ag. Int",
    "AgInt",
    "AgRg",
    "AG.REG",
    "Recl",
    "RCL",
    "Rcl",
    "RHC",
    "RMS",
    "RSE",
    "APL",
    "ARR",
    "H.C",
    "HC",
    "RE",
    "AR",
    "AI",
    "EDcl",
    "EDs",
    "ED",
    "R-Rp",
    "Rp",
    "Terceiro",
]

_ACC = {
    "a": "aáàãâ",
    "e": "eéê",
    "i": "ií",
    "o": "oóôõ",
    "u": "uú",
    "c": "cç",
    "s": "s5",
}


def _flex(s):
    out = []
    letras = sum(1 for ch in s if ch.isalpha())
    curto = letras <= 4 and " " not in s
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isalpha():
            alts = _ACC.get(ch.lower(), ch.lower())
            out.append(f"[{alts}]\\.?")
        elif ch == " ":
            out.append(r"\s+")
        elif ch == ".":
            out.append(r"[\s.]*")
        elif ch == "-":
            out.append(r"[\s\-]*")
        else:
            out.append(re.escape(ch))
        i += 1
    body = "".join(out)
    if curto:
        body += r"(?![a-z0-9])"
    return body


_ALT = "|".join(_flex(s) for s in sorted(INCIDENTES, key=len, reverse=True))
_CON = r"(?:n[oa]s?|em|na)"
RE_CADEIA = re.compile(
    rf"(?:{_ALT})(?:\s+(?:{_CON}\s+)?(?:{_ALT})){{0,6}}",
    re.IGNORECASE,
)

RE_TST = re.compile(
    r"(?:processo\s+n[ºo°.\u00ba]*\s*)?(?:TST[\s\-]*)?"
    r"(?:(?:ED|E|Ag|ARR|RR)[\s\-]*)+"
    r"\d{2,6}\s*-\s*\d{2}\s*\.\s*\d{4}\s*\.\s*\d\s*\.\s*\d{2}\s*\.\s*\d{4}",
    re.IGNORECASE,
)

RE_SUMULA = re.compile(
    r"(?:[5s][uú]m(?:ula|\.)|s[uú]m\.)\s*(?:vinculante)?\s*"
    r"n?[ºo°.\u00ba]*\s*\d+(?:\s+do\s+[A-Z]{2,4})?",
    re.IGNORECASE,
)

RE_LEI = re.compile(
    r"\bart(?:igo|\.)?\s+"
    r"\d+(?:\.\d{3})*"
    r"[ºo°]?"
    r"(?:\s*,?\s*§\s*[\dºo°A\-]+)?"
    r"(?:\s*,?\s*[IVXLC]+)?"
    r"(?:\s*,?\s*'[a-z]')?"
    r"(?:\s*,?\s*(?:inciso|al[íi]nea)\s*\S+)?"
    r"(?:\s*,?\s*d[oae]\s+[^.,;]{2,70})?",
    re.IGNORECASE,
)

RE_DISTRATOR = re.compile(
    r"(?:OAB|fls?\.|folhas?|protocolo|R\$|processo\s+n|autos\s+n)",
    re.IGNORECASE,
)

_NOME = (
    r"(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚáéíóúàêõçã.]+"
    r"(?:[\s\n]+(?:d[eao]s?[\s\n]+)?"
    r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚáéíóúàêõçã.]+){0,6})"
)
_TRIB = r"(?:ST[FMJ]|TST|TSE|STM|STJ)"
_ANO = r"\d{4}"

_CONT = {
    "julgado": re.compile(
        rf"\s+do\s+{_TRIB}\s+\w+\s+em\s+{_ANO}\s+pela\s+relatoria\s+d\w\s+{_NOME}",
        re.IGNORECASE,
    ),
    "precedente": re.compile(
        rf"(?:s)?\s+(?:do\s+{_TRIB}\s+de\s+{_ANO},?\s+d[aoe]\s+relatoria\s+d\w\s+{_NOME}"
        r"|firmado\s+em\s+sede\s+de\s+recurso\s+repetitivo"
        r"|desta\s+Casa\s+em\s+situa[cç][oõ]es\s+an[aá]logas)",
        re.IGNORECASE,
    ),
    "precedentes": None,
    "jurisprudencia": re.compile(
        r"\s+(?:pac[ií]fica\s+desta\s+Corte|consolidada\s+dos\s+tribunais\s+superiores)",
        re.IGNORECASE,
    ),
    "entendimento": re.compile(
        r"\s+sumulado\s+sobre\s+a\s+mat[eé]ria",
        re.IGNORECASE,
    ),
    "acordao": re.compile(
        rf"\s+(?:do\s+{_TRIB}\s+julgado\s+em\s+{_ANO}\s+sob\s+relatoria\s+d\w\s+{_NOME}"
        r"|da\s+Segunda\s+Turma)",
        re.IGNORECASE,
    ),
    "orientacao": re.compile(
        r"\s+jurisprudencial\s+da\s+Corte\s+Superior",
        re.IGNORECASE,
    ),
    "verbete": re.compile(
        r"\s+sumular\s+aplic[aá]vel\s+[aà]\s+esp[eé]cie",
        re.IGNORECASE,
    ),
    "recente": re.compile(
        r"\s+ac[oó]rd[aã]o\s+da\s+Segunda\s+Turma",
        re.IGNORECASE,
    ),
    "reclamacao": re.compile(
        rf"\s+do\s+STF,?\s+de\s+{_ANO},?\s+Rel\.?\s+Min\.?\s+{_NOME}",
        re.IGNORECASE,
    ),
    "reiterados": re.compile(
        r"\s+precedentes\s+do\s+Superior\s+Tribunal\s+de\s+Justi[cç]a",
        re.IGNORECASE,
    ),
}

_CONT_RCL = re.compile(
    rf"\s+de\s+{_ANO},?\s+Rel\.?\s+Min\.?\s+{_NOME}",
    re.IGNORECASE,
)
_CONT_APL = re.compile(
    rf"\s+de\s+{_ANO},?\s+Rel\.?\s+Min\.?\s+{_NOME}",
    re.IGNORECASE,
)
_CONT_ARESP = re.compile(
    rf"\s+do\s+{_TRIB},?\s+de\s+{_ANO},?\s+Rel\.?\s+Min\.?\s+{_NOME}",
    re.IGNORECASE,
)
_CONT_RHC = re.compile(
    rf"\s+do\s+{_TRIB},?\s+de\s+{_ANO},?\s+Rel\.?\s+Min\.?\s+{_NOME}",
    re.IGNORECASE,
)

_CONT_LEI = {
    "normas": re.compile(r"\s+de\s+reg[eê]ncia\s+da\s+mat[eé]ria", re.IGNORECASE),
    "norma": re.compile(r"\s+de\s+reg[eê]ncia\s+da\s+mat[eé]ria", re.IGNORECASE),
    "dispositivo": re.compile(
        r"\s+(?:constitucional\s+invocado\s+na\s+origem|legal\s+de\s+reg[eê]ncia)",
        re.IGNORECASE,
    ),
    "legislacao": re.compile(r"\s+de\s+reg[eê]ncia\s+da\s+mat[eé]ria", re.IGNORECASE),
    "artigo": re.compile(
        r"\s+correspondente\s+d[oa]\s+C[oó]digo\s+de\s+Processo\s+Civil",
        re.IGNORECASE,
    ),
    "lei": re.compile(
        r"\s+que\s+disciplina\s+a\s+prescri[cç][aã]o\s+no\s+caso",
        re.IGNORECASE,
    ),
}

_OCR_COLADO = set("OolISsGgBb")
_WS = set(" \t\n\r\xa0")
_SEP = set(".-–—") | _WS


def _cabecalho_len(texto: str) -> int:
    m = re.search(r"\n\s*\n", texto)
    return min(m.start() if m else 300, 300)


def _ano_relator(texto, ini, fim):
    blob = re.sub(r"\D", "", texto[ini:fim])
    if len(blob) != 4:
        return False
    try:
        ano = int(blob)
    except ValueError:
        return False
    if ano < 1980 or ano > 2035:
        return False
    return bool(re.search(r"rel\.|relator|min\.", texto[fim:fim + 40], re.I))


def _consome_numero(texto, pos):
    n = len(texto)
    i = pos
    while i < n and texto[i] in _WS:
        i += 1
    m = re.match(
        r"(?:n[uú]mero|n[ºo°.\u00ba]|n)(?=\s*[\d.OolIS])",
        texto[i:],
        re.IGNORECASE,
    )
    if m:
        i += m.end()
        while i < n and texto[i] in _WS:
            i += 1
    start = i
    digits = 0
    last = i
    j = i
    while j < n and (j - i) < 52:
        c = texto[j]
        if c.isdigit():
            digits += 1
            last = j + 1
            j += 1
        elif c in _OCR_COLADO and j > i and texto[j - 1] not in _WS:
            digits += 1
            last = j + 1
            j += 1
        elif c in _SEP:
            j += 1
        else:
            break
    if digits < 4:
        return None
    end = last
    muf = re.match(r"\s*[/\-(–—]\s*[A-Za-z]{2}\s*\)?", texto[end:])
    if muf:
        end += muf.end()
    if _ano_relator(texto, start, end):
        return None
    return end


def _apara(texto, ini, fim):
    s = texto[ini:fim]
    while s and s[-1] in " .,;:":
        s = s[:-1]
        fim -= 1
    while s and s[0] in " .,;:":
        s = s[1:]
        ini += 1
    return ini, fim, s


def extrair(texto: str):
    achados = {}
    cab = _cabecalho_len(texto)

    def add(ini, fim, tipo, vaga):
        ini, fim, s = _apara(texto, ini, fim)
        if fim - ini < 3:
            return
        if ini < cab and RE_DISTRATOR.search(texto[max(0, ini - 30):fim]):
            return
        achados[(ini, fim)] = {
            "inicio": ini,
            "fim": fim,
            "trecho": s,
            "tipo": tipo,
            "_vaga": vaga,
        }

    for m in RE_CADEIA.finditer(texto):
        fim = _consome_numero(texto, m.end())
        if fim is not None:
            if m.start() < cab and RE_DISTRATOR.search(
                texto[max(0, m.start() - 25):m.start()]
            ):
                continue
            add(m.start(), fim, "jurisprudencia", False)
            continue
        for rx in (_CONT_RCL, _CONT_APL, _CONT_ARESP, _CONT_RHC):
            mv = rx.match(texto, m.end())
            if mv:
                add(m.start(), mv.end(), "jurisprudencia", True)
                break

    for m in RE_TST.finditer(texto):
        add(m.start(), m.end(), "jurisprudencia", False)

    for m in RE_SUMULA.finditer(texto):
        add(m.start(), m.end(), "jurisprudencia", False)

    for ini, fim, _alvo in iter_proximos(texto, ["sumula"]):
        ms = re.match(
            r"(?:\s+vinculante)?\s*n?[ºo°.\u00ba]*\s*\d+(?:\s+do\s+[A-Z]{2,4})?",
            texto[fim:],
            re.IGNORECASE,
        )
        if ms:
            add(ini, fim + ms.end(), "jurisprudencia", False)

    for m in RE_LEI.finditer(texto):
        add(m.start(), m.end(), "lei", False)

    for ini, fim, _alvo in iter_proximos(texto, ["tema"]):
        ms = re.match(
            r"\s+[\d.]+(?:\s+da\s+repercuss[aã]o\s+geral)?",
            texto[fim:],
            re.IGNORECASE,
        )
        if ms:
            add(ini, fim + ms.end(), "jurisprudencia", False)

    ancoras_j = [
        "julgado", "precedente", "precedentes", "jurisprudencia", "entendimento",
        "acordao", "orientacao", "verbete", "recente", "reclamacao", "reiterados",
    ]
    for ini, fim, alvo in iter_proximos(texto, ancoras_j):
        chave = "precedente" if alvo == "precedentes" else alvo
        rx = _CONT.get(chave)
        if not rx:
            continue
        mv = rx.match(texto, fim)
        if mv:
            add(ini, mv.end(), "jurisprudencia", True)

    for ini, fim, alvo in iter_proximos(
        texto, ["normas", "norma", "dispositivo", "legislacao", "artigo", "lei"]
    ):
        rx = _CONT_LEI.get(alvo)
        if not rx:
            continue
        mv = rx.match(texto, fim)
        if mv:
            add(ini, mv.end(), "lei", True)

    return _compactar(achados)


def _compactar(achados):
    items = sorted(achados.values(), key=lambda d: (d["inicio"], -(d["fim"] - d["inicio"])))
    kept = []
    for c in items:
        drop = False
        substitui = []
        for k in kept:
            if c["fim"] <= k["inicio"] or c["inicio"] >= k["fim"]:
                continue
            c_in_k = c["inicio"] >= k["inicio"] and c["fim"] <= k["fim"]
            k_in_c = k["inicio"] >= c["inicio"] and k["fim"] <= c["fim"]
            if k["_vaga"] and not c["_vaga"]:
                substitui.append(k)
                continue
            if c["_vaga"] and not k["_vaga"]:
                drop = True
                break
            if k_in_c and not c_in_k:
                substitui.append(k)
                continue
            if c_in_k:
                drop = True
                break
            if (c["fim"] - c["inicio"]) > (k["fim"] - k["inicio"]):
                substitui.append(k)
            else:
                drop = True
                break
        if drop:
            continue
        for k in substitui:
            kept.remove(k)
        kept.append(c)
    return sorted(kept, key=lambda d: d["inicio"])
