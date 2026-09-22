import os
import re

_MODEL = None


def carregar_modelo(model_path="models/gliner_jusbrasil"):
    global _MODEL
    if _MODEL is None:
        try:
            import torch
            from gliner import GLiNER
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if os.path.exists(model_path):
                _MODEL = GLiNER.from_pretrained(model_path).to(device)
            else:
                _MODEL = GLiNER.from_pretrained("urchade/gliner_multi-v2.1").to(device)
        except Exception:
            _MODEL = None
    return _MODEL


def _ajustar_fronteiras(texto: str, ini: int, fim: int):
    while ini < fim and texto[ini] in " \t\r\n\"'“”‘’«»()[]{},;:.":
        ini += 1
    while fim > ini and texto[fim - 1] in " \t\r\n\"'“”‘’«»()[]{},;:.":
        fim -= 1
    return ini, fim


def extrair(texto: str):
    model = carregar_modelo()
    if model is None:
        from baseline_fuzzy.extrair import extrair as extrair_fuzzy
        return extrair_fuzzy(texto)

    labels = ["lei", "jurisprudencia"]
    candidatos = []

    parts = []
    last = 0
    for m in re.finditer(r"\n\s*\n", texto):
        parts.append((last, m.start()))
        last = m.end()
    parts.append((last, len(texto)))

    for p_start, p_end in parts:
        chunk = texto[p_start:p_end]
        if len(chunk.strip()) < 5:
            continue
        try:
            ents = model.predict_entities(chunk, labels, threshold=0.5)
            for e in ents:
                raw_ini = p_start + e["start"]
                raw_fim = p_start + e["end"]
                ini, fim = _ajustar_fronteiras(texto, raw_ini, raw_fim)
                if ini >= fim:
                    continue
                trecho = texto[ini:fim]
                if len(trecho) < 3:
                    continue
                tipo = e["label"]
                candidatos.append({
                    "inicio": ini,
                    "fim": fim,
                    "trecho": trecho,
                    "tipo": tipo,
                    "score": e.get("score", 0.0),
                })
        except Exception:
            continue

    if not candidatos:
        from baseline_fuzzy.extrair import extrair as extrair_fuzzy
        return extrair_fuzzy(texto)

    candidatos.sort(key=lambda c: (c["inicio"], -(c["fim"] - c["inicio"])))
    escolhidos = []
    ultimo_fim = -1
    for c in candidatos:
        if c["inicio"] >= ultimo_fim:
            escolhidos.append(c)
            ultimo_fim = c["fim"]

    return escolhidos
