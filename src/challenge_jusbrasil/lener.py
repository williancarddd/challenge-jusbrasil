from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from challenge_jusbrasil.pipeline import (
    EXTRACT_DIR,
    _carimbo,
    _escrever_json,
    _pasta_run,
    buscar,
    carregar_documentos,
    imprimir_avaliacao,
    model_slug,
)
from challenge_jusbrasil.resolver.lei import tipo_de
from challenge_jusbrasil.settings import RESULTS_DIR, ROOT, TXT_DIR
from challenge_jusbrasil.utils.kaggle_metric import IOU_MIN, _iou

MODELO = "pierreguillou/ner-bert-base-cased-pt-lenerbr"
ADAPTER_DIR = ROOT / "results" / "train" / "lener"
MAX_LEN = 512
STRIDE = 128
GAP_MAX = 20
EPOCHS = 6
LR = 3e-5
_ROTULOS = {"LEGISLACAO", "JURISPRUDENCIA"}
_CORTE = re.compile(r"[.!?\n]")
_TAG = re.compile(r"<start>(.*?)<end>", flags=re.DOTALL)
_LABELS = [
    "O",
    "B-LEGISLACAO",
    "I-LEGISLACAO",
    "B-JURISPRUDENCIA",
    "I-JURISPRUDENCIA",
]


def _spans_da_janela(rotulos: list[str], offsets: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    atual: list[Any] | None = None
    for rotulo, (inicio, fim) in zip(rotulos, offsets, strict=True):
        if inicio == fim:
            continue
        nome = rotulo[2:] if rotulo.startswith(("B-", "I-")) else ""
        if nome not in _ROTULOS:
            if atual is not None:
                spans.append((atual[0], atual[1], atual[2]))
                atual = None
            continue
        if atual is not None and atual[2] == nome and rotulo.startswith("I-"):
            atual[1] = fim
            continue
        if atual is not None:
            spans.append((atual[0], atual[1], atual[2]))
        atual = [inicio, fim, nome]
    if atual is not None:
        spans.append((atual[0], atual[1], atual[2]))
    return spans


def _juntar(texto: str, spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    ordenados = sorted(spans)
    saida: list[tuple[int, int, str]] = []
    for inicio, fim, rotulo in ordenados:
        if not saida:
            saida.append((inicio, fim, rotulo))
            continue
        ant_i, ant_f, ant_r = saida[-1]
        if rotulo == ant_r and inicio <= ant_f:
            saida[-1] = (ant_i, max(ant_f, fim), rotulo)
            continue
        meio = texto[ant_f:inicio]
        if rotulo == ant_r and 0 <= inicio - ant_f <= GAP_MAX and _CORTE.search(meio) is None:
            saida[-1] = (ant_i, fim, rotulo)
            continue
        saida.append((inicio, fim, rotulo))
    return saida


def _preferir_longos(citacoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordenadas = sorted(citacoes, key=lambda cit: (cit["inicio"] - cit["fim"], cit["inicio"]))
    saida: list[dict[str, Any]] = []
    for cit in ordenadas:
        if any(_iou(cit, outro) >= IOU_MIN for outro in saida):
            continue
        saida.append(cit)
    saida.sort(key=lambda cit: (cit["inicio"], cit["fim"]))
    return saida


def marcar(texto: str, tokenizer: Any, modelo: Any, dispositivo: str) -> list[dict[str, Any]]:
    import torch

    codificado = tokenizer(
        texto,
        return_offsets_mapping=True,
        return_overflowing_tokens=True,
        truncation=True,
        max_length=MAX_LEN,
        stride=STRIDE,
        padding=True,
        add_special_tokens=True,
        return_tensors="pt",
    )
    offsets = codificado.pop("offset_mapping")
    codificado.pop("overflow_to_sample_mapping", None)
    codificado = {chave: valor.to(dispositivo) for chave, valor in codificado.items()}
    with torch.no_grad():
        logits = modelo(**codificado).logits
    preditos = logits.argmax(dim=-1).cpu()
    id2label = {int(chave): valor for chave, valor in modelo.config.id2label.items()}
    spans: list[tuple[int, int, str]] = []
    for linha, mapa in zip(preditos, offsets, strict=True):
        rotulos = [id2label[int(indice)] for indice in linha.tolist()]
        pares = [(int(inicio), int(fim)) for inicio, fim in mapa.tolist()]
        spans.extend(_spans_da_janela(rotulos, pares))
    citacoes = []
    for inicio, fim, _rotulo in _juntar(texto, spans):
        trecho = texto[inicio:fim].strip()
        if len(trecho) < 3:
            continue
        ajuste = texto[inicio:fim].find(trecho)
        inicio_real = inicio + max(ajuste, 0)
        fim_real = inicio_real + len(trecho)
        citacoes.append(
            {
                "inicio": inicio_real,
                "fim": fim_real,
                "trecho": texto[inicio_real:fim_real],
                "tipo": tipo_de(texto[inicio_real:fim_real]),
                "classificacao": "incompleta",
                "confianca": None,
                "resolucao": None,
            }
        )
    return _preferir_longos(citacoes)


def _texto_e_spans(marcado: str) -> tuple[str, list[tuple[int, int, str]]]:
    partes: list[str] = []
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for match in _TAG.finditer(marcado):
        partes.append(marcado[cursor:match.start()])
        trecho = match.group(1)
        inicio = sum(len(parte) for parte in partes)
        partes.append(trecho)
        rotulo = "LEGISLACAO" if tipo_de(trecho) == "lei" else "JURISPRUDENCIA"
        spans.append((inicio, inicio + len(trecho), rotulo))
        cursor = match.end()
    partes.append(marcado[cursor:])
    return "".join(partes), spans


def _rotulos_da_janela(
    offsets: list[tuple[int, int]],
    spans: list[tuple[int, int, str]],
    label2id: dict[str, int],
) -> list[int]:
    rotulos: list[int] = []
    anterior: str | None = None
    for inicio, fim in offsets:
        if inicio == fim:
            rotulos.append(-100)
            anterior = None
            continue
        nome = None
        for s0, s1, rotulo in spans:
            if inicio < s1 and fim > s0:
                nome = rotulo
                break
        if nome is None:
            rotulos.append(label2id["O"])
            anterior = None
            continue
        chave = f"I-{nome}" if anterior == nome else f"B-{nome}"
        rotulos.append(label2id[chave])
        anterior = nome
    return rotulos


def _janelas(texto: str, spans: list[tuple[int, int, str]], tokenizer: Any) -> list[dict[str, list[int]]]:
    label2id = {nome: indice for indice, nome in enumerate(_LABELS)}
    codificado = tokenizer(
        texto,
        return_offsets_mapping=True,
        return_overflowing_tokens=True,
        truncation=True,
        max_length=MAX_LEN,
        stride=STRIDE,
        padding="max_length",
        add_special_tokens=True,
    )
    mapas = codificado["offset_mapping"]
    janelas = []
    for indice, mapa in enumerate(mapas):
        offsets = [(int(inicio), int(fim)) for inicio, fim in mapa]
        janelas.append(
            {
                "input_ids": list(codificado["input_ids"][indice]),
                "attention_mask": list(codificado["attention_mask"][indice]),
                "labels": _rotulos_da_janela(offsets, spans, label2id),
            }
        )
    return janelas


def prata_recente() -> Path:
    candidatos = sorted(RESULTS_DIR.glob("extract/*/prata.jsonl"))
    if not candidatos:
        raise SystemExit("prata.jsonl ausente")
    return candidatos[-1]


def treinar(jsonl: Path, saida: Path = ADAPTER_DIR) -> Path:
    import torch
    from torch.utils.data import Dataset
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    if not jsonl.is_file():
        raise SystemExit(f"jsonl ausente: {jsonl}")
    tokenizer = AutoTokenizer.from_pretrained(MODELO)
    itens: list[dict[str, list[int]]] = []
    documentos = 0
    for linha in jsonl.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        marcado = json.loads(linha)["messages"][-1]["content"]
        texto, spans = _texto_e_spans(marcado)
        itens.extend(_janelas(texto, spans, tokenizer))
        documentos += 1
    if not itens:
        raise SystemExit("nenhuma janela de treino")
    print(f"documentos={documentos} janelas={len(itens)}", flush=True)
    id2label = {indice: nome for indice, nome in enumerate(_LABELS)}
    label2id = {nome: indice for indice, nome in id2label.items()}
    modelo = AutoModelForTokenClassification.from_pretrained(
        MODELO,
        num_labels=len(_LABELS),
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    class Conjunto(Dataset):
        def __len__(self) -> int:
            return len(itens)

        def __getitem__(self, indice: int) -> dict[str, list[int]]:
            return itens[indice]

    def agrupar(lote: list[dict[str, list[int]]]) -> dict[str, torch.Tensor]:
        return {
            "input_ids": torch.tensor([item["input_ids"] for item in lote], dtype=torch.long),
            "attention_mask": torch.tensor([item["attention_mask"] for item in lote], dtype=torch.long),
            "labels": torch.tensor([item["labels"] for item in lote], dtype=torch.long),
        }

    saida.mkdir(parents=True, exist_ok=True)
    treinador = Trainer(
        model=modelo,
        args=TrainingArguments(
            output_dir=str(saida),
            num_train_epochs=EPOCHS,
            learning_rate=LR,
            per_device_train_batch_size=8,
            warmup_steps=10,
            weight_decay=0.01,
            logging_steps=5,
            save_strategy="no",
            bf16=torch.cuda.is_available(),
            report_to="none",
            remove_unused_columns=False,
        ),
        train_dataset=Conjunto(),
        data_collator=agrupar,
    )
    treinador.train()
    modelo.save_pretrained(saida)
    tokenizer.save_pretrained(saida)
    print(f"modelo salvo em {saida}", flush=True)
    return saida


def extrair_lener(txt_dir=TXT_DIR, modelo_dir: str | Path | None = None, documentos=None) -> list:
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    documentos = documentos if documentos is not None else carregar_documentos(txt_dir)
    if not documentos:
        raise SystemExit(f"nenhum documento em {txt_dir}")
    origem = str(modelo_dir or MODELO)
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"load {origem} device={dispositivo}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(origem)
    modelo = AutoModelForTokenClassification.from_pretrained(origem).to(dispositivo)
    modelo.eval()
    pasta = _pasta_run(EXTRACT_DIR, _carimbo(), model_slug(MODELO))
    for doc_id, texto in documentos:
        citacoes = marcar(texto, tokenizer, modelo, dispositivo)
        _escrever_json(
            pasta / f"{doc_id}.json",
            {"documento_id": doc_id, "citacoes": citacoes},
        )
        print(f"{doc_id} citacoes={len(citacoes)}", flush=True)
    _escrever_json(
        pasta / "meta.json",
        {
            "name": MODELO,
            "role": "lener",
            "family": "BERT",
            "parameters": "110M",
            "slug": model_slug(MODELO),
        },
    )
    print(f"extração salva em {pasta}", flush=True)
    return [pasta]


def avaliar_sem_treino(modelo_dir: Path) -> None:
    from train.__main__ import gold_sem, origens_treino

    bloqueados = origens_treino(ROOT / "data" / "train")
    documentos = [
        (doc_id, texto)
        for doc_id, texto in carregar_documentos(TXT_DIR)
        if doc_id not in bloqueados
    ]
    print(
        f"avaliação sem treino: excluidos={sorted(bloqueados)} restantes={len(documentos)}",
        flush=True,
    )
    gold = gold_sem(bloqueados, ROOT / "results" / "train" / "gold_heldout.csv")
    imprimir_avaliacao(
        buscar(extrair_lener(modelo_dir=modelo_dir, documentos=documentos), goldenset_path=gold)
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("etapa", nargs="?", choices=["extrair", "treinar"], default="extrair")
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--saida", type=Path, default=ADAPTER_DIR)
    args = parser.parse_args()
    if args.etapa == "treinar":
        destino = treinar(args.jsonl or prata_recente(), args.saida)
        avaliar_sem_treino(destino)
        return
    imprimir_avaliacao(buscar(extrair_lener()))


if __name__ == "__main__":
    main()
