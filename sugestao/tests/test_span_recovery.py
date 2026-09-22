"""O teto da fase 1, travado como regressão.

Se a LLM devolver o texto raw, a recuperação de span tem que ser perfeita. Qualquer
queda aqui é defeito da camada de casamento, não do modelo — e a distinção importa,
porque erro de reconhecimento e erro de coordenada se confundem no score final.
"""

from __future__ import annotations

from collections import defaultdict

import pytest

from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.preprocessing import normalize, usable_blocks
from cacador_alucinacoes.span_recovery import (
    intersection_over_union,
    locate,
    portuguese_tokenizer,
)


@pytest.fixture(scope="module")
def nlp():
    return portuguese_tokenizer()


@pytest.fixture(scope="module")
def corpus():
    goldenset = load_goldenset()
    documents = load_documents()
    grouped = defaultdict(list)
    for citation in goldenset:
        grouped[citation.document_id].append(citation)
    return documents, grouped


def test_perfect_input_recovers_every_span(corpus, nlp):
    """225/225 exatos, sem oráculo de qual bloco contém o quê.

    Todos os candidatos do documento vão juntos, varrendo todos os blocos úteis — que é
    como vai ser em produção.
    """
    documents, grouped = corpus
    recovered = 0

    for document_id, citations in grouped.items():
        document = documents[document_id]
        wanted = {
            citation.citation_id: normalize(document[citation.start : citation.end])
            for citation in citations
        }

        located = []
        for block in usable_blocks(document):
            found, _ = locate(block, sorted(set(wanted.values())), nlp)
            located.extend(found)

        for citation in citations:
            hits = [f for f in located if f.text == wanted[citation.citation_id]]
            assert hits, f"{document_id} {citation.citation_id} não encontrado"
            if any(
                (f.start, f.end) == (citation.start, citation.end) for f in hits
            ):
                recovered += 1

    assert recovered == 225


def test_failure_mode_is_always_absence_never_wrong_position(corpus, nlp):
    """Um candidato que não existe no texto não pode casar em lugar nenhum.

    É o que garante que a verificação (a string devolvida está no bloco?) detecte toda
    falha de transcrição. Span errado em silêncio seria muito pior que citação perdida.
    """
    documents, grouped = corpus
    document_id = "gen_n1_001"
    document = documents[document_id]
    invented = ["REsp nº 9.999.999/ZZ", "Súmula 4321 do STF"]

    for block in usable_blocks(document):
        found, missing = locate(block, invented, nlp)
        assert found == []
        assert set(missing) == set(invented)


def test_iou_threshold_arithmetic():
    assert intersection_over_union((0, 30), (0, 30)) == 1.0
    assert intersection_over_union((0, 10), (20, 30)) == 0.0
    # Forma curta contra o gold com a cadeia recursal na frente: sobrevive ao limiar.
    assert intersection_over_union((9, 30), (0, 30)) >= 0.5
