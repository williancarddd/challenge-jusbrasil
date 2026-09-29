"""Fase 1: pedir à LLM que aponte as citações de um bloco, e verificar o que ela devolve.

O contrato com o modelo é estreito de propósito: ele devolve **o trecho literal** e uma
confiança, nada mais. Não classifica, não canoniza, não resolve — isso é fase 2. O
trecho literal é o que permite recuperar o span pelo `token.idx` sem tolerância nenhuma.

A verificação não é opcional. Medido no gabarito: quando a saída não é literal, o modo
de falha é sempre "não encontrado", nunca "encontrado no lugar errado" — então conferir
que a string existe no bloco detecta 100% dos desvios. O que ela não faz é evitá-los;
para isso existe a decodificação restrita por gramática.
"""

from __future__ import annotations

import json
import math
import re
import os
from dataclasses import dataclass, replace

import httpx

from cacador_alucinacoes.preprocessing import Block

DEFAULT_ENDPOINT = "http://localhost:8000/v1/chat/completions"
DEFAULT_MODEL = "qwen3-8b-fp8"
GEMMA_NAME = "gemma-distil"
_TAG = re.compile(r"<start>(.*?)<end>", re.DOTALL)


def default_workers() -> int:
    """Um trabalhador por CPU, menos uma, deixada para o processo principal.

    Lido da máquina em vez de fixado, porque o envelope da avaliação (8 vCPUs) não é o
    da máquina de desenvolvimento. `WORKERS` no ambiente sobrepõe — é assim que se roda
    serializado (`WORKERS=1`) quando o objetivo é reprodutibilidade.
    """
    override = os.environ.get("WORKERS")
    if override:
        return max(1, int(override))
    return max(1, (os.cpu_count() or 2) - 1)

# O schema é imposto pelo xgrammar no vLLM: o modelo não consegue emitir JSON fora dele.
# Isso garante a *forma* da resposta. Garantir que o `text` seja substring do bloco é
# outro problema — ver `verify` e a nota no topo.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["text", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["citations"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
Você identifica citações jurídicas em trechos de peças processuais brasileiras.

REGRA ABSOLUTA: copie o trecho EXATAMENTE como aparece no texto, caractere por \
caractere. O texto contém erros de digitalização — números partidos por espaço, letras \
trocadas, abreviações irregulares. NÃO corrija nada. NÃO complete abreviações. NÃO \
ajuste acentuação, maiúsculas, pontuação ou espaçamento. Um trecho corrigido é inútil e \
será descartado.

Existem DUAS famílias de citação, e as duas contam.

FAMÍLIA 1 — referência com identificador, em três formatos:
  processo    <classe recursal> <número> <UF>   ex.: "AgRg no REsp 1.234.567/SP"
              ou número no formato CNJ          ex.: "REspe 0600530-94.2020.6.26.0171"
  dispositivo <artigo> do <código ou lei>       ex.: "art. 5º, LV, da Constituição"
  súmula      Súmula [Vinculante] <número>      ex.: "Súmula 284 do STF"

FAMÍLIA 2 — julgado SEM número de processo, mas identificado por ano e relator. \
Também é citação e também deve ser retornada: "o julgado do STJ proferido em 2019 pela \
relatoria do Ministro Fulano", "Rcl de 2022, Rel. Min. Fulano".

Referência genérica, que não aponta para nenhuma fonte específica, NÃO é citação e NÃO \
deve ser retornada: "a jurisprudência pacífica desta Corte", "o dispositivo \
constitucional invocado", "as normas de regência da matéria", "o verbete sumular \
aplicável", "reiterados precedentes do Superior Tribunal de Justiça".

ONDE O TRECHO COMEÇA E TERMINA — é o erro mais comum. Devolva SÓ a referência, nunca a \
frase que a contém. Comece no primeiro token da própria citação e termine no último. \
Inclua os prefixos recursais que antecedem a classe ("AgRg no", "EDcl nos EDcl no", \
"AgInt no"), porque fazem parte dela. Exclua verbos, conectivos e comentários em volta.

  texto:   "A propósito, veja-se o REsp 8.111.222/MG, que bem ilustra a matéria."
  correto: "REsp 8.111.222/MG"
  errado:  "A propósito, veja-se o REsp 8.111.222/MG, que bem ilustra a matéria."

  texto:   "Cumpre destacar o AgInt no AREsp 9.888.777/BA, de idêntica premissa."
  correto: "AgInt no AREsp 9.888.777/BA"

INCLUA OS QUALIFICADORES DA REFERÊNCIA. Tudo que identifica ou restringe a fonte citada \
faz parte da citação: tribunal, ano, número da turma, e sobretudo o RELATOR. Vá até o \
fim dessa informação, mesmo que ela venha depois de vírgula. O que não entra é o \
comentário sobre a citação — o que ela decidiu, por que se aplica, o que dela se extrai.

A linha é essa: enquanto o texto ainda estiver dizendo QUAL é a fonte, inclua; quando \
passar a dizer o que ela significa ou por que foi invocada, pare.

  texto:   "Milita em favor da parte a Rcl de 2022, Rel. Min. Alexandre De Moraes, que \
reconhece a excepcionalidade da medida."
  correto: "Rcl de 2022, Rel. Min. Alexandre De Moraes"
  errado:  "Rcl de 2022"                        (cortou o relator, que identifica a fonte)
  errado:  "Rcl de 2022, Rel. Min. Alexandre De Moraes, que reconhece a excepcionalidade \
da medida."                                     (levou o comentário junto)

  texto:   "Como se vê do acórdão do STJ julgado em 2021 sob relatoria de Fulano de Tal, \
a tese não prospera."
  correto: "acórdão do STJ julgado em 2021 sob relatoria de Fulano de Tal"

NÃO retorne: número dos autos do próprio documento, protocolo, inscrição na OAB, \
referência a folhas dos autos, valor da causa, título de seção, nem o parágrafo inteiro.

confidence é sua confiança de que o trecho é mesmo uma citação, de 0 a 1.
Se não houver citação alguma, devolva a lista vazia."""


@dataclass(frozen=True)
class Candidate:
    """O que a LLM devolveu, antes de qualquer verificação."""

    text: str
    confidence: float
    # A probabilidade dos tokens, não o número que a LLM escreveu. Ver `token_confidence`.
    logprob: float | None = None


# Os distratores nomeados pelo §2 do PDF: "número dos autos do próprio documento,
# protocolo, inscrição na OAB, fls. 234/567, valor da causa. Nenhum está no gabarito —
# extraí-los conta como falso positivo." Isto é especificação, não forma enumerada a
# partir da amostra. Medido: 0 das 225 citações do gabarito contém qualquer um destes.
#
# `autos` fica DE FORA de propósito: o mesmo parágrafo do PDF distingue o número dos
# autos do próprio documento (distrator) da referência a outro processo em formato CNJ
# no corpo do texto (citação legítima). Rejeitar por "autos" comeria a segunda.
KNOWN_DISTRACTORS = re.compile(
    r"OAB|\bfls?\.|\bfolhas?\b|protocolo|R\$|valor\s+da\s+causa", re.IGNORECASE
)

# A peça ou decisão que está SENDO julgada não é citação — é o objeto do processo, não
# precedente invocado. O que separa uma da outra não é o substantivo (`acórdão` aparece
# nas duas) e sim o particípio que o marca como atacado, ou o verbo de interposição.
# Medido: 0 das 225 citações do gabarito casam com isto, e ele preserva
# `recente acórdão da Segunda Turma` enquanto rejeita `acórdão recorrido`.
UNDER_JUDGMENT = re.compile(
    r"\b(?:ac(?:ó|o)rd(?:ã|a)o|decis(?:ã|a)o|senten(?:ç|c)a|julgado|ju[íi]zo)\s+"
    r"(?:recorrid|agravad|embargad|impugnad|atacad|hostilizad|combatid|guerreiad|"
    r"de\s+origem|a\s+quo)"
    r"|\b(?:apela(?:ç|c)(?:ã|a)o|recurso|agravo)\s+interpost"
    r"|\br\.\s+senten(?:ç|c)a"
    r"|\bautos\s+em\s+refer(?:ê|e)ncia",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Extraction:
    """Resultado de um bloco, com os descartes preservados em vez de sumidos."""

    block: Block
    verified: list[Candidate]
    hallucinated: list[Candidate]
    whole_block: list[Candidate]
    distractor: list[Candidate]

    @property
    def transcription_failures(self) -> int:
        """Quantos candidatos a LLM devolveu que não existem no bloco."""
        return len(self.hallucinated)


def verify(block: Block, candidates: list[Candidate]) -> Extraction:
    """Separa o aproveitável do que a LLM reescreveu e do que é o bloco inteiro.

    Duas rejeições, com fundamentos diferentes:

    - **não existe no bloco**: a LLM reescreveu o texto em vez de copiá-lo. Medido no
      gabarito, o modo de falha é sempre esse — nunca "achou no lugar errado" —, então
      conferir a presença literal detecta 100% dos desvios de transcrição.
    - **é o bloco inteiro**: nenhuma das 225 citações do gabarito ocupa um bloco
      completo, nem 80% dele. Quando a LLM devolve o bloco todo ela está marcando um
      título de seção (`III - DOS PRECEDENTES INVOCADOS`) ou o fecho da peça
      (`Nestes termos, pede deferimento.`). Sozinha, esta regra levou a precisão de
      63,5% para 83,0% sem custar recall nenhum.
    - **contém distrator nomeado pelo enunciado** (`OAB`, `fls.`, protocolo, valor da
      causa) **ou é a peça sob julgamento** (`acórdão recorrido`, `r. sentença`). Ver
      `KNOWN_DISTRACTORS` e `UNDER_JUDGMENT`.
    """
    whole = block.text.strip()
    verified, hallucinated, whole_block, distractor = [], [], [], []
    for candidate in candidates:
        if candidate.text not in block.text:
            hallucinated.append(candidate)
        elif candidate.text.strip() == whole:
            whole_block.append(candidate)
        elif KNOWN_DISTRACTORS.search(candidate.text) or UNDER_JUDGMENT.search(
            candidate.text
        ):
            distractor.append(candidate)
        else:
            verified.append(candidate)
    return Extraction(
        block=block,
        verified=verified,
        hallucinated=hallucinated,
        whole_block=whole_block,
        distractor=distractor,
    )


def _prompt_treinado() -> str:
    from challenge_jusbrasil.settings import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def build_gemma_request(block: Block, *, model: str = GEMMA_NAME) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _prompt_treinado()},
            {"role": "user", "content": block.text},
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": -1,
        "seed": 0,
        "max_tokens": 4096,
    }


def parse_tags(body: dict) -> list[Candidate]:
    content = body["choices"][0]["message"]["content"] or ""
    vistos: list[str] = []
    for trecho in _TAG.findall(content):
        if trecho and trecho not in vistos:
            vistos.append(trecho)
    return [Candidate(text=trecho, confidence=1.0) for trecho in vistos]


def build_request(block: Block, *, model: str = DEFAULT_MODEL) -> dict:
    """Monta o payload."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": block.text},
        ],
        # A saída precisa ser determinística para o pacote de verificação reproduzir o
        # score. Temperatura zero sozinha não basta: o `generation_config.json` do Qwen3
        # traz `do_sample: true`, `top_k: 20` e `top_p: 0.95`, e o vLLM os adota como
        # default do servidor. Os três são neutralizados aqui, e o servidor sobe com
        # `--generation-config=vllm` para não herdá-los de saída.
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": -1,
        "seed": 0,
        # O raciocínio consome centenas de tokens antes do JSON. Com 3000 um bloco do
        # `gen_n2_003` ainda saía truncado no meio da string e perdia todas as suas
        # citações; o teto agora acompanha o KV cache disponível.
        "max_tokens": 6000,
        # Medido por ablação: o modo de raciocínio do Qwen3 vale +20 citações de recall
        # (170 -> 190 de 225). Desligá-lo para economizar contexto foi o que derrubou o
        # recall numa investigação anterior — o custo é tempo, e há 75x de folga.
        "chat_template_kwargs": {"enable_thinking": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "citations", "schema": RESPONSE_SCHEMA},
        },
    }


_CITATION_OBJECT = re.compile(
    r'\{\s*"text"\s*:\s*("(?:[^"\\]|\\.)*")\s*,\s*"confidence"\s*:\s*([0-9.]+)\s*\}'
)


def parse_response(body: dict) -> list[Candidate]:
    """Lê a lista de citações, salvando o que der quando a resposta vem truncada.

    O modelo às vezes entra em loop repetindo a mesma citação até bater no teto de
    tokens, e aí o JSON chega sem fechar. Descartar a resposta inteira perderia também
    as citações legítimas que vieram antes do loop — então os objetos completos são
    recuperados um a um e deduplicados, que é justamente o que desfaz a repetição.
    """
    content = body["choices"][0]["message"]["content"]
    try:
        items = json.loads(content).get("citations", [])
        return [
            Candidate(text=item["text"], confidence=float(item.get("confidence", 1.0)))
            for item in items
        ]
    except json.JSONDecodeError:
        pass

    seen, salvaged = set(), []
    for raw_text, confidence in _CITATION_OBJECT.findall(content):
        text = json.loads(raw_text)
        if text in seen:
            continue
        seen.add(text)
        salvaged.append(Candidate(text=text, confidence=float(confidence)))
    return salvaged


def token_confidence(body: dict) -> dict[str, float]:
    """Média geométrica das probabilidades dos tokens de cada item, por texto.

    Cobre do `{` do item ao fim do valor de `text`: inclui a decisão de abrir o item, não
    só a cópia do trecho. Medido contra o gabarito (169 spans, 8 errados): AUC 0,871,
    contra 0,821 do produto das probabilidades e 0,809 da mínima.

    O alinhamento é em bytes, não em caracteres, porque um token pode carregar meio
    caractere UTF-8 — os acentos do português caem nisso.
    """
    choice = body["choices"][0]
    tokens = (choice.get("logprobs") or {}).get("content") or []
    content = (choice["message"]["content"] or "").encode("utf-8")
    stream = b"".join(bytes(token["bytes"]) for token in tokens)
    base = stream.rfind(content)
    if not tokens or base < 0:
        return {}

    starts, cursor = [], 0
    for token in tokens:
        starts.append(cursor)
        cursor += len(token["bytes"])

    out, search_from = {}, 0
    for candidate in parse_response(body):
        encoded = json.dumps(candidate.text, ensure_ascii=False).encode("utf-8")
        at = content.find(encoded, search_from)
        if at < 0:
            continue
        search_from = at + len(encoded)
        first = base + content.rfind(b"{", 0, at)
        last = base + at + len(encoded)
        values = [
            token["logprob"]
            for token, start in zip(tokens, starts)
            if start < last and start + len(token["bytes"]) > first
        ]
        if values and candidate.text not in out:
            out[candidate.text] = math.exp(sum(values) / len(values))
    return out


def extract(
    block: Block,
    client: httpx.Client,
    *,
    model: str | None = None,
) -> Extraction:
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    if model == GEMMA_NAME:
        payload = build_gemma_request(block, model=model)
        response = client.post(DEFAULT_ENDPOINT, json=payload)
        response.raise_for_status()
        return verify(block, parse_tags(response.json()))
    payload = build_request(block, model=model)
    # Não altera a decodificação (gulosa): só devolve a probabilidade de cada token
    # gerado, de onde sai a confiança da LLM.
    payload["logprobs"] = True
    response = client.post(DEFAULT_ENDPOINT, json=payload)
    response.raise_for_status()
    body = response.json()
    confidence = token_confidence(body)
    candidates = [
        replace(candidate, logprob=confidence.get(candidate.text))
        for candidate in parse_response(body)
    ]
    return verify(block, candidates)
