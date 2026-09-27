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

from challenge_jusbrasil.busca import Busca, criar_busca
from challenge_jusbrasil.resolver.lei import tipo_de
from challenge_jusbrasil.chunker import Chunker, Janela
from challenge_jusbrasil.settings import (
    CHUNK_OVERLAP,
    GOLDENSET_PATH,
    INFER_BATCH_SIZE,
    MODELS,
    RESULTS_DIR,
    TXT_DIR,
    chat_prompt,
    engine_kwargs,
    infer_sampling,
    orcamento_texto,
)
from challenge_jusbrasil.utils.json_to_submission import encode
from challenge_jusbrasil.utils.kaggle_metric import (
    IOU_MIN,
    _iou,
    avaliar,
)



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


_SPAN_TAG_RE = re.compile(r"<start\b[^>]*>(.*?)<end>", re.IGNORECASE | re.DOTALL)


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
        trecho = match.group(1).strip("\n")
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
                "tipo": tipo_de(texto[inicio:fim]),
                "classificacao": "incompleta",
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
    return saida


def fundir_citacoes(citacoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordenadas = sorted(
        citacoes,
        key=lambda cit: (cit.get("_borda", False), cit["inicio"], cit["fim"]),
    )
    saida: list[dict[str, Any]] = []
    for cit in ordenadas:
        if any(_iou(cit, outro) >= IOU_MIN for outro in saida):
            continue
        saida.append({chave: valor for chave, valor in cit.items() if chave != "_borda"})
    saida.sort(key=lambda cit: (cit["inicio"], cit["fim"]))
    return saida


def citacoes_da_janela(
    texto: str,
    janela: Janela,
    raw: str,
    sobreposicao: int,
) -> list[dict[str, Any]]:
    fim_janela = janela.start + len(janela.text)
    documento_fim = len(texto)
    citacoes = []
    for cit in citacoes_de_saida(janela.text, raw):
        cit["inicio"] += janela.start
        cit["fim"] += janela.start
        cit["trecho"] = texto[cit["inicio"] : cit["fim"]]
        toca_inicio = janela.start > 0 and cit["inicio"] < janela.start + sobreposicao
        toca_fim = fim_janela < documento_fim and cit["fim"] > fim_janela - sobreposicao
        cit["_borda"] = toca_inicio or toca_fim
        citacoes.append(cit)
    return citacoes


def resolver_ids(
    texto: str,
    citacoes: list[dict[str, Any]],
    busca: Busca | None = None,
) -> list[dict[str, Any]]:
    return (busca or criar_busca()).aplicar(texto, citacoes)


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


def _lora_request() -> Any:
    caminho = os.environ.get("LORA_PATH", "").strip()
    if not caminho:
        return None
    from vllm.lora.request import LoRARequest

    return LoRARequest("distil", 1, caminho)


def chat_lotes(llm: Any, sampling: Any, mensagens: list[list[dict[str, str]]], batch_size: int) -> list[str]:
    if batch_size < 1:
        raise ValueError("batch_size deve ser positivo")
    brutos: list[str] = []
    total = (len(mensagens) + batch_size - 1) // batch_size if mensagens else 0
    pedido = _lora_request()
    for numero, inicio in enumerate(range(0, len(mensagens), batch_size), start=1):
        lote = mensagens[inicio : inicio + batch_size]
        print(f"chat lote {numero}/{total} n={len(lote)}", flush=True)
        kwargs: dict[str, Any] = {"sampling_params": sampling, "use_tqdm": False}
        if pedido is not None:
            kwargs["lora_request"] = pedido
        saidas = llm.chat(lote, **kwargs)
        brutos.extend(item.outputs[0].text for item in saidas)
    return brutos


def gerar_citacoes(
    llm: Any,
    sampling: Any,
    documentos: list[tuple[str, str]],
    chunker: Chunker,
    batch_size: int,
) -> list[list[dict[str, Any]]]:
    plano: list[tuple[int, Janela]] = []
    for indice, (_, texto) in enumerate(documentos):
        plano.extend((indice, janela) for janela in chunker.janelas(texto))
    print(f"chunks {len(plano)} lote={batch_size}", flush=True)
    mensagens = [chat_prompt(documentos[indice][0], janela.text) for indice, janela in plano]
    brutos = chat_lotes(llm, sampling, mensagens, batch_size)
    por_doc: list[list[dict[str, Any]]] = [[] for _ in documentos]
    for (indice, janela), raw in zip(plano, brutos, strict=True):
        texto = documentos[indice][1]
        por_doc[indice].extend(citacoes_da_janela(texto, janela, raw, chunker.sobreposicao))
    return [fundir_citacoes(citacoes) for citacoes in por_doc]


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


EXTRACT_DIR = RESULTS_DIR / "extract"
SEARCH_DIR = RESULTS_DIR / "search"
_IGNORAR_JSON = {"meta.json", "resumo.json"}


def _carimbo() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _pasta_run(raiz: Path, carimbo: str, slug: str) -> Path:
    pasta = raiz / f"{carimbo}_{slug}"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _escrever_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _avaliar_contratos(
    contratos: dict[str, dict[str, Any]],
    goldenset_path: Path,
) -> dict[str, Any]:
    linhas = [
        {"documento_id": doc_id, "citacoes": encode(contrato)}
        for doc_id, contrato in contratos.items()
    ]
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
    return avaliar(solution, submission)


def extrair(
    modelos: list[dict[str, Any]] | None = None,
    txt_dir: Path = TXT_DIR,
    results_dir: Path = EXTRACT_DIR,
    batch_size: int = INFER_BATCH_SIZE,
    documentos: list[tuple[str, str]] | None = None,
) -> list[Path]:
    os.environ.setdefault("VLLM_USE_FLASHINFER_SAMPLER", "0")
    from vllm import LLM, SamplingParams

    documentos = documentos if documentos is not None else carregar_documentos(txt_dir)
    if not documentos:
        raise SystemExit(f"nenhum documento em {txt_dir}")
    catalogo = modelos if modelos is not None else MODELS
    carimbo = _carimbo()
    pastas: list[Path] = []
    for model in catalogo:
        slug = model_slug(model["name"])
        print(f"load {model['name']}")
        llm = LLM(model=model["name"], **engine_kwargs(model))
        sampling = SamplingParams(**infer_sampling(model))
        chunker = Chunker(orcamento_texto(model), CHUNK_OVERLAP)
        try:
            citacoes_por_doc = gerar_citacoes(llm, sampling, documentos, chunker, batch_size)
        finally:
            descarregar_llm(llm)
        pasta = _pasta_run(results_dir, carimbo, slug)
        for (doc_id, _), citacoes in zip(documentos, citacoes_por_doc, strict=True):
            contrato = {
                "documento_id": doc_id,
                "citacoes": citacoes,
            }
            _escrever_json(pasta / f"{doc_id}.json", contrato)
        _escrever_json(
            pasta / "meta.json",
            {
                "name": model["name"],
                "role": model["role"],
                "family": model["family"],
                "parameters": model["parameters"],
                "slug": slug,
                "batch_size": batch_size,
            },
        )
        print(f"extração salva em {pasta}")
        pastas.append(pasta)
    return pastas


def extracoes_recentes(extract_dir: Path = EXTRACT_DIR) -> list[Path]:
    if not extract_dir.is_dir():
        raise SystemExit(f"nenhuma extração em {extract_dir}")
    pastas = [pasta for pasta in extract_dir.iterdir() if pasta.is_dir()]
    if not pastas:
        raise SystemExit(f"nenhuma extração em {extract_dir}")
    ultimo = max(pasta.name.split("_", 1)[0] for pasta in pastas)
    return sorted(pasta for pasta in pastas if pasta.name.startswith(f"{ultimo}_"))


def buscar(
    pastas: list[Path] | None = None,
    txt_dir: Path = TXT_DIR,
    goldenset_path: Path = GOLDENSET_PATH,
    results_dir: Path = SEARCH_DIR,
    modo: str | None = None,
) -> dict[str, Any]:
    origens = pastas if pastas is not None else extracoes_recentes()
    if not origens:
        raise SystemExit("nenhuma extração para buscar")
    estrategia = criar_busca(modo)
    textos = dict(carregar_documentos(txt_dir))
    carimbo = _carimbo()
    resultados: dict[str, Any] = {}
    for origem in origens:
        meta_path = origem / "meta.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            por_slug = {model_slug(model["name"]): model for model in MODELS}
            model = por_slug.get(origem.name)
            meta = (
                {
                    "name": model["name"],
                    "role": model["role"],
                    "family": model["family"],
                    "parameters": model["parameters"],
                    "slug": origem.name,
                }
                if model is not None
                else {"name": origem.name, "slug": origem.name}
            )
        slug = str(meta.get("slug") or model_slug(str(meta.get("name") or origem.name)))
        contratos: dict[str, dict[str, Any]] = {}
        for path in sorted(origem.glob("*.json")):
            if path.name in _IGNORAR_JSON:
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc_id = str(doc.get("documento_id") or path.stem)
            citacoes = resolver_ids(
                textos.get(doc_id, ""),
                list(doc.get("citacoes") or []),
                estrategia,
            )
            contratos[doc_id] = {"documento_id": doc_id, "citacoes": citacoes}
        avaliacao = _avaliar_contratos(contratos, goldenset_path)
        pasta = _pasta_run(results_dir, carimbo, slug)
        for doc_id, contrato in contratos.items():
            _escrever_json(pasta / f"{doc_id}.json", contrato)
        item = {
            "name": meta.get("name"),
            "role": meta.get("role"),
            "family": meta.get("family"),
            "parameters": meta.get("parameters"),
            "slug": slug,
            "busca": estrategia.nome,
            "extract": str(origem),
            "avaliacao": avaliacao,
        }
        _escrever_json(pasta / "resumo.json", item)
        nome = str(meta.get("name") or slug)
        resultados[nome] = item
        print(f"{nome} score_final={avaliacao['score_final']:.4f}")
        print(f"busca salva em {pasta}")
    return resultados


def imprimir_avaliacao(resultados: dict[str, Any]) -> None:
    print()
    for nome, item in resultados.items():
        avaliacao = item["avaliacao"]
        papel = item.get("role") or ""
        print(f"{papel} {nome}".strip())
        for nivel, detalhe in sorted(avaliacao["niveis"].items(), key=lambda par: int(par[0])):
            f1 = {classe: round(valor, 3) for classe, valor in detalhe["f1_por_classe"].items()}
            print(
                f"  nivel {nivel}: score={detalhe['score']:.4f} "
                f"macro_f1={detalhe['macro_f1']:.4f} tau={detalhe['tau']:.3f} "
                f"bonus={detalhe['b']:.4f} f1={f1}"
            )
        print(f"  SCORE FINAL: {avaliacao['score_final']:.4f}")
