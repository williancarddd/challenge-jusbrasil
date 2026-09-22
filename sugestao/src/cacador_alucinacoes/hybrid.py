"""União dos dois extratores, com o acordo entre eles virando confiança.

Os perfis são complementares e foram medidos nos 26 documentos:

    só regex   P=0,890  R=0,609
    só LLM     P=0,865  R=0,884
    união      P=0,816  R=0,924
    interseção P=1,000  R=0,569

A união é a escolha porque a assimetria do desafio favorece recall: citação não extraída
não chega à fase 2 e é perda definitiva, enquanto falso positivo ainda pode morrer lá,
quando a resolução contra a base não encontrar nada.

E a interseção não é descartada — vira o sinal de confiança. Os spans em que os dois
métodos concordam tiveram **precisão medida de 1,000** (128 de 128), o que é exatamente
o tipo de faixa bem calibrada que o bônus de calibração do contrato recompensa.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from cacador_alucinacoes.regex_extraction import RegexMatch
from cacador_alucinacoes.span_recovery import Found, intersection_over_union

# Qualquer sobreposição basta para considerar que os dois ramos viram a mesma citação.
# Medido: exigir IoU >= 0,5 fazia um span de regex parcialmente sobreposto virar predição
# separada — duas para a mesma citação, uma acertando e a outra virando falso positivo
# automático. Absorver derrubou os falsos positivos de borda de 7 para 1, sem mexer no
# recall (0,947) e sem diluir a faixa de acordo, que ficou em 0,993 com 149 spans em vez
# de 143. Limiares de 0,1 a 0,5 são degraus intermediários piores; nada existe entre
# "não se tocam" e "se tocam".
AGREEMENT_OVERLAP = 0.0

# Não é limiar nosso: é o da métrica oficial. `kaggle_metric._parse_submission_cell`
# levanta `ParticipantVisibleError` — e a submissão inteira é recusada, não é perda de
# pontos — quando duas predições do mesmo documento têm IoU >= 0,5. O valor é o mesmo do
# alinhamento contra o gabarito, e a coincidência não é acidente: IoU >= 0,5 *é* a
# definição de "mesma citação" no desafio, então duas predições nessa faixa são uma só.
DUPLICATE_IOU = 0.5


@dataclass(frozen=True)
class Citation:
    """Uma citação ao longo das duas fases.

    A **fase 1** preenche onde a citação está e como foi reconhecida. A **fase 2**
    preenche os quatro campos do contrato de submissão, todos derivados da resolução
    contra a base canônica:

    - `kind` (`tipo`): vem da coluna `tipo` do registro resolvido. Só as `real` resolvem,
      então as `inventada` e `incompleta` — 129 das 225 no gabarito — precisam do tipo
      inferido da forma da citação, sem registro para consultar.
    - `label` (`classificacao`): `real` com um feito, `inventada` com zero, `incompleta`
      com dois ou mais sem critério de desempate.
    - `canonical_id` (`resolucao.id_canonico`): obrigatório nas `real`, nulo no resto.
    - `confidence` (`confianca`): probabilidade de a classe — e o link, se `real` — estar
      correta. Alimenta o bônus de calibração de até 10%.

    `agreed` é sinal de fase 1 e entra como insumo da confiança de fase 2: nas 50
    execuções do estudo de variância, os ~7.400 spans concordantes acumulados tiveram
    precisão de 100,0%, com desvio zero.
    """

    # fase 1 — reconhecimento
    start: int
    end: int
    text: str
    from_llm: bool
    from_regex: bool
    # fase 2 — classificação e resolução
    kind: str | None = None
    label: str | None = None
    canonical_id: str | None = None
    confidence: float | None = None

    @property
    def agreed(self) -> bool:
        """Os dois métodos apontaram o mesmo span."""
        return self.from_llm and self.from_regex


def merge(llm: list[Found], regex: list[RegexMatch]) -> list[Citation]:
    """Une os dois conjuntos, marcando quem veio de onde.

    O span da LLM prevalece quando os dois concordam: ela erra a borda para mais, o
    regex para menos, e o alinhamento é por IoU >= 0,5 — mas as duas bordas passam no
    limiar quando há acordo, então a escolha é indiferente para o score e a da LLM
    preserva o prefixo recursal, que é a convenção do gabarito.

    O pareamento caminha as duas listas **por posição**, com dois ponteiros. Ambas já
    chegam ordenadas — o `filter_spans` do spaCy devolve por `start` e os blocos são
    percorridos em ordem —, então avançar sempre o que começa antes é suficiente e custa
    O(n+m). A versão anterior varria a lista inteira aceitando o primeiro acima do
    limiar, o que permitia parear um span com outro distante do texto.
    """
    left = sorted(llm, key=lambda c: (c.start, c.end))
    right = sorted(regex, key=lambda m: (m.start, m.end))
    citations: list[Citation] = []
    i = j = 0

    def from_llm_candidate(candidate, agreed: bool) -> Citation:
        return Citation(
            start=candidate.start,
            end=candidate.end,
            text=candidate.text,
            from_llm=True,
            from_regex=agreed,
        )

    def from_regex_match(match) -> Citation:
        # O `kind` do `RegexMatch` NÃO é propagado: ele diz apenas qual padrão casou,
        # não o que a citação é. O `tipo` do contrato sai da resolução da fase 2.
        return Citation(
            start=match.start,
            end=match.end,
            text=match.text,
            from_llm=False,
            from_regex=True,
        )

    while i < len(left) and j < len(right):
        candidate, other = left[i], right[j]
        overlap = intersection_over_union(
            (candidate.start, candidate.end), (other.start, other.end)
        )
        if overlap > AGREEMENT_OVERLAP:
            citations.append(from_llm_candidate(candidate, agreed=True))
            i += 1
            j += 1
        elif (candidate.start, candidate.end) <= (other.start, other.end):
            citations.append(from_llm_candidate(candidate, agreed=False))
            i += 1
        else:
            citations.append(from_regex_match(other))
            j += 1

    citations.extend(from_llm_candidate(c, agreed=False) for c in left[i:])
    citations.extend(from_regex_match(m) for m in right[j:])
    return _deduplicate(sorted(citations, key=lambda c: (c.start, c.end)))


def _deduplicate(citations: list[Citation]) -> list[Citation]:
    """Colapsa o que a métrica leria como a mesma citação predita duas vezes.

    O pareamento de `merge` caminha as duas listas com dois ponteiros e só compara LLM
    contra regex — nunca regex contra regex. Quando o regex casa dois padrões sobre o
    mesmo trecho (`Súmula 935\\ndo STF` e `entendimento a Súmula 935\\ndo STF`, no
    `gen_n2_001`), um deles pareia com o span da LLM e o outro sai sozinho. Medido: são
    duas predições com IoU 0,53, e é exatamente a condição que faz o servidor recusar a
    submissão inteira.

    Sobrevive a mais longa — convenção do gabarito, cujos trechos trazem a cadeia
    recursal completa, e a mesma regra que o `filter_spans` já aplica dentro do bloco.
    As origens são unidas: se os dois ramos viram a citação, o acordo se mantém.
    """
    kept: list[Citation] = []
    for citation in citations:
        twin = None
        for index, existing in enumerate(kept):
            overlap = intersection_over_union(
                (existing.start, existing.end), (citation.start, citation.end)
            )
            if overlap >= DUPLICATE_IOU:
                twin = index
                break
        if twin is None:
            kept.append(citation)
            continue
        existing = kept[twin]
        kept[twin] = replace(
            max(existing, citation, key=lambda c: c.end - c.start),
            from_llm=existing.from_llm or citation.from_llm,
            from_regex=existing.from_regex or citation.from_regex,
        )
    return sorted(kept, key=lambda c: (c.start, c.end))
