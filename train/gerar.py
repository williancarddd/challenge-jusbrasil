from __future__ import annotations

import json
import random
import re
from pathlib import Path

from challenge_jusbrasil.pipeline import chat_lotes, descarregar_llm
from challenge_jusbrasil.settings import ROOT, chat_prompt, engine_kwargs, teacher_model

SAIDA = ROOT / "data" / "train"
META = SAIDA / "gemma.jsonl"
MANIFESTO = SAIDA / "manifest.jsonl"
TOTAL = 1000
MAX_LEN = 4096
MAX_TOKENS = 1400
LOTE = 32
_TAG = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")

SISTEMA = """Você redige peças judiciais brasileiras.
Marque cada citação, completa ou incompleta, com <start> e <end>.
Citação incompleta é a que aponta uma fonte e não traz número de artigo, de súmula ou de processo.
Deixe sem marca o número do próprio caso, OAB, protocolo, folhas e valores em reais.
Responda somente com a peça."""

_PECAS = (
    "memorial",
    "voto",
    "acórdão",
    "decisão monocrática",
    "parecer",
    "embargos de declaração",
)
_TRIBUNAIS = ("STF", "STJ", "TST", "TSE", "STM", "TJSP", "TRF4", "TRT3")
_TEMAS = (
    "prescrição intercorrente",
    "competência da justiça do trabalho",
    "tutela de urgência em contrato administrativo",
    "responsabilidade civil por acidente de trânsito",
    "improbidade e dolo específico",
    "execução fiscal e prescrição",
    "adicional de insalubridade",
    "guarda compartilhada",
    "recuperação judicial e crédito trabalhista",
    "mandado de segurança contra ato de mesa",
    "aposentadoria especial",
    "usucapião extrajudicial",
    "despejo por falta de pagamento",
    "habeas corpus e prisão preventiva",
    "licitação e sobrepreço",
)


def pedido(indice: int, rng: random.Random) -> str:
    return (
        f"Escreva um {rng.choice(_PECAS)} do {rng.choice(_TRIBUNAIS)} "
        f"sobre {rng.choice(_TEMAS)}. "
        "Tamanho entre 2200 e 3400 caracteres. "
        "Inclua de 6 a 10 citações: leis com artigo e diploma, julgados com número, "
        "menções sem número e ao menos um identificador inventado. "
        "Invente relatores, datas e números. "
        "Prosa contínua, sem lista e sem título de seção. "
        f"Variação {indice}."
    )


def limpar(bruto: str) -> tuple[str, str] | None:
    texto = bruto.strip()
    texto = _TAG.sub("", texto).strip()
    if texto.count("<start>") != texto.count("<end>") or "<start>" not in texto:
        return None
    partes: list[str] = []
    cursor = 0
    marcas = 0
    while True:
        inicio = texto.find("<start>", cursor)
        if inicio < 0:
            partes.append(texto[cursor:])
            break
        fim = texto.find("<end>", inicio + 7)
        if fim < 0 or "<start>" in texto[inicio + 7 : fim]:
            return None
        partes.append(texto[cursor:inicio])
        partes.append(texto[inicio + 7 : fim])
        marcas += 1
        cursor = fim + 5
    plano = "".join(partes)
    if marcas < 4 or not 800 <= len(plano) <= 4500:
        return None
    return plano, texto


def gravar(indice: int, plano: str, marcado: str) -> None:
    nome = f"gem_{indice:04d}"
    (SAIDA / f"{nome}.txt").write_text(plano, encoding="utf-8")
    registro = {
        "documento_id": nome,
        "inicio": 0,
        "messages": [
            *chat_prompt(nome, plano),
            {"role": "assistant", "content": marcado},
        ],
    }
    with META.open("a", encoding="utf-8") as saida:
        saida.write(json.dumps(registro, ensure_ascii=False) + "\n")
    with MANIFESTO.open("a", encoding="utf-8") as saida:
        saida.write(
            json.dumps(
                {"arquivo": f"{nome}.txt", "origem": "gemma", "operacao": "gemma"},
                ensure_ascii=False,
            )
            + "\n"
        )


def gerar(total: int = TOTAL) -> None:
    from vllm import LLM, SamplingParams

    SAIDA.mkdir(parents=True, exist_ok=True)
    prontos = {path.stem for path in SAIDA.glob("gem_*.txt")}
    faltam = [indice for indice in range(1, total + 1) if f"gem_{indice:04d}" not in prontos]
    if not faltam:
        print(f"ja existem {total} exemplos em {SAIDA}", flush=True)
        return
    professor = teacher_model()
    kwargs = engine_kwargs(professor)
    kwargs["max_model_len"] = MAX_LEN
    print(f"load {professor['name']} faltam={len(faltam)}", flush=True)
    llm = LLM(model=professor["name"], **kwargs)
    try:
        rodada = 0
        while faltam and rodada < 4:
            rodada += 1
            sampling = SamplingParams(temperature=0.7 + 0.1 * rodada, top_p=0.95, max_tokens=MAX_TOKENS)
            print(f"rodada {rodada} pedidos={len(faltam)}", flush=True)
            rejeitados: list[int] = []
            aceitos = 0
            for inicio in range(0, len(faltam), LOTE):
                bloco = faltam[inicio : inicio + LOTE]
                mensagens = [
                    [
                        {"role": "system", "content": SISTEMA},
                        {"role": "user", "content": pedido(indice, random.Random(indice * 1009 + rodada))},
                    ]
                    for indice in bloco
                ]
                brutos = chat_lotes(llm, sampling, mensagens, LOTE, professor)
                for indice, bruto in zip(bloco, brutos, strict=True):
                    par = limpar(bruto)
                    if par is None:
                        rejeitados.append(indice)
                        continue
                    gravar(indice, par[0], par[1])
                    aceitos += 1
                print(
                    f"rodada {rodada} aceitos={aceitos} rejeitados={len(rejeitados)}",
                    flush=True,
                )
            faltam = rejeitados
    finally:
        descarregar_llm(llm)
    if faltam:
        raise SystemExit(f"faltaram {len(faltam)} exemplos válidos")
    print(f"exemplos={total} pasta={SAIDA}", flush=True)


if __name__ == "__main__":
    gerar()
