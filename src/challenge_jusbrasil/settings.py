from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TXT_DIR = ROOT / "data" / "txt"
LORA_BASE = "unsloth/gemma-3-12b-it-unsloth-bnb-4bit"
LORA_DIR = ROOT / "models" / "gemma-3-12b-lora"
GOLDENSET_PATH = ROOT / "data" / "goldenset.csv"
RESULTS_DIR = ROOT / "results"

INFER_BATCH_SIZE = 1000
BUSCA = "regex"
MAX_MODEL_LEN = 8192
CHUNK_OVERLAP = 200
CHARS_PER_TOKEN = 2
CHAT_OVERHEAD_TOKENS = 256

VLLM_ENGINE: dict[str, Any] = {
    "trust_remote_code": True,
    "gpu_memory_utilization": 0.90,
    "seed": 42,
    "disable_log_stats": False,
    "max_model_len": MAX_MODEL_LEN,
}

VLLM_SAMPLING: dict[str, Any] = {
    "temperature": 0.0,
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
    },
    {
        "name": "unsloth/Phi-4-mini-instruct-unsloth-bnb-4bit",
        "family": "Phi",
        "parameters": "3.8B",
        "quantization": "bnb-4bit",
        "url": "https://huggingface.co/unsloth/Phi-4-mini-instruct-unsloth-bnb-4bit",
        "role": "student",
    },
    {
        "name": "unsloth/Qwen3-8B-unsloth-bnb-4bit",
        "family": "Qwen",
        "parameters": "8B",
        "quantization": "bnb-4bit",
        "url": "https://huggingface.co/unsloth/Qwen3-8B-unsloth-bnb-4bit",
        "role": "student",
    },
    {
        "name": "unsloth/gemma-3-12b-it-unsloth-bnb-4bit",
        "family": "Gemma",
        "parameters": "12B",
        "quantization": "bnb-4bit",
        "url": "https://huggingface.co/unsloth/gemma-3-12b-it-unsloth-bnb-4bit",
        "role": "student",
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

SYSTEM_PROMPT = """You extract legal citations in a Brazilian judicial document.

Return the same text, without changing any character, and mark each citation with <start> and <end>.
Do not return JSON. Do not return a confidence score. Do not classify the citation. Do not output an id. Do not write anything outside the marked text.

Mark each citation with a bare tag. Do not set attributes on the tag.
<start>exact span<end>

A citation points at a legal source: a statute, article, code, constitution, súmula, precedent, judgment, or theme of general repercussion. Mark it even when it has no number.
The span starts at the first word of the citation and runs through its identifier: number, court, state, and rapporteur when the citation is descriptive. Keep line breaks that fall inside the span. Do not mark a bare number. Do not mark a person's name alone.
Leave untagged a sentence that only asserts a court position and names no source. Leave untagged the case number of the document itself, OAB, protocol, page sheets (fls.), including a long range, and the amount in dispute.
Mark one citation per span. Spans must not overlap. The text between the tags is a literal copy of the document, including line breaks.
If there is no citation, return the text with no tags.

Examples:

Input:
A OAB/SP 123.456 não integra a fundamentação. O pedido se apoia no art. 12 da Lei nº 1.234/2000.
Output:
A OAB/SP 123.456 não integra a fundamentação. O pedido se apoia no <start>art. 12 da Lei nº 1.234/2000<end>.

Input:
O valor da causa é R$ 8.500,00. A Súmula 12 do STJ orienta o caso.
Output:
O valor da causa é R$ 8.500,00. A <start>Súmula 12 do STJ<end> orienta o caso.

Input:
A peça menciona o AgInt no AREsp 2.104.883/SP. As folhas são fls. 418/902. O protocolo é 2020/000222.
Output:
A peça menciona o <start>AgInt no AREsp 2.104.883/SP<end>. As folhas são fls. 418/902. O protocolo é 2020/000222.

Input:
Confira-se o Embargos de Declaração no Recurso Ordinário nº
45.678/BA, distinto do número isolado 45.678.
Output:
Confira-se o <start>Embargos de Declaração no Recurso Ordinário nº
45.678/BA<end>, distinto do número isolado 45.678.

Input:
O paradigma é o TST-RR-1000-11.2019.5.03.0001. Discute-se o Tema 999 da repercussão geral.
Output:
O paradigma é o <start>TST-RR-1000-11.2019.5.03.0001<end>. Discute-se o <start>Tema 999 da repercussão geral<end>.

Input:
Invoca-se o art. 904 do Código Eleitoral e o R-Rp nº 12.345/DF.
Output:
Invoca-se o <start>art. 904 do Código Eleitoral<end> e o <start>R-Rp nº 12.345/DF<end>.

Input:
Há precedente reiterado deste tribunal sobre o tema. A posição dos tribunais é firme neste ponto.
Output:
Há <start>precedente reiterado deste tribunal<end> sobre o tema. A posição dos tribunais é firme neste ponto.

Input:
Aplica-se o dispositivo legal aplicável à controvérsia. Cita-se acórdão do STJ julgado em 2019 sob a relatoria de Nancy Andrighi.
Output:
Aplica-se o <start>dispositivo legal aplicável à controvérsia<end>. Cita-se <start>acórdão do STJ julgado em 2019 sob a relatoria de Nancy Andrighi<end>.
"""


def student_models() -> list[dict[str, Any]]:
    return [m for m in MODELS if m["role"] == "student"]


def teacher_models() -> list[dict[str, Any]]:
    return [m for m in MODELS if m["role"] == "teacher"]


def teacher_model() -> dict[str, Any]:
    return dict(TEACHER)


def modelo_padrao() -> dict[str, Any]:
    for modelo in MODELS:
        if modelo["name"] == LORA_BASE:
            return modelo
    raise SystemExit(f"modelo padrão ausente: {LORA_BASE}")


def lora_dir() -> Path:
    bruto = os.environ.get("LORA_PATH", "").strip()
    caminho = Path(bruto) if bruto else LORA_DIR
    if not (caminho / "adapter_config.json").is_file():
        raise SystemExit(f"adaptador LoRA ausente: {caminho}")
    return caminho


def engine_kwargs(model: dict[str, Any]) -> dict[str, Any]:
    kwargs = dict(model["vllm"])
    if os.environ.get("GPU_MEMORY_UTILIZATION", "").strip():
        kwargs["gpu_memory_utilization"] = float(os.environ["GPU_MEMORY_UTILIZATION"])
    kwargs.setdefault("quantization", "bitsandbytes")
    kwargs.setdefault("max_model_len", MAX_MODEL_LEN)
    if model["name"] == LORA_BASE:
        lora_dir()
        kwargs["enable_lora"] = True
        kwargs["max_lora_rank"] = 16
        kwargs["max_loras"] = 1
    return kwargs


def reserva_tokens() -> int:
    return (len(SYSTEM_PROMPT) + 64) // CHARS_PER_TOKEN + CHAT_OVERHEAD_TOKENS


def orcamento_texto(model: dict[str, Any]) -> int:
    max_len = int(engine_kwargs(model)["max_model_len"])
    max_out = int(infer_sampling(model)["max_tokens"])
    tokens = max(CHUNK_OVERLAP, max_len - max_out - reserva_tokens())
    return tokens * CHARS_PER_TOKEN


def infer_sampling(model: dict[str, Any]) -> dict[str, Any]:
    params = dict(VLLM_SAMPLING)
    max_len = int(engine_kwargs(model)["max_model_len"])
    livre = max(0, max_len - reserva_tokens())
    params["max_tokens"] = max(64, min(max_len // 2, (livre * 3) // 5))
    return params


def user_prompt(documento_id: str, texto: str) -> str:
    return f"documento_id: {documento_id}\n\n{texto}"


def chat_prompt(documento_id: str, texto: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(documento_id, texto)},
    ]
