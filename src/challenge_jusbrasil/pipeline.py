from __future__ import annotations

import csv
import gc
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from challenge_jusbrasil.settings import (
    GOLDENSET_PATH,
    INFER_BATCH_SIZE,
    MODELS,
    RESULTS_DIR,
    TXT_DIR,
    chat_prompt,
    engine_kwargs,
    infer_sampling,
)
from challenge_jusbrasil.utils.json_to_submission import encode
from challenge_jusbrasil.utils.kaggle_metric import (
    CLASSES,
    IOU_MIN,
    _iou,
    avaliar,
)

TIPOS = ("lei", "jurisprudencia")
_CONTEXTO = 250
_KB_CACHE: Any = None


def model_slug(name: str) -> str:
    return name.replace("/", "_")


def carregar_documentos(txt_dir: Path = TXT_DIR) -> list[tuple[str, str]]:
    docs = []
    for path in sorted(txt_dir.glob("*.txt")):
        docs.append((path.stem, path.read_text(encoding="utf-8")))
    return docs


def solution_frame(goldenset_path: Path = GOLDENSET_PATH) -> pd.DataFrame:
    por_doc: dict[str, list[str]] = defaultdict(list)
    nivel_por_doc: dict[str, int] = {}
    with goldenset_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            doc = row["documento_id"]
            nivel_por_doc[doc] = int(row["nivel"])
            classe = row["classificacao"].strip().lower()
            ids = [
                parte
                for parte in re.split(r"[\s:]+", row.get("id_canonico") or "")
                if parte and parte != "-"
            ]
            campo_ids = ":".join(ids) if classe == "real" and ids else "-"
            por_doc[doc].append(f"{row['inicio']},{row['fim']},{classe},{campo_ids}")
    linhas = [
        {
            "documento_id": doc,
            "nivel": nivel_por_doc[doc],
            "citacoes": "|".join(blocos) if blocos else "-",
        }
        for doc, blocos in por_doc.items()
    ]
    return pd.DataFrame(linhas)


_SPAN_TAG_RE = re.compile(r"<start\b([^>]*)>(.*?)<end>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r"""([A-Za-z_]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def _atributos_tag(bruto: str) -> dict[str, str]:
    atributos: dict[str, str] = {}
    for match in _ATTR_RE.finditer(bruto):
        valor = match.group(2) if match.group(2) is not None else match.group(3)
        atributos[match.group(1).lower()] = valor
    return atributos


def localizar_trecho(texto: str, trecho: str) -> tuple[int, int] | None:
    trecho = trecho.strip("\n")
    if not trecho:
        return None
    pos = texto.find(trecho)
    if pos >= 0:
        return pos, pos + len(trecho)
    normalizado: list[str] = []
    mapa: list[int] = []
    for indice, char in enumerate(texto):
        if char.isspace():
            if normalizado and normalizado[-1] != " ":
                normalizado.append(" ")
                mapa.append(indice)
            continue
        normalizado.append(char)
        mapa.append(indice)
    agulha = " ".join(trecho.split())
    if not agulha or not mapa:
        return None
    plano = "".join(normalizado)
    pos = plano.find(agulha)
    if pos < 0:
        return None
    inicio = mapa[pos]
    fim = mapa[pos + len(agulha) - 1] + 1
    return inicio, fim


def _id_canonico(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto in ("", "-", "null", "None"):
        return None
    if not texto.isdigit():
        return None
    return texto


def citacoes_de_saida(texto: str, raw: str) -> list[dict[str, Any]]:
    candidatos: list[dict[str, Any]] = []
    cursor = 0
    for match in _SPAN_TAG_RE.finditer(raw or ""):
        atributos = _atributos_tag(match.group(1))
        classe = atributos.get("classificacao", "").strip().lower()
        if classe not in CLASSES:
            continue
        tipo = atributos.get("tipo", "").strip().lower()
        if tipo not in TIPOS:
            tipo = "jurisprudencia"
        trecho = match.group(2).strip("\n")
        if not trecho:
            continue
        span = localizar_trecho(texto[cursor:], trecho)
        if span is None:
            span = localizar_trecho(texto, trecho)
            if span is None:
                continue
            inicio, fim = span
        else:
            inicio, fim = cursor + span[0], cursor + span[1]
        cursor = fim
        candidatos.append(
            {
                "inicio": inicio,
                "fim": fim,
                "trecho": texto[inicio:fim],
                "tipo": tipo,
                "classificacao": classe,
                "confianca": None,
                "resolucao": None,
            }
        )
    candidatos.sort(key=lambda cit: (cit["inicio"], cit["fim"]))
    saida: list[dict[str, Any]] = []
    for cit in candidatos:
        if any(_iou(cit, outro) >= IOU_MIN for outro in saida):
            continue
        saida.append(cit)
    saida.sort(key=lambda cit: (cit["inicio"], cit["fim"]))
    return resolver_ids(texto, saida)


def carregar_kb() -> Any:
    global _KB_CACHE
    if _KB_CACHE is not None:
        return _KB_CACHE if _KB_CACHE is not False else None
    from challenge_jusbrasil.settings import ROOT

    db_path = ROOT / "data" / "desafio1_bracis.db"
    davi = ROOT / "davi_version"
    if not db_path.exists():
        _KB_CACHE = False
        return None
    import sqlite3
    import sys

    sys.path.insert(0, str(davi))
    sys.path.insert(0, str(davi / "kb"))
    from build_kb import build_dispositivos, build_header_index, build_sumulas
    from resolve import KB

    con = sqlite3.connect(str(db_path))
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    kb = KB.__new__(KB)
    kb.header_index = build_header_index(con)
    kb.sumulas = build_sumulas(con)
    kb.dispositivos = build_dispositivos(con)
    kb.con = con
    _KB_CACHE = kb
    return kb


def _resolver_uma(kb: Any, texto: str, cit: dict[str, Any]) -> tuple[str, str | None]:
    from extract import _LEI_ART_RE, _SUMULA_RE
    from resolve import resolve_jurisprudencia_numero, resolve_lei_artigo, resolve_sumula

    trecho = cit["trecho"]
    if cit["tipo"] == "lei":
        match = _LEI_ART_RE.search(trecho)
        if match is None:
            return "incompleta", None
        classe, id_ = resolve_lei_artigo(kb, match.group("num"), match.group("codigo"))
        return classe, _id_canonico(id_)
    match = _SUMULA_RE.search(trecho)
    if match:
        tribunal = match.group("trib")
        classe, id_ = resolve_sumula(
            kb,
            match.group("num"),
            tribunal.upper() if tribunal else None,
            bool(match.group("vinc")),
        )
        return classe, _id_canonico(id_)
    ctx = texto[max(0, cit["inicio"] - _CONTEXTO) : cit["fim"] + _CONTEXTO]
    classe, id_, _via = resolve_jurisprudencia_numero(kb, trecho, ctx)
    return classe, _id_canonico(id_)


def resolver_ids(texto: str, citacoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kb = carregar_kb()
    for cit in citacoes:
        if kb is None:
            classe_kb, id_kb = "incompleta", None
        else:
            classe_kb, id_kb = _resolver_uma(kb, texto, cit)
        if cit["classificacao"] == "real" and id_kb is not None:
            cit["resolucao"] = {"id_canonico": id_kb}
        elif cit["classificacao"] == "real":
            cit["classificacao"] = classe_kb if classe_kb in CLASSES else "incompleta"
            cit["resolucao"] = None
        else:
            cit["resolucao"] = None
    return citacoes


def submission_frame(
    documentos: list[tuple[str, str]],
    saidas: list[str],
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    linhas = []
    contratos: dict[str, dict[str, Any]] = {}
    for (doc_id, texto), raw in zip(documentos, saidas, strict=True):
        citacoes = citacoes_de_saida(texto, raw)
        contrato = {"documento_id": doc_id, "citacoes": citacoes}
        contratos[doc_id] = contrato
        linhas.append({"documento_id": doc_id, "citacoes": encode(contrato)})
    return pd.DataFrame(linhas), contratos


def avaliar_saidas(
    documentos: list[tuple[str, str]],
    saidas: list[str],
    goldenset_path: Path = GOLDENSET_PATH,
) -> dict[str, Any]:
    submission, contratos = submission_frame(documentos, saidas)
    presentes = set(submission["documento_id"])
    solution = solution_frame(goldenset_path)
    faltantes = [
        {"documento_id": doc_id, "citacoes": "-"}
        for doc_id in solution["documento_id"]
        if doc_id not in presentes
    ]
    if faltantes:
        submission = pd.concat([submission, pd.DataFrame(faltantes)], ignore_index=True)
    return {"avaliacao": avaliar(solution, submission), "contratos": contratos, "submission": submission}


def descarregar_llm(llm: Any) -> None:
    import torch

    engine = getattr(llm, "llm_engine", None)
    core = getattr(engine, "engine_core", None)
    for obj in (core, engine, llm):
        if obj is None:
            continue
        for name in ("shutdown", "close", "terminate"):
            fn = getattr(obj, name, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
                break
    del llm
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
        torch.cuda.synchronize()
    time.sleep(8)


def gerar_textos(llm: Any, sampling: Any, documentos: list[tuple[str, str]], batch_size: int) -> list[str]:
    textos: list[str] = []
    for inicio in range(0, len(documentos), batch_size):
        lote = documentos[inicio : inicio + batch_size]
        mensagens = [chat_prompt(doc_id, texto) for doc_id, texto in lote]
        saidas = llm.chat(mensagens, sampling_params=sampling, use_tqdm=False)
        textos.extend(item.outputs[0].text for item in saidas)
    return textos


def executar(
    modelos: list[dict[str, Any]] | None = None,
    txt_dir: Path = TXT_DIR,
    goldenset_path: Path = GOLDENSET_PATH,
    results_dir: Path = RESULTS_DIR,
    batch_size: int = INFER_BATCH_SIZE,
) -> dict[str, Any]:
    os.environ.setdefault("VLLM_USE_FLASHINFER_SAMPLER", "0")
    from vllm import LLM, SamplingParams

    documentos = carregar_documentos(txt_dir)
    if not documentos:
        raise SystemExit(f"nenhum documento em {txt_dir}")
    catalogo = modelos if modelos is not None else MODELS
    resultados: dict[str, Any] = {}
    for model in catalogo:
        print(f"load {model['name']}")
        llm = LLM(model=model["name"], **engine_kwargs(model))
        sampling = SamplingParams(**infer_sampling(model))
        try:
            saidas = gerar_textos(llm, sampling, documentos, batch_size)
        finally:
            descarregar_llm(llm)
        avaliado = avaliar_saidas(documentos, saidas, goldenset_path)
        pasta = results_dir / model_slug(model["name"])
        pasta.mkdir(parents=True, exist_ok=True)
        for doc_id, contrato in avaliado["contratos"].items():
            destino = pasta / f"{doc_id}.json"
            destino.write_text(
                json.dumps(contrato, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        resultados[model["name"]] = {
            "role": model["role"],
            "family": model["family"],
            "parameters": model["parameters"],
            "avaliacao": avaliado["avaliacao"],
        }
        score = avaliado["avaliacao"]["score_final"]
        print(f"{model['name']} score_final={score:.4f}")
    return resultados
