"""A verificação da saída da LLM — a rede que torna o desvio visível.

Não precisa do modelo no ar: o que se testa aqui é a fronteira entre o que ele devolveu
e o que existe no texto.
"""

from __future__ import annotations

import json

from cacador_alucinacoes.extraction import (
    RESPONSE_SCHEMA,
    Candidate,
    build_request,
    parse_response,
    verify,
)
from cacador_alucinacoes.goldenset import load_documents
from cacador_alucinacoes.preprocessing import usable_blocks


def first_block_with(text: str):
    document = load_documents()["gen_n2_002"]
    return next(b for b in usable_blocks(document) if text in b.text)


def test_verify_separates_literal_from_rewritten():
    """`Súmula 211` é o conserto que o texto ruidoso `5úmula 211` provoca."""
    block = first_block_with("5úmula 211 do STJ")
    literal = Candidate(text="5úmula 211 do STJ", confidence=0.9)
    corrected = Candidate(text="Súmula 211 do STJ", confidence=0.9)

    result = verify(block, [literal, corrected])

    assert result.verified == [literal]
    assert result.hallucinated == [corrected]
    assert result.transcription_failures == 1


def test_verify_rejects_a_candidate_that_is_the_whole_block():
    """Nenhuma das 225 citações ocupa um bloco inteiro — nem 80% dele.

    Quando a LLM devolve o bloco todo, ela marcou um título de seção ou o fecho da
    peça. Rejeitar isso levou a precisão de 63,5% para 83,0% sem custar recall.
    """
    document = load_documents()["gen_n1_002"]
    heading = next(
        b for b in usable_blocks(document) if b.text.strip() == "II - DO DIREITO APLICÁVEL"
    )
    candidate = Candidate(text="II - DO DIREITO APLICÁVEL", confidence=0.8)

    result = verify(heading, [candidate])

    assert result.verified == []
    assert result.whole_block == [candidate]
    assert result.hallucinated == []


def test_verify_keeps_the_deviation_instead_of_dropping_it():
    """Falha de transcrição é informação, não lixo — some do resultado, não do registro."""
    block = first_block_with("5úmula")
    invented = Candidate(text="REsp nº 9.999.999/ZZ", confidence=1.0)

    result = verify(block, [invented])

    assert result.verified == []
    assert result.hallucinated == [invented]


def test_request_carries_the_grammar_by_default():
    block = first_block_with("5úmula")
    payload = build_request(block)

    assert payload["temperature"] == 0.0
    assert payload["response_format"]["json_schema"]["schema"] == RESPONSE_SCHEMA
    assert payload["messages"][-1]["content"] == block.text


def test_request_without_grammar_for_ablation():
    block = first_block_with("5úmula")
    assert "response_format" not in build_request(block, constrained=False)


def test_parse_response_reads_the_tuples():
    body = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "citations": [
                                {"text": "Súmula 7 do STJ", "confidence": 0.93},
                                {"text": "art. 373, I, do CPC", "confidence": 0.71},
                            ]
                        }
                    )
                }
            }
        ]
    }
    candidates = parse_response(body)
    assert [c.text for c in candidates] == ["Súmula 7 do STJ", "art. 373, I, do CPC"]
    assert candidates[0].confidence == 0.93


def test_parse_response_handles_empty_block():
    body = {"choices": [{"message": {"content": '{"citations": []}'}}]}
    assert parse_response(body) == []
