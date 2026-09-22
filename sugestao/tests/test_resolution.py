"""Fase 2: normalização do número e as premissas do catálogo.

Não precisa do modelo no ar. O que toca a base fica marcado, porque `data/` não é
versionado e a suíte precisa passar sem ele.
"""

from __future__ import annotations

import pytest

from cacador_alucinacoes.goldenset import (
    literal_excerpt,
    load_documents,
    load_goldenset,
)
from cacador_alucinacoes.resolution import (
    DATABASE,
    STATUTE_CATALOGUE,
    SUMMARY_CATALOGUE,
    Resolver,
    number_phrase,
    query_text,
    restore_digits,
    restore_letters,
    small_number,
)

needs_database = pytest.mark.skipif(
    not DATABASE.exists(), reason="a base congelada não está em data/"
)


def test_ocr_restore_only_touches_digits_inside_the_number():
    """A condição posicional é o que separa conserto de estrago.

    Sem ela a troca come a UF e a sigla do tribunal: medido, a versão ingênua quebrava
    11 citações que já funcionavam para consertar 4.
    """
    assert restore_digits("21737l8") == "2173718"
    assert restore_digits("1.45g.779") == "1.459.779"
    assert restore_digits("1.528.4S5") == "1.528.455"
    assert restore_digits("170076O") == "1700760"

    # o que NÃO pode ser tocado
    assert restore_digits("1.708.000/SP") == "1.708.000/SP"
    assert restore_digits("TST-AgARR-25823") == "TST-AgARR-25823"
    assert restore_digits("REsp 1.234/SE") == "REsp 1.234/SE"


def test_cnj_is_segmented_from_the_right():
    """O rabo do CNJ tem 13 dígitos; o sequencial à esquerda varia de 3 a 7.

    Agrupar de três em três — o que a especificação sugere para número de STJ — produz a
    sequência de tokens errada para CNJ e a busca de frase devolve zero.
    """
    assert number_phrase("0600316-49.2020.6.16.0182") == "0600316 49 2020 6 16 0182"
    assert number_phrase("1099-66.2011.5.02.0251") == "1099 66 2011 5 02 0251"
    # sem separador nenhum, que é o ruído do nível 2
    assert number_phrase("0600316-4920206160182") == "0600316 49 2020 6 16 0182"


def test_number_grouped_in_threes_for_the_stj_form():
    assert number_phrase("REsp 1.741.784/PR") == "1 741 784"
    assert number_phrase("1.741. 784") == "1 741 784"


def test_a_year_is_not_a_case_number():
    """`Rcl de 2021, Rel. Min. Rosa Weber` é `incompleta` no gabarito.

    Sem esta guarda o ano vira a consulta, devolve um candidato por acidente e a citação
    sai classificada `real`. Medido: acontecia em 19 das 65 `incompleta`.
    """
    assert number_phrase("Rcl de 2021, Rel. Min. Rosa Weber") is None
    assert number_phrase("julgado do STF proferido em 2025") is None
    assert number_phrase("a jurisprudência pacífica desta Corte") is None


def test_catalogue_covers_every_record_that_search_cannot_reach():
    """As 18 entradas não são conveniência: a base não guarda a chave que as liga.

    Súmula não traz o próprio número em campo nenhum, e dispositivo não diz de qual
    código é. Se este teste quebrar porque a base mudou, a decisão de manter o catálogo
    precisa ser revista — não o teste.
    """
    assert len(SUMMARY_CATALOGUE) == 5
    assert len(STATUTE_CATALOGUE) == 13
    assert len(set(SUMMARY_CATALOGUE.values())) == 5
    assert len(set(STATUTE_CATALOGUE.values())) == 13


@needs_database
def test_invented_summary_does_not_resolve_to_the_only_court_record():
    """`Súmula 979 do STF` é `inventada` e precisa sair assim.

    Resolver súmula por tribunal acertaria as duas do STF e do TST e transformaria toda
    súmula inventada daquele tribunal em `real` — que é o erro grave, o que dispara τ.
    """
    resolver = Resolver()
    assert resolver.resolve("Súmula 979 do STF").label == "inventada"
    assert resolver.resolve("Súmula Vinculante 182").label == "inventada"
    assert resolver.resolve("Súmula 331 do TST").label == "real"


@needs_database
def test_invented_article_of_the_wrong_code_does_not_resolve():
    """`art 290 da Constituição Federal` é inventado, mas 290 existe — no CPM.

    Casar só pelo número resolveria para o registro errado e a citação sairia `real`.
    """
    resolver = Resolver()
    assert resolver.resolve("art 290 da Constituição Federal").label == "inventada"
    assert resolver.resolve("art. 290 do Código Penal Militar").label == "real"


def test_query_text_completes_a_number_the_span_cut():
    """A fase 1 devolveu `…RESP 21737` onde o documento traz `21737l8`.

    O span passa no IoU >= 0,5 e casa com o gabarito, mas o número truncado não resolve.
    Estender só o texto da consulta não move span nenhum — o `inicio`/`fim` submetido
    continua sendo o da fase 1.
    """
    document = "AgInt no RESP 21737l8 - SP, Rel. Min. Fulano"
    assert query_text(document, 0, len("AgInt no RESP 21737")) == "AgInt no RESP 21737l8"
    # sem número cortado, nada muda
    assert query_text(document, 0, 13) == "AgInt no RESP"


@needs_database
def test_the_number_alone_is_not_the_identity():
    """`Reclamação nº 22.357/PE` é `inventada`; `MS 22.357` existe e é outra classe.

    Sem a verificação de classe, os registros que citam o mandado de segurança viravam
    candidatos da reclamação e a citação saía `real` — o erro grave, que dispara τ.
    """
    resolver = Resolver()
    assert resolver.resolve("Reclamação nº 22.357/PE").label == "inventada"


@needs_database
def test_classification_over_the_goldenset_spans():
    """Piso medido da fase 2 sobre os spans do gabarito, isolado do recall da fase 1."""
    documents = load_documents()
    resolver = Resolver()
    correct = grave = 0
    for citation in load_goldenset():
        text = literal_excerpt(documents[citation.document_id], citation.start, citation.end)
        found = resolver.resolve(text)
        correct += found.label == citation.label
        grave += citation.label == "inventada" and found.label == "real"

    assert correct >= 224, f"a classificação caiu para {correct}/225"
    assert grave <= 1, f"{grave} alucinações vazaram como `real`"


def test_letter_restore_recovers_the_word_without_eating_the_number():
    """`5úmula` precisa virar `Súmula`, mas `art. 5º` não pode virar `art. Sº`."""
    assert restore_letters("5úmula 211 do STJ").startswith("Súmula")
    assert restore_letters("art. 5º, LV, da Constituição") == "art. 5º, LV, da Constituição"
    assert restore_letters("REsp 1.234/SP") == "REsp 1.234/SP"


def test_article_number_keeps_the_thousands_separator():
    """`art. 1.134` é o artigo 1134, não o artigo 1."""
    assert small_number("art. 1.134 da Lei nº 13.105/2015") == 1134
    assert small_number("art. 373, I, do CPC") == 373


@needs_database
def test_ocr_noise_does_not_cost_the_class():
    """Os três defeitos que o nível 2 expôs, cada um numa citação do gabarito."""
    resolver = Resolver()
    # dígito sósia comendo a palavra
    assert resolver.resolve("5úmula 211 do STJ").label == "real"
    # quebra de linha no meio do nome do código
    assert resolver.resolve("art 312 do Código\nde Processo Penal").label == "real"


@needs_database
def test_law_named_by_number_outside_the_coverage_is_invented():
    """Citar lei por número é consulta formulável — logo `inventada`, não `incompleta`.

    A diferença importa: `incompleta` é a classe de quem não consegue nem formular a
    busca, e trocar uma pela outra custa recall de uma classe e precisão da outra.
    """
    resolver = Resolver()
    assert resolver.resolve("art 189 da Lei nº 9.504/1997").label == "inventada"
    assert resolver.resolve("art 60 da Lei nº 13.467/2017").label == "inventada"
    # 13.105/2015 é o CPC, que está na cobertura — mas não tem artigo 1.134
    assert resolver.resolve("art. 1.134 da Lei nº 13.105/2015").label == "inventada"
    assert resolver.resolve("art. 373 da Lei nº 13.105/2015").label == "real"
