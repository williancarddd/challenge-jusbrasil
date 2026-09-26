from __future__ import annotations

import csv
import gc
import json
import os
import re
import time
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from challenge_jusbrasil.resolver import Resolver
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
_RESOLVER_CACHE: Resolver | None | bool = None


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


def carregar_resolver() -> Resolver | None:
    global _RESOLVER_CACHE
    if _RESOLVER_CACHE is not None:
        return _RESOLVER_CACHE if _RESOLVER_CACHE is not False else None
    from challenge_jusbrasil.settings import ROOT

    db_path = ROOT / "data" / "desafio1_bracis.db"
    if not db_path.exists():
        _RESOLVER_CACHE = False
        return None
    _RESOLVER_CACHE = Resolver.carregar(db_path)
    return _RESOLVER_CACHE


def resolver_ids(texto: str, citacoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolver = carregar_resolver()
    for cit in citacoes:
        if resolver is None:
            if cit["classificacao"] == "real":
                cit["classificacao"] = "incompleta"
            cit["resolucao"] = None
            continue
        contexto = texto[max(0, cit["inicio"] - _CONTEXTO) : cit["fim"] + _CONTEXTO]
        resultado = resolver.resolve(cit["trecho"], cit["tipo"], contexto)
        cit["classificacao"] = resultado.classificacao
        cit["resolucao"] = (
            {"id_canonico": resultado.id_canonico}
            if resultado.classificacao == "real" and resultado.id_canonico
            else None
        )
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


def _jsonable(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {str(chave): _jsonable(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_jsonable(item) for item in valor]
    if isinstance(valor, float):
        return float(valor)
    if hasattr(valor, "item"):
        return _jsonable(valor.item())
    return valor


def salvar_resultados(
    resultados: dict[str, Any],
    nome: str,
    results_dir: Path = RESULTS_DIR,
    contratos: dict[str, dict[str, Any]] | None = None,
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%dT%H%M%S")
    pasta = results_dir / "runs" / f"{carimbo}_{nome}"
    pasta.mkdir(parents=True, exist_ok=True)
    if contratos:
        for slug, docs in contratos.items():
            destino_modelo = pasta / slug
            destino_modelo.mkdir(parents=True, exist_ok=True)
            for doc_id, contrato in docs.items():
                (destino_modelo / f"{doc_id}.json").write_text(
                    json.dumps(_jsonable(contrato), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
    texto = json.dumps(_jsonable(resultados), ensure_ascii=False, indent=2)
    destino = pasta / "resumo.json"
    destino.write_text(texto, encoding="utf-8")
    (results_dir / "resumo.json").write_text(texto, encoding="utf-8")
    print(f"run salva em {destino}")
    return destino


def reavaliar_extraidos(
    results_dir: Path = RESULTS_DIR,
    txt_dir: Path = TXT_DIR,
    goldenset_path: Path = GOLDENSET_PATH,
) -> dict[str, Any]:
    textos = dict(carregar_documentos(txt_dir))
    por_slug = {model_slug(model["name"]): model for model in MODELS}
    resultados: dict[str, Any] = {}
    contratos_por_modelo: dict[str, dict[str, Any]] = {}
    for slug, model in por_slug.items():
        pasta = results_dir / slug
        if not pasta.is_dir():
            continue
        linhas = []
        contratos: dict[str, dict[str, Any]] = {}
        for path in sorted(pasta.glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc_id = str(doc.get("documento_id") or path.stem)
            citacoes = resolver_ids(textos.get(doc_id, ""), list(doc.get("citacoes") or []))
            contrato = {"documento_id": doc_id, "citacoes": citacoes}
            contratos[doc_id] = contrato
            linhas.append({"documento_id": doc_id, "citacoes": encode(contrato)})
        submission = pd.DataFrame(linhas)
        solution = solution_frame(goldenset_path)
        presentes = set(submission["documento_id"]) if not submission.empty else set()
        faltantes = [
            {"documento_id": doc_id, "citacoes": "-"}
            for doc_id in solution["documento_id"]
            if doc_id not in presentes
        ]
        if faltantes:
            submission = pd.concat([submission, pd.DataFrame(faltantes)], ignore_index=True)
        resultados[model["name"]] = {
            "role": model["role"],
            "family": model["family"],
            "parameters": model["parameters"],
            "avaliacao": avaliar(solution, submission),
        }
        contratos_por_modelo[slug] = contratos
        score = resultados[model["name"]]["avaliacao"]["score_final"]
        print(f"{model['name']} score_final={score:.4f}")
    if not resultados:
        raise SystemExit(f"nenhuma extração de modelo em {results_dir}")
    salvar_resultados(resultados, "modelos", results_dir, contratos_por_modelo)
    return resultados


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
    pasta_run = results_dir / "runs" / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}_inferencia"
    for model in catalogo:
        print(f"load {model['name']}")
        llm = LLM(model=model["name"], **engine_kwargs(model))
        sampling = SamplingParams(**infer_sampling(model))
        try:
            saidas = gerar_textos(llm, sampling, documentos, batch_size)
        finally:
            descarregar_llm(llm)
        avaliado = avaliar_saidas(documentos, saidas, goldenset_path)
        pasta = pasta_run / model_slug(model["name"])
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
    texto = json.dumps(_jsonable(resultados), ensure_ascii=False, indent=2)
    pasta_run.mkdir(parents=True, exist_ok=True)
    destino = pasta_run / "resumo.json"
    destino.write_text(texto, encoding="utf-8")
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "resumo.json").write_text(texto, encoding="utf-8")
    print(f"run salva em {destino}")
    return resultados
