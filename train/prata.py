from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from challenge_jusbrasil.chunker import Chunker
from challenge_jusbrasil.pipeline import carregar_documentos, citacoes_de_saida, extrair
from challenge_jusbrasil.settings import (
    CHUNK_OVERLAP,
    GOLDENSET_PATH,
    ROOT,
    chat_prompt,
    orcamento_texto,
    teacher_model,
)

PRATA_DIR = ROOT / "results" / "train"


def ids_avaliacao(goldenset_path: Path = GOLDENSET_PATH) -> set[str]:
    if not goldenset_path.is_file():
        return set()
    with goldenset_path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["documento_id"] for row in csv.DictReader(handle)}


def spans_validos(texto: str, citacoes: list[dict[str, Any]]) -> list[tuple[int, int]]:
    saida: list[tuple[int, int]] = []
    cursor = 0
    for cit in sorted(citacoes, key=lambda item: (int(item["inicio"]), int(item["fim"]))):
        inicio = int(cit["inicio"])
        fim = int(cit["fim"])
        if inicio < cursor or fim > len(texto) or inicio >= fim:
            continue
        saida.append((inicio, fim))
        cursor = fim
    return saida


def marcar(texto: str, spans: list[tuple[int, int]]) -> str:
    partes: list[str] = []
    cursor = 0
    for inicio, fim in spans:
        partes.append(texto[cursor:inicio])
        partes.append("<start>")
        partes.append(texto[inicio:fim])
        partes.append("<end>")
        cursor = fim
    partes.append(texto[cursor:])
    return "".join(partes)


def janela_aceita(texto: str, citacoes: list[dict[str, Any]]) -> str | None:
    spans = spans_validos(texto, citacoes)
    marcado = marcar(texto, spans)
    recuperadas = citacoes_de_saida(texto, marcado)
    if [(cit["inicio"], cit["fim"]) for cit in recuperadas] != spans:
        return None
    return marcado


def exemplos_de_extracao(
    pasta: Path,
    documentos: list[tuple[str, str]],
    modelo: dict[str, Any],
) -> list[dict[str, Any]]:
    chunker = Chunker(orcamento_texto(modelo), CHUNK_OVERLAP)
    exemplos: list[dict[str, Any]] = []
    descartadas = 0
    for doc_id, texto in documentos:
        payload = json.loads((pasta / f"{doc_id}.json").read_text(encoding="utf-8"))
        citacoes = payload.get("citacoes") or []
        for janela in chunker.janelas(texto):
            fim = janela.start + len(janela.text)
            locais = []
            for cit in citacoes:
                inicio = int(cit["inicio"])
                termino = int(cit["fim"])
                if inicio >= janela.start and termino <= fim:
                    locais.append(
                        {
                            "inicio": inicio - janela.start,
                            "fim": termino - janela.start,
                        }
                    )
            marcado = janela_aceita(janela.text, locais)
            if marcado is None:
                descartadas += 1
                continue
            exemplos.append(
                {
                    "documento_id": doc_id,
                    "inicio": janela.start,
                    "messages": [
                        *chat_prompt(doc_id, janela.text),
                        {"role": "assistant", "content": marcado},
                    ],
                }
            )
    print(f"janelas aceitas={len(exemplos)} descartadas={descartadas}", flush=True)
    return exemplos


def gerar_prata(txt_dir: Path, goldenset_path: Path = GOLDENSET_PATH) -> Path:
    if not txt_dir.is_dir():
        raise SystemExit(f"pasta de treino ausente: {txt_dir}")
    bloqueados = ids_avaliacao(goldenset_path)
    documentos = [
        (doc_id, texto)
        for doc_id, texto in carregar_documentos(txt_dir)
        if doc_id not in bloqueados
    ]
    pulados = len(carregar_documentos(txt_dir)) - len(documentos)
    if pulados:
        print(f"documentos da avaliação deixados de fora: {pulados}", flush=True)
    if not documentos:
        raise SystemExit(f"nenhum documento de treino em {txt_dir}")
    professor = teacher_model()
    pastas = extrair([professor], txt_dir=txt_dir, documentos=documentos)
    pasta = pastas[0]
    exemplos = exemplos_de_extracao(pasta, documentos, professor)
    if not exemplos:
        raise SystemExit(f"nenhuma janela aceita em {pasta}")
    destino = pasta / "prata.jsonl"
    with destino.open("w", encoding="utf-8") as handle:
        for exemplo in exemplos:
            handle.write(json.dumps(exemplo, ensure_ascii=False) + "\n")
    print(f"prata salva em {destino}", flush=True)
    return destino
