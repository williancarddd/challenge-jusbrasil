from __future__ import annotations

from pathlib import Path
from typing import Any

from challenge_jusbrasil.utils.kaggle_metric import CLASSES

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
    {
        "name": "unsloth/Phi-4-mini-instruct-unsloth-bnb-4bit",
        "family": "Phi",
        "parameters": "3.8B",
        "quantization": "bnb-4bit",
        "url": "https://huggingface.co/unsloth/Phi-4-mini-instruct-unsloth-bnb-4bit",
        "role": "student",
    }
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

SYSTEM_PROMPT = f"""You extract and classify legal citations in a Brazilian judicial document.

Return the same text, without changing any character, and mark each citation with <start> and <end>.
Do not return JSON. Do not return a confidence score. Do not write anything outside the marked text.

On the opening tag, set tipo and classificacao. Do not output an id.
<start tipo="lei|jurisprudencia" classificacao="{"|".join(CLASSES)}">exact span<end>

Classify each citation with exactly one of these classes: {", ".join(CLASSES)}.
- real: the statute or case exists and identifies a single document.
- inventada: the identifier is specific enough to search, but no matching statute or case exists.
- incompleta: a single search cannot be formed, or the citation matches more than one case.

Ignore distractors that look like citations but are not: the case number of the document itself, OAB, protocol, page sheets (fls.), and the amount in dispute. Leave them untagged.
Mark one citation per span. Spans must not overlap. The text between the tags is a literal copy of the document, including line breaks.
If there is no citation, return the text with no tags.

Examples of real:

Input:
A OAB/SP 123.456 não integra a fundamentação. O pedido se apoia no art. 373, I, do CPC.
Output:
A OAB/SP 123.456 não integra a fundamentação. O pedido se apoia no <start tipo="lei" classificacao="real">art. 373, I, do CPC<end>.

Input:
O acórdão citado é o AgInt no REsp 1.599.910/PR, distinto do protocolo 2024/000111.
Output:
O acórdão citado é o <start tipo="jurisprudencia" classificacao="real">AgInt no REsp 1.599.910/PR<end>, distinto do protocolo 2024/000111.

Input:
A Súmula Vinculante 10 orienta o caso. O valor da causa é R$ 10.000,00.
Output:
A <start tipo="jurisprudencia" classificacao="real">Súmula Vinculante 10<end> orienta o caso. O valor da causa é R$ 10.000,00.

Examples of inventada:


Input:
A peça menciona a Reclamação nº 66.516/RO. As folhas são fls. 12/30.
Output:
A peça menciona a <start tipo="jurisprudencia" classificacao="inventada">Reclamação nº 66.516/RO<end>. As folhas são fls. 12/30.

Input:
O autor invoca o art. 158 do Código de Defesa do Consumidor.
Output:
O autor invoca o <start tipo="lei" classificacao="inventada">art. 158 do Código de Defesa do Consumidor<end>.

Input:
O recurso aponta o RE 7.216.673/RS como paradigma.
Output:
O recurso aponta o <start tipo="jurisprudencia" classificacao="inventada">RE 7.216.673/RS<end> como paradigma.

Examples of incompleta:

Input:
Há jurisprudência pacífica desta Corte sobre o tema.
Output:
Há <start tipo="jurisprudencia" classificacao="incompleta">jurisprudência pacífica desta Corte<end> sobre o tema.

Input:
Aplicam-se as normas de regência da matéria ao pedido.
Output:
Aplicam-se as <start tipo="lei" classificacao="incompleta">normas de regência da matéria<end> ao pedido.

Input:
Cita-se julgado do STF proferido em 2024 pela relatoria de Dias Toffoli.
Output:
Cita-se <start tipo="jurisprudencia" classificacao="incompleta">julgado do STF proferido em 2024 pela relatoria de Dias Toffoli<end>.
"""


def student_models() -> list[dict[str, Any]]:
    return [m for m in MODELS if m["role"] == "student"]


def teacher_models() -> list[dict[str, Any]]:
    return [m for m in MODELS if m["role"] == "teacher"]


def teacher_model() -> dict[str, Any]:
    return dict(TEACHER)


def engine_kwargs(model: dict[str, Any]) -> dict[str, Any]:
    kwargs = dict(model["vllm"])
    kwargs.setdefault("quantization", "bitsandbytes")
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
