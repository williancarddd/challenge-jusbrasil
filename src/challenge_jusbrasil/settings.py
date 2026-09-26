from __future__ import annotations

from pathlib import Path
from typing import Any

from challenge_jusbrasil.utils.kaggle_metric import CLASSES, IOU_MIN

ROOT = Path(__file__).resolve().parents[2]
TXT_DIR = ROOT / "data" / "txt"
GOLDENSET_PATH = ROOT / "data" / "goldenset.csv"
RESULTS_DIR = ROOT / "results"

INFER_BATCH_SIZE = 1000

VLLM_ENGINE: dict[str, Any] = {
    "trust_remote_code": True,
    "gpu_memory_utilization": 0.90,
    "seed": 42,
    "disable_log_stats": False,
}

VLLM_SAMPLING: dict[str, Any] = {
    "temperature": 0.0,
    "max_tokens": 4048,
    "seed": 42,
}

TEACHERS: list[dict[str, Any]] = [
    {
        "name": "unsloth/gemma-4-31B-it-unsloth-bnb-4bit",
        "family": "Gemma",
        "parameters": "31B",
        "quantization": "bnb-4bit",
        "url": "https://huggingface.co/unsloth/gemma-4-31B-it-unsloth-bnb-4bit",
        "role": "teacher",
        "vllm": {
            "max_model_len": 32768,
        },
    },
]

STUDENTS: list[dict[str, Any]] = [
    {
        "name": "unsloth/Llama-3.2-1B-Instruct-unsloth-bnb-4bit",
        "family": "Llama",
        "parameters": "1B",
        "quantization": "bnb-4bit",
        "url": "https://huggingface.co/unsloth/Llama-3.2-1B-Instruct-unsloth-bnb-4bit",
        "role": "student",
    },
    {
        "name": "unsloth/SmolLM2-135M-Instruct-bnb-4bit",
        "family": "SmolLM2",
        "parameters": "135M",
        "quantization": "bnb-4bit",
        "url": "https://huggingface.co/unsloth/SmolLM2-135M-Instruct-bnb-4bit",
        "role": "student",
        "vllm": {
            "max_model_len": 8192,
        },
    },
]

MODELS: list[dict[str, Any]] = [
    {**teacher, "role": "teacher"} for teacher in TEACHERS
] + [
    {**student, "role": "student"} for student in STUDENTS
]

for _model in MODELS:
    extra = dict(_model.get("vllm") or {})
    _model["vllm"] = {**VLLM_ENGINE, **extra}

TEACHER: dict[str, Any] = dict(next(m for m in MODELS if m["role"] == "teacher"))

SYSTEM_PROMPT = f"""Você extrai e classifica citações jurídicas em um documento judicial.

Localize cada citação de lei ou de jurisprudência no corpo do texto. Ignore distratores que parecem citação e não são: número dos autos do próprio documento, OAB, protocolo, folhas (fls.) e valor da causa.

Classifique cada citação com exatamente uma destas classes: {", ".join(CLASSES)}.
- real: a lei ou o processo existe e o id numérico do Jusbrasil (coluna id, somente dígitos) é conhecido. Nunca invente esse id.
- inventada: o identificador é concreto o bastante para uma busca, mas não existe lei ou processo correspondente.
- incompleta: não dá para formular uma busca única, ou a citação casa com mais de um feito.

Campos obrigatórios de cada item:
- trecho: cópia exata e contígua do documento, preservando quebras de linha.
- tipo: lei ou jurisprudencia.
- classificacao: {" | ".join(CLASSES)}.
- id_canonico: string só com dígitos quando classificacao for real; null nas demais.
- confianca: número em [0, 1].

A avaliação alinha predição e gabarito por sobreposição de spans com IoU >= {IOU_MIN}. Envie uma citação por span. Spans de citações diferentes não podem se sobrepor. O trecho precisa ocorrer literalmente no documento, porque inicio e fim são offsets de codepoints com texto[inicio:fim] == trecho.

Responda somente com JSON, sem markdown e sem texto fora do JSON:
{{"citacoes":[{{"trecho":"...","tipo":"jurisprudencia","classificacao":"incompleta","id_canonico":null,"confianca":0.5}}]}}
Se não houver citação, responda {{"citacoes":[]}}.
"""


def student_models() -> list[dict[str, Any]]:
    return [m for m in MODELS if m["role"] == "student"]


def teacher_models() -> list[dict[str, Any]]:
    return [m for m in MODELS if m["role"] == "teacher"]


def teacher_model() -> dict[str, Any]:
    return dict(TEACHER)


def engine_kwargs(model: dict[str, Any]) -> dict[str, Any]:
    kwargs = dict(model["vllm"])
   
    kwargs.setdefault("max_model_len", 16384)
    return kwargs


def infer_sampling(model: dict[str, Any]) -> dict[str, Any]:
    params = dict(VLLM_SAMPLING)
    max_len = int(engine_kwargs(model)["max_model_len"])
    params["max_tokens"] = min(int(params["max_tokens"]), max(64, max_len // 2))
    return params


def user_prompt(documento_id: str, texto: str) -> str:
    return f"documento_id: {documento_id}\n\n{texto}"


def chat_prompt(documento_id: str, texto: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(documento_id, texto)},
    ]
