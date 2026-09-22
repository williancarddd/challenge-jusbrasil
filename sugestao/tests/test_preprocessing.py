"""Invariantes do pré-processamento, medidas contra o gabarito.

Estes testes não conferem que o código faz o que o código faz — conferem que as
premissas do desenho continuam verdadeiras. Se alguma quebrar, é sinal de que uma
decisão precisa ser revista, não de que um detalhe precisa de ajuste.
"""

from __future__ import annotations

import unicodedata

import pytest

from cacador_alucinacoes.goldenset import (
    literal_excerpt,
    load_documents,
    load_goldenset,
)
from cacador_alucinacoes.preprocessing import (
    SpanShifted,
    blocks,
    normalize,
    strip_accents,
    usable_blocks,
)

TOTAL_CITATIONS = 225
TOTAL_DOCUMENTS = 26


@pytest.fixture(scope="module")
def goldenset():
    return load_goldenset()


@pytest.fixture(scope="module")
def documents():
    return load_documents()


def test_goldenset_is_complete(goldenset, documents):
    assert len(goldenset) == TOTAL_CITATIONS
    assert len(documents) == TOTAL_DOCUMENTS
    assert sum(1 for c in goldenset if c.label == "real") == 96
    assert all(c.canonical_id for c in goldenset if c.label == "real")
    assert not any(c.canonical_id for c in goldenset if c.label != "real")


def test_span_reproduces_the_excerpt(goldenset, documents):
    """`texto[inicio:fim]` bate com `trecho` nas 225 linhas.

    O gabarito escapa a quebra de linha como os dois caracteres `\\n`.
    """
    for citation in goldenset:
        literal = literal_excerpt(
            documents[citation.document_id], citation.start, citation.end
        )
        assert literal.replace("\n", "\\n") == citation.excerpt, citation.citation_id


def test_no_citation_crosses_a_block(goldenset, documents):
    """A escolha do parágrafo como unidade depende disso.

    O sentencizer do spaCy corta 41 das 225; o bloco corta zero. Uma citação partida
    não é recuperável por nenhuma das metades e vira erro de recall.
    """
    orphans = []
    for citation in goldenset:
        spans = blocks(documents[citation.document_id])
        fits = any(b.start <= citation.start and citation.end <= b.end for b in spans)
        if not fits:
            orphans.append(citation.citation_id)
    assert orphans == []


def test_preamble_discard_never_eats_a_citation(goldenset, documents):
    """A invariante que protege o recall: nada descartado pode conter citação."""
    lost = []
    for citation in goldenset:
        for block in blocks(documents[citation.document_id]):
            if block.discarded and block.start <= citation.start < block.end:
                lost.append((citation.document_id, citation.citation_id))
    assert lost == []


def test_discards_both_preamble_blocks(documents):
    """52 de 52 — os dois primeiros blocos dos 26 documentos."""
    discarded = sum(
        1 for doc in documents.values() for b in blocks(doc) if b.discarded
    )
    assert discarded == 2 * TOTAL_DOCUMENTS


def test_predicate_never_runs_outside_the_preamble(documents):
    """Descarte é conjunção de posição e assinatura.

    A assinatura solta dispararia em 186 dos 412 blocos. Nenhum bloco de índice 2+
    pode ser descartado, por mais que pareça preâmbulo.
    """
    for doc in documents.values():
        for block in blocks(doc):
            if block.index >= 2:
                assert not block.discarded


def test_offsets_survive_normalization(documents):
    """A invariante central: o texto normalizado é 1:1 com a fatia original."""
    for doc in documents.values():
        for block in blocks(doc):
            assert len(block.text) == block.end - block.start
            assert block.absolute_position(0) == block.start


def test_normalization_preserves_length(documents):
    for doc in documents.values():
        assert len(normalize(doc)) == len(doc)
        assert len(strip_accents(doc)) == len(doc)


def test_guard_catches_length_changing_transformation():
    """Qualquer normalização que mude o comprimento tem que falhar alto.

    `normalize` é 1:1 por construção, então quem exercita a guarda é uma normalização
    plugada de fora. Os dois casos aqui são os que o conjunto cego pode trazer: NFKC
    expandindo ligadura (`ﬁ` -> `fi`) e uma transformação que remove caracteres.
    """

    def with_nfkc(text: str) -> str:
        return unicodedata.normalize("NFKC", text)

    with pytest.raises(SpanShifted):
        blocks("TÍTULO\n\nO ﬁm do processo.", normalization=with_nfkc)

    def destructive(text: str) -> str:
        return text.replace(".", "")

    with pytest.raises(SpanShifted):
        blocks("AUTOS Nº 1.234\n\nCorpo.", normalization=destructive)


def test_nfkc_would_not_change_length_in_these_26(documents):
    """Medição, não garantia: aqui NFKC é 1:1 (só `º`->`o` e NBSP->espaço).

    É por acaso do conteúdo, não propriedade da técnica — por isso a guarda existe.
    """
    for doc in documents.values():
        assert len(unicodedata.normalize("NFKC", doc)) == len(doc)


def test_usable_blocks_exclude_the_preamble(documents):
    doc = documents["gen_n1_001"]
    assert [b.index for b in usable_blocks(doc)][:1] == [2]
