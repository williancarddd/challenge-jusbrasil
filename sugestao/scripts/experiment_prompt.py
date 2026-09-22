"""Banco de ensaio do prompt — NÃO altera o pipeline.

O diagnóstico que motiva: quando o bloco traz citação **com** número, a família 2 é
sub-reportada. Medido no cache, a LLM não devolve nada nas posições das 11 citações
vagas perdidas — não é borda cortada, é ausência —, e nos mesmos blocos ela devolve as
numeradas. A hipótese é que as duas famílias competem pela mesma resposta.

Três variantes sobre o mesmo conjunto de blocos:

    atual          uma chamada, um array. O controle — é o `SYSTEM_PROMPT` do pipeline,
                   sem uma vírgula de diferença.
    schema-duplo   uma chamada, DOIS arrays obrigatórios. A gramática do xgrammar impede
                   a resposta de existir sem abrir a lista da família 2: a separação vira
                   estrutural em vez de textual.
    duas-passadas  duas chamadas, uma por família, cada uma com a seção da outra família
                   removida do prompt.

**Uma variável por vez**: as três partem do mesmo texto e diferem só na separação das
famílias. As variantes são construídas por cirurgia sobre o `SYSTEM_PROMPT` real, com
asserção de que a cirurgia pegou — reescrever o prompt à mão introduziria diferenças de
redação que se confundiriam com o efeito medido.

Todas rodam **serializadas**, porque o batching contínuo do vLLM muda a saída entre
execuções e confundiria efeito do prompt com variância.

Uso: `uv run python scripts/experiment_prompt.py [variante ...]`
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict

import httpx

from cacador_alucinacoes.extraction import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    Candidate,
    parse_response,
    verify,
)
from cacador_alucinacoes.goldenset import ROOT, load_documents
from cacador_alucinacoes.preprocessing import usable_blocks
from cacador_alucinacoes.span_recovery import locate, portuguese_tokenizer

# Âncoras da cirurgia. Se o `SYSTEM_PROMPT` mudar de forma, o `assert` abaixo quebra —
# o que é o comportamento certo: a variante deixaria de ser comparável ao controle.
_FAMILY_1_HEAD = "FAMÍLIA 1 — referência com identificador"
_FAMILY_2_HEAD = "FAMÍLIA 2 — referência a uma fonte jurídica SEM identificador"
_AFTER_FAMILIES = "ONDE O TRECHO COMEÇA E TERMINA"
_BOTH_COUNT = "Existem DUAS famílias de citação, e as duas contam."


def _section(text: str, start_mark: str, end_mark: str) -> str:
    start = text.index(start_mark)
    return text[start : text.index(end_mark, start)]


FAMILY_1 = _section(SYSTEM_PROMPT, _FAMILY_1_HEAD, _FAMILY_2_HEAD)
FAMILY_2 = _section(SYSTEM_PROMPT, _FAMILY_2_HEAD, _AFTER_FAMILIES)
assert FAMILY_1.strip() and FAMILY_2.strip(), "a cirurgia no SYSTEM_PROMPT não pegou"

# schema-duplo: mesma instrução, mais um parágrafo dizendo que são duas listas.
_TWO_LISTS = (
    "Cada família tem sua PRÓPRIA lista na resposta, e uma não dispensa a outra: o mesmo "
    "trecho pode trazer as duas, e é comum que traga. Percorra o trecho inteiro para cada "
    "uma; devolva lista vazia só quando aquela família realmente não ocorrer."
)
PROMPT_SPLIT = SYSTEM_PROMPT.replace(_BOTH_COUNT, f"{_BOTH_COUNT} {_TWO_LISTS}")
assert PROMPT_SPLIT != SYSTEM_PROMPT, "a âncora das duas famílias não foi encontrada"

# duas-passadas: cada prompt perde a seção da outra família.
PROMPT_ONLY_1 = SYSTEM_PROMPT.replace(FAMILY_2, "").replace(
    _BOTH_COUNT,
    "Nesta tarefa interessa UMA família de citação. Referência genérica, sem "
    "identificador que permita localizá-la, NÃO entra — ela é tratada em outro lugar.",
)
PROMPT_ONLY_2 = SYSTEM_PROMPT.replace(FAMILY_1, "").replace(
    _BOTH_COUNT,
    "Nesta tarefa interessa UMA família de citação. Citação com número de processo, "
    "artigo de lei ou número de súmula NÃO entra — ela é tratada em outro lugar.",
)
assert FAMILY_2 not in PROMPT_ONLY_1 and FAMILY_1 not in PROMPT_ONLY_2

_ITEM = RESPONSE_SCHEMA["properties"]["citations"]["items"]
DOUBLE_SCHEMA = {
    "type": "object",
    "properties": {
        "com_identificador": {"type": "array", "items": _ITEM},
        "sem_identificador": {"type": "array", "items": _ITEM},
    },
    "required": ["com_identificador", "sem_identificador"],
    "additionalProperties": False,
}

VARIANTS = {
    "atual": [(SYSTEM_PROMPT, RESPONSE_SCHEMA, ["citations"])],
    "schema-duplo": [(PROMPT_SPLIT, DOUBLE_SCHEMA, ["com_identificador", "sem_identificador"])],
    "duas-passadas": [
        (PROMPT_ONLY_1, RESPONSE_SCHEMA, ["citations"]),
        (PROMPT_ONLY_2, RESPONSE_SCHEMA, ["citations"]),
    ],
}


def _candidates(body: dict, keys: list[str]) -> list[Candidate]:
    content = body["choices"][0]["message"]["content"]
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return parse_response(body)  # truncada: recupera os objetos completos
    return [
        Candidate(text=item["text"], confidence=float(item.get("confidence", 1.0)))
        for key in keys
        for item in payload.get(key, [])
    ]


def capture(variant: str) -> dict:
    documents = load_documents()
    nlp = portuguese_tokenizer()
    passes = VARIANTS[variant]
    captured: dict[str, list[dict]] = defaultdict(list)
    started = time.monotonic()

    with httpx.Client(timeout=600) as client:
        for document_id, document in documents.items():
            for block in usable_blocks(document):
                confidence_of: dict[str, float] = {}
                for prompt, schema, keys in passes:
                    response = client.post(DEFAULT_ENDPOINT, json={
                        "model": DEFAULT_MODEL,
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": block.text},
                        ],
                        "temperature": 0.0, "top_p": 1.0, "top_k": -1, "seed": 0,
                        "max_tokens": 6000,
                        "chat_template_kwargs": {"enable_thinking": True},
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {"name": "citations", "schema": schema},
                        },
                    })
                    response.raise_for_status()
                    for candidate in verify(block, _candidates(response.json(), keys)).verified:
                        confidence_of.setdefault(candidate.text, candidate.confidence)
                if not confidence_of:
                    continue
                located, _ = locate(block, sorted(confidence_of), nlp)
                for span in located:
                    captured[document_id].append({
                        "start": span.start, "end": span.end, "text": span.text,
                        "block_index": span.block_index,
                        "confidence": confidence_of.get(span.text, 1.0),
                    })
            print(f"  {document_id}: {len(captured[document_id])} spans", flush=True)

    print(f"{variant}: {time.monotonic() - started:.0f}s para 26 documentos")
    return dict(captured)


def main() -> None:
    wanted = sys.argv[1:] or list(VARIANTS)
    for variant in wanted:
        if variant not in VARIANTS:
            sys.exit(f"variante desconhecida: {variant}. Há {list(VARIANTS)}")
        print(f"\n=== {variant} ===", flush=True)
        path = ROOT / "data" / f"cache_{variant}.json"
        path.write_text(json.dumps(capture(variant), indent=1), encoding="utf-8")
        print(f"salvo em {path}")


if __name__ == "__main__":
    main()
