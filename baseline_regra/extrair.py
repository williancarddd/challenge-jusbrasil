# -*- coding: utf-8 -*-
"""Extração de spans de citação por regex (baseline determinístico).

Cobre: jurisprudência com número (CNJ e abreviado), súmulas, dispositivos de
lei, e as formas VAGAS (sem identificador buscável) que já nascem incompletas.
Filtra distratores do cabeçalho (autos do próprio doc, OAB, fls., valor).
"""
import re

# ---- padrões de jurisprudência COM número --------------------------------
CLASSES_JURIS = (
    r"AgRg\s+no\s+AREsp|AgInt\s+no\s+AREsp|AgRg\s+no\s+REsp|AgInt\s+no\s+REsp|"
    r"AgInt|AgRg|AREsp|REsp|Recurso\s+Especial|Recurso\s+em\s+Habeas\s+Corpus|"
    r"RHC|Habeas\s+Corpus|HC|Reclama(?:ç|c)(?:ã|a)o|Rcl|RE\b|"
    r"Agravo\s+em\s+Recurso\s+Especial|APL|Apela(?:ç|c)(?:ã|a)o|RSE|"
    r"Recurso\s+em\s+Sentido\s+Estrito|AgProbatório"
)
NUM_CNJ = r"\d{7}\s*-?\s*\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
NUM_MILHAR = r"\d[\d.\s]{2,}\d"      # 1.996.496 / 1576933 / 1.741. 784
UF = r"(?:\s*[/\-(]\s*[A-Za-z]{2}\s*\)?)?"

RE_JURIS_NUM = re.compile(
    rf"(?:{CLASSES_JURIS})\s*(?:n[ºo°.]*\s*)?(?:{NUM_CNJ}|{NUM_MILHAR}){UF}",
    re.IGNORECASE,
)
RE_SUMULA = re.compile(
    r"S(?:ú|u)mula(?:\s+Vinculante)?\s+n?[ºo°.]*\s*\d+(?:\s+do\s+[A-Z]{2,4})?",
    re.IGNORECASE,
)

# ---- dispositivos de lei COM identificador --------------------------------
RE_LEI = re.compile(
    r"art(?:igo|\.)\s*\d+[ºo°]?(?:\s*,?\s*[IVXLC]+)?(?:\s*,?\s*(?:inciso|al(?:í|i)nea)\s*\S+)?"
    r"(?:\s*,?\s*d[oae]\s+[^.,;\n]{2,60})?",
    re.IGNORECASE,
)

# ---- formas VAGAS => já nascem incompletas --------------------------------
RE_VAGA_JURIS = re.compile(
    r"(?:julgado|precedente|ac(?:ó|o)rd(?:ã|a)o|entendimento|Reclama(?:ç|c)(?:ã|a)o|"
    r"Agravo\s+em\s+Recurso\s+Especial|jurisprud(?:ê|e)ncia)\b[^.]{0,120}?"
    r"(?:do\s+ST[FMJ]|desta\s+Corte|sumulad[oa]|pac(?:í|i)fica|"
    r"proferid[oa]\s+em\s+\d{4}|de\s+\d{4})[^.]{0,80}",
    re.IGNORECASE,
)
RE_VAGA_LEI = re.compile(
    r"(?:normas?|dispositivo|legisla(?:ç|c)(?:ã|a)o|artigo\s+correspondente)"
    r"[^.]{0,60}?(?:de\s+reg(?:ê|e)ncia|constitucional|correspondente)[^.]{0,50}",
    re.IGNORECASE,
)

# ---- distratores (nunca são citação) --------------------------------------
RE_DISTRATOR = re.compile(
    r"(?:OAB|fls?\.|folhas?|protocolo|R\$|processo\s+n)", re.IGNORECASE
)

def _cabecalho_len(texto: str) -> int:
    """Fim do cabeçalho: heurística = até a 1ª linha em branco dupla ou 300 chars."""
    m = re.search(r"\n\s*\n", texto)
    return min(m.start() if m else 300, 300)

def extrair(texto: str):
    """Retorna lista de dicts {inicio, fim, trecho, tipo, _vaga}."""
    achados = {}
    cab = _cabecalho_len(texto)

    def add(m, tipo, vaga):
        ini, fim = m.start(), m.end()
        # apara espaços/pontuação nas bordas mantendo codepoints coerentes
        s = texto[ini:fim]
        while s and s[-1] in " .,;:":
            s = s[:-1]; fim -= 1
        while s and s[0] in " .,;:":
            s = s[1:]; ini += 1
        if fim - ini < 3:
            return
        # distrator no cabeçalho: número que é dos próprios autos
        if ini < cab and RE_DISTRATOR.search(texto[max(0, ini-30):fim]):
            return
        achados[(ini, fim)] = {"inicio": ini, "fim": fim, "trecho": s,
                               "tipo": tipo, "_vaga": vaga}

    for m in RE_JURIS_NUM.finditer(texto):
        # não capturar o número dos autos do próprio processo (cabeçalho + distrator lexical)
        if m.start() < cab and RE_DISTRATOR.search(texto[max(0, m.start()-25):m.start()]):
            continue
        add(m, "jurisprudencia", False)
    for m in RE_SUMULA.finditer(texto):
        add(m, "jurisprudencia", False)
    for m in RE_VAGA_JURIS.finditer(texto):
        add(m, "jurisprudencia", True)
    for m in RE_LEI.finditer(texto):
        add(m, "lei", False)
    for m in RE_VAGA_LEI.finditer(texto):
        add(m, "lei", True)

    return sorted(achados.values(), key=lambda d: d["inicio"])
