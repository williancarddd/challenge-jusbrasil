from __future__ import annotations

import csv
import gc
import json
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


def extrair_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    if not text:
        return {"citacoes": []}
    data = json.loads(text)
    if isinstance(data, list):
        return {"citacoes": data}
    if not isinstance(data, dict):
        return {"citacoes": []}
    return data


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


def _confianca(valor: Any) -> float | None:
    if valor is None or valor == "" or valor == "-":
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= numero <= 1.0:
        return None
    return numero


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
    try:
        data = extrair_json(raw)
    except json.JSONDecodeError:
        return []
    itens = data.get("citacoes") or []
    if not isinstance(itens, list):
        return []
    candidatos: list[dict[str, Any]] = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        classe = str(item.get("classificacao") or "").strip().lower()
        if classe not in CLASSES:
            continue
        tipo = str(item.get("tipo") or "").strip().lower()
        if tipo not in TIPOS:
            tipo = "jurisprudencia"
        trecho = item.get("trecho")
        span = localizar_trecho(texto, str(trecho)) if trecho is not None else None
        if span is None:
            inicio = item.get("inicio")
            fim = item.get("fim")
            try:
                inicio_i, fim_i = int(inicio), int(fim)
            except (TypeError, ValueError):
                continue
            if 0 <= inicio_i < fim_i <= len(texto):
                span = (inicio_i, fim_i)
        if span is None:
            continue
        inicio, fim = span
        id_canonico = _id_canonico(item.get("id_canonico"))
        if classe == "real" and id_canonico is None:
            classe = "incompleta"
        resolucao = {"id_canonico": id_canonico} if classe == "real" else None
        candidatos.append(
            {
                "inicio": inicio,
                "fim": fim,
                "trecho": texto[inicio:fim],
                "tipo": tipo,
                "classificacao": classe,
                "confianca": _confianca(item.get("confianca")),
                "resolucao": resolucao,
            }
        )
    candidatos.sort(key=lambda cit: (-(cit["confianca"] or 0.0), cit["inicio"], cit["fim"]))
    saida: list[dict[str, Any]] = []
    for cit in candidatos:
        if any(_iou(cit, outro) >= IOU_MIN for outro in saida):
            continue
        saida.append(cit)
    saida.sort(key=lambda cit: (cit["inicio"], cit["fim"]))
    return saida


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
