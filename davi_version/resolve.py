# -*- coding: utf-8 -*-
"""Resolve uma citação extraída (tipo + identificadores) para uma classe
(real/inventada/incompleta) + id_canonico, consultando a KB offline
(kb/kb.json) com fallback de FTS ao vivo sobre o SQLite para os acórdãos que
não entraram no header_index."""
import json
import re
import sqlite3
from pathlib import Path

from normalize import (extract_number_token, fuzzy_fix_word, norm_codigo,
                        only_digits, regroup_digits, strip_accents)

HERE = Path(__file__).resolve().parent
KB_PATH = HERE / "kb" / "kb.json"


class KB:
    def __init__(self, kb_path=KB_PATH, db_path=None):
        data = json.loads(Path(kb_path).read_text(encoding="utf-8"))
        self.header_index = data["header_index"]
        self.sumulas = data["sumulas"]
        self.dispositivos = data["dispositivos"]
        self.con = None
        if db_path is not None and Path(db_path).exists():
            self.con = sqlite3.connect(str(db_path))
            self.con.text_factory = lambda b: b.decode("utf-8", "replace")

    def close(self):
        if self.con is not None:
            self.con.close()


# --------------------------------------------------------------- jurisprudência numerada

def _fts_fallback(kb: KB, digits: str):
    """Quando o número não está no header_index (acórdão sem número extraído
    na etapa offline), consulta o FTS ao vivo e aplica a heurística de
    posição: só conta como 'dono' do número o registro em que ele aparece
    perto do início do próprio texto (cabeçalho), não apenas citado no corpo."""
    if kb.con is None or len(digits) < 3:
        return []
    phrase = regroup_digits(digits)
    cur = kb.con.cursor()
    try:
        cur.execute(
            "SELECT d.documento_id, d.id, d.tribunal, d.ano, d.relator, d.texto, d.texto_len "
            "FROM documentos_fts JOIN documentos d ON d.rowid = documentos_fts.rowid "
            "WHERE documentos_fts MATCH ? AND d.natureza='acordao'",
            (f'"{phrase}"',),
        )
    except sqlite3.OperationalError:
        return []
    out = []
    for documento_id, doc_id, tribunal, ano, relator, texto, texto_len in cur.fetchall():
        pos = texto.find(phrase)
        if pos < 0:
            # tolera formatação um pouco diferente da reagrupada
            pos = 0 if only_digits(texto[:4000]).find(digits) >= 0 else -1
        limite = max(2500, int(0.03 * texto_len))
        if 0 <= pos <= limite:
            out.append({"id": doc_id, "documento_id": documento_id, "tribunal": tribunal,
                        "ano": ano, "relator": relator})
    return out


def _tiebreak_por_relator(candidatos, contexto: str):
    if not contexto:
        return None
    ctx_norm = strip_accents(contexto).lower()
    achados = []
    for c in candidatos:
        relator = c.get("relator") or ""
        sobrenome = strip_accents(relator).lower().split()
        sobrenome = [t for t in sobrenome if len(t) > 3]
        if sobrenome and any(tok in ctx_norm for tok in sobrenome):
            achados.append(c)
    if len(achados) == 1:
        return achados[0]
    return None


def resolve_jurisprudencia_numero(kb: KB, trecho: str, contexto: str = ""):
    """trecho: texto bruto da citação (pode ter prefixo de classe + UF).
    Retorna (classe, id_canonico|None, via) — via é só para debug/confiança."""
    tok = extract_number_token(trecho)
    if not tok:
        return "incompleta", None, "sem_numero"
    digits = only_digits(tok)
    if len(digits) < 3:
        return "incompleta", None, "numero_curto"

    cands = kb.header_index.get(digits, [])
    via = "header_index"
    if not cands:
        cands = _fts_fallback(kb, digits)
        via = "fts_fallback"

    if len(cands) == 0:
        return "inventada", None, via
    if len(cands) == 1:
        return "real", cands[0]["id"], via
    escolhido = _tiebreak_por_relator(cands, contexto)
    if escolhido is not None:
        return "real", escolhido["id"], via + "+relator"
    return "incompleta", None, via + "+ambiguo"


# --------------------------------------------------------------- súmula

def resolve_sumula(kb: KB, numero: str, tribunal: str = None, vinculante: bool = False):
    matches = [s for s in kb.sumulas if s["numero"] == numero and s["vinculante"] == vinculante]
    if tribunal:
        exatas = [s for s in matches if s["tribunal"] == tribunal]
        if exatas:
            matches = exatas
        else:
            return "inventada", None
    if len(matches) == 0:
        return "inventada", None
    if len(matches) == 1:
        return "real", matches[0]["id"]
    return "incompleta", None


# --------------------------------------------------------------- lei / dispositivo

def resolve_lei_artigo(kb: KB, numero: str, codigo_raw: str):
    codigo = norm_codigo(codigo_raw)
    if codigo is None:
        return "inventada", None
    numero_norm = only_digits(numero).lstrip("0") or "0"
    for d in kb.dispositivos:
        if d["numero"] == numero_norm and d["codigo"] == codigo:
            return "real", d["id"]
    return "inventada", None
