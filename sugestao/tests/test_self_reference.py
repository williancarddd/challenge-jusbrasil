"""O descarte de autorreferência, e a invariante que o torna seguro."""

from __future__ import annotations

import pytest

from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.self_reference import is_self_reference


@pytest.fixture(scope="module")
def documents():
    return load_documents()


def test_it_never_touches_a_citation_of_the_goldenset(documents):
    """A invariante que autoriza o filtro: **zero** das 225 é derrubada.

    Um filtro de precisão que come recall é troca ruim aqui — span não extraído é perda
    definitiva, e o falso positivo custa só precisão de uma classe. Se este teste
    quebrar, o filtro perdeu o direito de existir na forma atual.
    """
    killed = [
        citation
        for citation in load_goldenset()
        if is_self_reference(
            documents[citation.document_id], citation.start, citation.end
        )
    ]
    assert not killed, [(c.document_id, c.excerpt) for c in killed]


@pytest.mark.parametrize(
    "before, span",
    [
        ("vem, respeitosamente, à presença de Vossa Excelência interpor o presente ", "AGRAVO INTERNO"),
        ("inconformada com a decisão que indeferiu a ordem, vem interpor o presente ", "AGRAVO REGIMENTAL"),
        ("DECISÃO MONOCRÁTICA Cuida-se de ", "apelação interposta em face de sentença"),
        ("A defesa do apelante, inconformada com a ", "r. sentença proferida pelo Conselho"),
        ("não se conformando com o acórdão proferido pelo ", "Tribunal Regional Eleitoral DO RIO GRANDE DO SUL"),
    ],
)
def test_the_introducing_clause_marks_the_document_itself(before, span):
    """O marcador está **antes** do span — por isso a janela, e não só o trecho."""
    document = f"{before}{span} e segue o texto."
    assert is_self_reference(document, len(before), len(before) + len(span))


@pytest.mark.parametrize(
    "span",
    ["acórdão recorrido", "autos em referência", "a decisão combatida"],
)
def test_the_expression_says_it_of_itself(span):
    document = f"o raciocínio desenvolvido no {span} parte de premissa equivocada"
    start = document.index(span)
    assert is_self_reference(document, start, start + len(span))


@pytest.mark.parametrize(
    "before, span",
    [
        ("Ao apreciar os ", "Embargos de Declaração no Agravo Interno no AREsp 1.234/SP"),
        ("Milita em favor da parte a ", "Rcl de 2022, Rel. Min. Alexandre De Moraes"),
        ("Ampara a pretensão a ", "orientação jurisprudencial da Corte"),
        ("Nos termos do ", "art. 5º, LV, da Constituição Federal"),
    ],
)
def test_a_real_citation_survives(before, span):
    document = f"{before}{span}, que bem ilustra a matéria."
    assert not is_self_reference(document, len(before), len(before) + len(span))
