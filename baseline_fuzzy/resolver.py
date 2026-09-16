# -*- coding: utf-8 -*-
"""Consulta à base com hipóteses de OCR e resolução de súmula por número."""
import re
import sqlite3
import unicodedata

from rapidfuzz import fuzz, process

from .fuzzy import normaliza
from .normalizar import frases_busca, _OCR_TOKEN

_POS_CABECALHO = 250


def _numero_compacto(trecho: str):
    s = trecho.replace("\n", " ")
    melhor, nmelhor = None, 0
    for m in re.finditer(r"\d[\d.OolISsGg\s\-–—]{1,48}[\dOolISsGg]", s):
        compacto = re.sub(r"\s+", "", m.group())
        compacto = re.sub(r"[-/][A-Za-z]$", "", compacto)
        nd = len(re.sub(r"\D", "", compacto))
        if nd > nmelhor:
            nmelhor = nd
            melhor = compacto
    return melhor


def _frases_do_trecho(trecho: str):
    compacto = _numero_compacto(trecho)
    if not compacto:
        return [], ""
    frases = [compacto]
    for tab in _OCR_TOKEN:
        oc = compacto.translate(tab)
        frases.append(oc)
        d = re.sub(r"\D", "", oc)
        if len(d) >= 4:
            frases.extend(frases_busca(d))
    dcru = re.sub(r"\D", "", compacto)
    if len(dcru) >= 4:
        frases.extend(frases_busca(dcru))
    visto, uniq = set(), []
    for f in frases:
        if f and f not in visto and len(f) >= 4:
            visto.add(f)
            uniq.append(f)
    return uniq, compacto


def _id_forte(compacto: str) -> bool:
    if not compacto:
        return False
    d = re.sub(r"\D", "", compacto.translate(_OCR_TOKEN[0]))
    if len(d) >= 20 or len(d) >= 7:
        return True
    return bool(re.search(r"\d{2,}-\d{2}\.\d{4}", compacto))


_LEIS = {
    "cf": "constituicao federal da republica",
    "ce": "codigo eleitoral",
    "cpm": "codigo penal militar",
    "cpp": "codigo de processo penal",
    "cpc": "codigo de processo civil cpc",
    "clt": "clt consolidacao das leis do trabalho",
    "cdc": "codigo de defesa do consumidor",
    "cc": "codigo civil",
    "lc": "lei complementar",
}

_DISP = {
    "cf": "iguais perante a lei estatuto da magistratura trabalhadores urbanos e rurais",
    "ce": "tribunais regionais sao terminativas",
    "cpm": "lugar sujeito a administracao militar substancia entorpecente",
    "cpp": "prisao preventiva garantia da ordem publica",
    "cpc": "onus da prova incumbe ao autor quanto ao fato constitutivo de seu direito",
    "clt": "recurso de revista ao reclamante carteira de trabalho",
    "cdc": "fornecedor de servicos independentemente da existencia de culpa",
    "cc": "violar direito e causar dano a outrem",
    "lc": "sao inelegiveis para qualquer cargo",
}


def _hint_lei(trecho: str):
    n = normaliza(trecho)
    if re.search(r"\bcpc\b", n):
        return "cpc"
    if re.search(r"\bclt\b", n):
        return "clt"
    hit = process.extractOne(
        n,
        _LEIS,
        scorer=fuzz.partial_ratio,
        score_cutoff=70,
    )
    return hit[2] if hit else None


def _hint_disp(texto: str):
    n = normaliza(texto[:600])
    if "reclamante" in n or "recurso de revista" in n or "carteira de trabalho" in n:
        return "clt"
    hit = process.extractOne(
        n,
        _DISP,
        scorer=fuzz.partial_ratio,
        score_cutoff=65,
    )
    return hit[2] if hit else None


class Resolvedor:
    def __init__(self, db_path=None, cx=None):
        self.cx = cx or sqlite3.connect(db_path)
        self.normativos = list(
            self.cx.execute(
                "SELECT id, natureza, tipo, texto, tribunal FROM documentos "
                "WHERE natureza IN ('sumula','dispositivo')"
            )
        )
        self._cabeca = {}

    def _cabeca_de(self, jid):
        if jid not in self._cabeca:
            row = self.cx.execute(
                "SELECT substr(texto,1,320) FROM documentos WHERE id=?", (jid,)
            ).fetchone()
            s = row[0] if row else ""
            s = s.replace("–", "-").replace("—", "-")
            s = unicodedata.normalize("NFKD", s)
            s = "".join(c for c in s if not unicodedata.combining(c))
            s = re.sub(r"\s+", " ", s).strip().lower()
            self._cabeca[jid] = s[:280]
        return self._cabeca[jid]

    def _busca(self, frases):
        q_fts = (
            "SELECT d.id, d.tribunal, instr(d.texto, ?) AS pos "
            "FROM documentos_fts JOIN documentos d ON d.rowid=documentos_fts.rowid "
            "WHERE documentos_fts MATCH ? AND d.natureza='acordao'"
        )
        q_like = (
            "SELECT d.id, d.tribunal, instr(d.texto, ?) AS pos "
            "FROM documentos d WHERE d.natureza='acordao' AND d.texto LIKE ?"
        )
        cab, todos = {}, {}
        for frase in frases:
            if not frase or len(frase) < 4:
                continue
            rows = []
            try:
                rows = list(self.cx.execute(q_fts, (frase, '"%s"' % frase)))
            except sqlite3.OperationalError:
                rows = []
            nd = len(re.sub(r"\D", "", frase))
            if not rows and nd >= 7:
                rows = list(self.cx.execute(q_like, (frase, "%" + frase + "%")))
            for jid, trib, pos in rows:
                if not pos:
                    continue
                todos[jid] = (trib, pos)
                if pos <= _POS_CABECALHO:
                    cab[jid] = (trib, pos)
        return cab, todos

    def _um_feito(self, ids):
        grupos = {}
        for jid in ids:
            grupos.setdefault(self._cabeca_de(jid), []).append(jid)
        if len(grupos) != 1:
            return None
        return str(max(grupos[next(iter(grupos))]))

    def resolver_juris(self, trecho: str):
        if re.search(r"tem[aã]\s+[\d.]+", trecho, re.IGNORECASE):
            return ("inventada", None)
        uniq, compacto = _frases_do_trecho(trecho)
        if not uniq:
            return ("inventada", None)
        cab, todos = self._busca(uniq)
        if cab:
            um = self._um_feito(cab)
            if um:
                return ("real", um)
            return ("incompleta", None)
        if not _id_forte(compacto):
            return ("inventada", None)
        if len(todos) == 1:
            return ("real", str(next(iter(todos))))
        if len(todos) > 1:
            um = self._um_feito(todos)
            if um:
                return ("real", um)
            return ("incompleta", None)
        return ("inventada", None)

    def resolver_sumula(self, trecho: str):
        m = re.search(
            r"(?:[5s][uú]m(?:ula|\.)|s[uú]m\.)\s*(?:vinculante)?\s*"
            r"n?[ºo°.\u00ba]*\s*(\d+)(?:\s+do\s+([A-Z]{2,4}))?",
            trecho,
            re.IGNORECASE,
        )
        if not m:
            return ("incompleta", None)
        num = m.group(1)
        trib = (m.group(2) or "").upper()
        hits = []
        rx = re.compile(r"s[uú]mula\s*" + re.escape(num) + r"\b", re.IGNORECASE)
        for jid, nat, tipo, texto, ttrib in self.normativos:
            if nat != "sumula":
                continue
            if not rx.search(texto):
                continue
            if trib and ttrib and trib != ttrib.upper():
                continue
            hits.append(jid)
        uniq = set(hits)
        if len(uniq) == 1:
            return ("real", str(next(iter(uniq))))
        if len(uniq) == 0:
            return ("inventada", None)
        return ("incompleta", None)

    def resolver_lei(self, trecho: str):
        m = re.search(r"art(?:igo|\.)?\s*(\d+(?:\.\d{3})*)", trecho, re.IGNORECASE)
        if not m:
            return ("incompleta", None)
        artnum = m.group(1).replace(".", "")
        hint = _hint_lei(trecho)
        hits = []
        for jid, nat, tipo, texto, ttrib in self.normativos:
            if nat != "dispositivo":
                continue
            mt = re.match(
                r"\s*art(?:igo|\.)?\s*(\d+(?:\.\d{3})*)", texto, re.IGNORECASE
            )
            if not mt or mt.group(1).replace(".", "") != artnum:
                continue
            dh = _hint_disp(texto)
            if hint and dh and hint != dh:
                continue
            hits.append(jid)
        uniq = set(hits)
        if len(uniq) == 1:
            return ("real", str(next(iter(uniq))))
        if len(uniq) == 0:
            return ("inventada", None)
        return ("incompleta", None)
