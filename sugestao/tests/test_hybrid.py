"""O ramo determinístico e a fusão dos dois extratores.

Não precisa do modelo no ar: o regex roda local e a fusão é testada com candidatos
sintéticos no lugar da saída da LLM.
"""

from __future__ import annotations

import pytest

from cacador_alucinacoes.goldenset import load_documents, load_goldenset
from cacador_alucinacoes.hybrid import merge
from cacador_alucinacoes.preprocessing import usable_blocks
from cacador_alucinacoes.regex_extraction import RegexMatch, find
from cacador_alucinacoes.span_recovery import Found, intersection_over_union


@pytest.fixture(scope="module")
def documents():
    return load_documents()


def test_regex_never_matches_inside_the_preamble(documents):
    """O descarte de blocos substitui o filtro de cabeçalho por posição.

    O número dos autos e o valor da causa vivem no preâmbulo; se o regex os alcançasse,
    entrariam como falso positivo garantido.
    """
    for document in documents.values():
        windows = [(b.start, b.end) for b in usable_blocks(document)]
        for match in find(document):
            assert any(
                low <= match.start and match.end <= high for low, high in windows
            ), match.text


def test_regex_alone_favours_precision_over_recall(documents):
    """O perfil que justifica o híbrido: o regex erra por omissão, não por invenção."""
    goldenset = load_goldenset()
    expected = {}
    for citation in goldenset:
        expected.setdefault(citation.document_id, []).append(citation)

    hits = predictions = 0
    for document_id, document in documents.items():
        matches = find(document)
        predictions += len(matches)
        used = set()
        for citation in expected[document_id]:
            for index, match in enumerate(matches):
                if index in used:
                    continue
                if (
                    intersection_over_union(
                        (match.start, match.end), (citation.start, citation.end)
                    )
                    >= 0.5
                ):
                    used.add(index)
                    hits += 1
                    break

    precision = hits / predictions
    recall = hits / len(goldenset)
    assert precision > recall, "o regex deixou de ser o ramo preciso"
    assert precision >= 0.85
    assert recall >= 0.55


def test_merge_marks_agreement_and_keeps_the_llm_span():
    """Quando os dois apontam o mesmo trecho, a borda da LLM prevalece.

    Ela preserva o prefixo recursal, que é a convenção do gabarito.
    """
    llm = [Found(start=10, end=40, text="AgRg no REsp 1.234/SP", block_index=3)]
    regex = [RegexMatch(start=18, end=40, text="REsp 1.234/SP", kind="jurisprudencia")]

    merged = merge(llm, regex)

    assert len(merged) == 1
    assert merged[0].agreed
    assert (merged[0].start, merged[0].end) == (10, 40)


def test_merge_keeps_what_only_one_side_found():
    llm = [Found(start=0, end=20, text="Súmula 7 do STJ", block_index=2)]
    regex = [RegexMatch(start=90, end=110, text="art. 5º da CF", kind="lei")]

    merged = merge(llm, regex)

    assert [c.agreed for c in merged] == [False, False]
    assert [(c.from_llm, c.from_regex) for c in merged] == [(True, False), (False, True)]
    assert merged[0].start < merged[1].start


def test_phase_two_fields_start_empty():
    """`tipo`, `classificacao`, `id_canonico` e `confianca` são preenchidos na fase 2.

    A fase 1 não os adivinha: o `kind` do `RegexMatch` diz qual padrão casou, não o que
    a citação é, e propagá-lo seria confundir uma coisa com a outra.
    """
    agreed = merge(
        [Found(start=0, end=10, text="REsp 1/SP", block_index=1)],
        [RegexMatch(start=0, end=10, text="REsp 1/SP", kind="jurisprudencia")],
    )[0]
    solo = merge([Found(start=0, end=10, text="REsp 1/SP", block_index=1)], [])[0]

    for citation in (agreed, solo):
        assert citation.kind is None
        assert citation.label is None
        assert citation.canonical_id is None
        assert citation.confidence is None

    # O sinal de reconhecimento continua disponível como insumo da fase 2.
    assert agreed.agreed and not solo.agreed


def test_merge_never_emits_what_the_metric_calls_duplicate():
    """Duas predições com IoU >= 0,5 fazem o servidor recusar a submissão inteira.

    A forma reproduzida é a que quebrou no `gen_n2_001`: o regex casa dois padrões sobre
    o mesmo trecho, um deles pareia com o span da LLM e o outro sairia sozinho. O
    pareamento de `merge` compara LLM contra regex e nunca regex contra regex, então sem
    a deduplicação as duas predições chegam ao CSV.
    """
    llm = [Found(start=20, end=37, text="Súmula 935 do STF", block_index=5)]
    regex = [
        RegexMatch(
            start=3, end=37, text="entendimento a Súmula 935\ndo STF", kind="jurisprudencia"
        ),
        RegexMatch(start=20, end=37, text="Súmula 935\ndo STF", kind="jurisprudencia"),
    ]

    merged = merge(llm, regex)

    for first in range(len(merged)):
        for second in range(first + 1, len(merged)):
            assert (
                intersection_over_union(
                    (merged[first].start, merged[first].end),
                    (merged[second].start, merged[second].end),
                )
                < 0.5
            ), "a métrica rejeitaria esta submissão como duplicata"


def test_deduplication_keeps_the_longest_span():
    """Convenção do gabarito: o trecho traz a cadeia recursal inteira."""
    merged = merge(
        [],
        [
            RegexMatch(start=10, end=40, text="AgRg no REsp 1.234/SP", kind="jurisprudencia"),
            RegexMatch(start=18, end=40, text="REsp 1.234/SP", kind="jurisprudencia"),
        ],
    )

    assert len(merged) == 1
    assert (merged[0].start, merged[0].end) == (10, 40)


def test_ocr_confusions_are_a_closed_set_and_the_spellings_are_not():
    """A distinção que autoriza codificar isto.

    O vocabulário de citação vaga é aberto — não há como enumerar os modos de referir
    jurisprudência sem número. Já o ruído é substituição de caractere sobre um alfabeto
    finito, publicado na especificação e gerado pelo mesmo processo no conjunto cego.

    Então o que entra no código é a **confusão**, não a grafia: `entendirnento` e
    `profcrido` não aparecem como literais em lugar nenhum, e mesmo assim casam.
    """
    from cacador_alucinacoes.regex_extraction import VAGUE_CASE_LAW, noisy

    assert noisy("me") == "(?:m|rn)(?:e|c)"

    for text in (
        "entendimento sumulado sobre a matéria",
        "entendirnento sumulado sobre a matéria",
        "julgado do STJ proferido em 2023",
        "julgado do STJ profcrido em 2023",
    ):
        assert VAGUE_CASE_LAW.search(text), text
