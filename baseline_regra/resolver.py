# -*- coding: utf-8 -*-
"""Passo 3: consultar a base congelada, agrupar por feito, decidir a classe.

Regra do desafio:
  1 feito distinto  -> real       (id_canonico = coluna `id`)
  0                 -> inventada
  2+ feitos         -> incompleta
Citações vagas (sem identificador buscável) -> incompleta sem tocar o banco.
"""
import re
import sqlite3
import unicodedata
from normalizar import so_digitos, reagrupa_milhar, is_cnj, cnj_formatado, normaliza_uf

def _norm_txt(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

class Resolvedor:
    def __init__(self, db_path: str):
        self.cx = sqlite3.connect(db_path)
        # carrega os 18 normativos em memória (sumula + dispositivo)
        self.normativos = list(self.cx.execute(
            "SELECT id, natureza, tipo, texto FROM documentos "
            "WHERE natureza IN ('sumula','dispositivo')"))

    # ---- jurisprudência com número ------------------------------------
    def _candidatos_fts(self, frase: str):
        q = ("SELECT d.id, d.tribunal, instr(d.texto, ?) AS pos "
             "FROM documentos_fts JOIN documentos d ON d.rowid=documentos_fts.rowid "
             "WHERE documentos_fts MATCH ? AND d.natureza='acordao'")
        try:
            rows = list(self.cx.execute(q, (frase, '"%s"' % frase)))
        except sqlite3.OperationalError:
            return []
        # separa "é o processo" (nº no cabeçalho) de "só cita" (nº no corpo)
        # pos<=120 => cabeçalho: é o feito. senão, apenas menção.
        return [(r[0], r[1]) for r in rows if r[2] and r[2] <= 120]

    def resolver_juris(self, trecho: str):
        limpo = trecho.replace("\n", " ")
        digits = so_digitos(limpo)
        if not digits:
            return ("incompleta", None)
        frase = cnj_formatado(digits) if is_cnj(digits) else reagrupa_milhar(digits)
        cand = self._candidatos_fts(frase)
        # agrupa por feito = (id do jusbrasil). Aqui cada acórdão-feito tem 1 id.
        feitos = {}
        for jid, trib in cand:
            feitos.setdefault(jid, jid)
        n = len(feitos)
        if n == 1:
            return ("real", str(next(iter(feitos))))
        if n == 0:
            return ("inventada", None)
        return ("incompleta", None)

    # ---- súmula --------------------------------------------------------
    def resolver_sumula(self, trecho: str):
        # LIMITAÇÃO DO BASELINE: os 5 registros de súmula não expõem o número
        # da súmula no texto, e não há tabela número->id. Sem resolução
        # implementada, toda súmula cai em incompleta. (Alvo de melhoria.)
        return ("incompleta", None)

    # ---- dispositivo de lei -------------------------------------------
    def resolver_lei(self, trecho: str):
        alvo = _norm_txt(trecho)
        # extrai "art N"
        m = re.search(r"art(?:igo|\.)?\s*(\d+)", trecho, re.IGNORECASE)
        if not m:
            return ("incompleta", None)
        artnum = m.group(1)
        hits = []
        for jid, nat, tipo, texto in self.normativos:
            if nat != "dispositivo":
                continue
            mt = re.match(r"\s*art(?:igo|\.)?\s*(\d+)", texto, re.IGNORECASE)
            if mt and mt.group(1) == artnum:
                hits.append(jid)
        if len(set(hits)) == 1:
            return ("real", str(hits[0]))
        if len(set(hits)) == 0:
            return ("inventada", None)
        return ("incompleta", None)
