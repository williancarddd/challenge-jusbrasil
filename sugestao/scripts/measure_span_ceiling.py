"""Mede o teto da fase 1: com string perfeita, a recuperação de span funciona?

Simula uma LLM ideal — que devolve exatamente o trecho do gabarito, já normalizado como
ela o teria visto — e verifica se a camada de casamento reconstrói os 225 spans. Um
fracasso aqui é problema do casamento, não do modelo, e é muito mais barato de descobrir
agora do que confundido com erro de reconhecimento depois.

Roda dois cenários:

- **realista**: todos os candidatos do documento de uma vez, varrendo todos os blocos
  úteis, sem saber de qual bloco cada citação veio;
- **perturbado**: a LLM "consertando" o texto em vez de copiá-lo, para dimensionar o
  custo de o requisito de texto raw ser violado.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.preprocessing import blocks, normalize, usable_blocks
from cacador_alucinacoes.span_recovery import (
    intersection_over_union,
    locate,
    portuguese_tokenizer,
)

IOU_THRESHOLD = 0.5


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text)


def fix_obvious_ocr(text: str) -> str:
    """O conserto que um modelo de instrução faz sem ser pedido."""
    text = re.sub(r"\b5(?=[úùu][mn])", "S", text)  # 5úmula -> Súmula
    return text.replace("rn", "m")  # entendirnento -> entendimento


def evaluate(label: str, perturbation=None) -> None:
    goldenset = load_goldenset()
    documents = load_documents()
    nlp = portuguese_tokenizer()

    by_document = defaultdict(list)
    for citation in goldenset:
        by_document[citation.document_id].append(citation)

    exact = aligned = 0
    unmatched: list[tuple[str, str, str]] = []
    misplaced: list[tuple[str, str, float]] = []
    spurious = 0

    for document_id, citations in by_document.items():
        document = documents[document_id]
        candidate_of = {}
        for citation in citations:
            # A LLM leu o texto normalizado, então o "texto raw" que ela devolveria é a
            # fatia normalizada — não a fatia crua do arquivo.
            text = normalize(document[citation.start : citation.end])
            candidate_of[citation.citation_id] = (
                perturbation(text) if perturbation else text
            )

        # Cenário realista: nenhuma pista de qual bloco contém o quê.
        located: list = []
        still_missing = set(candidate_of.values())
        for block in usable_blocks(document):
            found, _ = locate(block, sorted(set(candidate_of.values())), nlp)
            located.extend(found)
            still_missing -= {f.text for f in found}

        spurious += max(0, len(located) - len(citations))

        for citation in citations:
            wanted = candidate_of[citation.citation_id]
            hits = [f for f in located if f.text == wanted]
            if not hits:
                unmatched.append((document_id, citation.citation_id, wanted))
                continue
            best = max(
                hits,
                key=lambda f: intersection_over_union(
                    (f.start, f.end), (citation.start, citation.end)
                ),
            )
            score = intersection_over_union(
                (best.start, best.end), (citation.start, citation.end)
            )
            if (best.start, best.end) == (citation.start, citation.end):
                exact += 1
            if score >= IOU_THRESHOLD:
                aligned += 1
            else:
                misplaced.append((document_id, citation.citation_id, score))

    total = len(goldenset)
    print(f"\n=== {label}")
    print(f"span idêntico ao esperado:  {exact}/{total}  ({100 * exact / total:.1f}%)")
    print(f"alinhado no IoU >= 0,5:     {aligned}/{total}  ({100 * aligned / total:.1f}%)")
    print(f"não encontrado:             {len(unmatched)}")
    print(f"deslocado:                  {len(misplaced)}")
    print(f"casamentos a mais que o esperado: {spurious}")
    for document_id, citation_id, text in unmatched[:6]:
        print(f"     perdido {document_id} {citation_id}: {text!r}")


def main() -> None:
    evaluate("LLM ideal — devolve o texto raw")
    evaluate("LLM tirando acento", strip_accents)
    evaluate("LLM colapsando espaço múltiplo", collapse_spaces)
    evaluate("LLM consertando OCR óbvio", fix_obvious_ocr)


if __name__ == "__main__":
    main()
