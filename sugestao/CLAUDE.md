# Diretrizes — Caça-Alucinações (BRACIS 2026)

Encontrar citações jurídicas em peças processuais e classificá-las em `real`,
`inventada` ou `incompleta`. **Fase 1** reconhece a citação e devolve o span;
**fase 2** classifica e resolve contra a base canônica. A fase 2 ainda não existe.

## A restrição dura: nunca alterar os spans

O gabarito cobre `inicio`/`fim` em **codepoints do arquivo cru**, alinhados por IoU ≥ 0,5.
Isso não proíbe transformar o texto — proíbe perder a posição. Toda transformação cai em
um de três grupos:

1. **1:1 em codepoint** — não muda comprimento, offsets preservados sem mapa. É o que
   `preprocessing.normalize` faz. Aplicar livremente.
2. **Muda comprimento** — só com mapa de offsets (índice normalizado → índice original).
   Nada disso existe hoje; se entrar, o mapa entra junto.
3. **Destrutiva sem mapa** — proibida.

`_guard_length` levanta `SpanShifted` quando uma normalização muda o tamanho. **Nunca
remover essa guarda para fazer um teste passar** — ela é a única coisa entre nós e um
offset silenciosamente errado.

Na **fase 2 a restrição não vale**: com o span já registrado, a string pode ser
canonizada à vontade para consultar a base.

## Convenções de código

- **Identificadores em inglês.** Funções, variáveis, classes, módulos, campos de
  dataclass, nomes de teste. Nunca `eh` no lugar de `é`.
- **Docstrings e comentários em português.**
- Nomes de coluna do gabarito e do contrato de submissão (`inicio`, `fim`, `trecho`,
  `tipo`, `classificacao`, `id_canonico`) ficam **confinados à fronteira** de leitura e
  serialização. Dentro do código são `start`, `end`, `excerpt`, `kind`, `label`,
  `canonical_id`.
- Comentário explica **por que**, não o que. Se um número aparece no código (um limiar,
  um índice), o comentário diz de qual medição ele saiu.

## Regras de método

**Os 26 documentos de `input/` são exemplos, não especificação.** A avaliação roda sobre
um conjunto cego semelhante que não recebemos. Toda forma enumerada a partir deles —
vocabulário de citação vaga, títulos de seção, variantes de ruído — é **evidência e caso
de teste**, nunca lista fechada a codificar.

**Regex complementa, não lidera.** Ele é o ramo determinístico do híbrido e é bom nisso:
medido, nunca inventa (100% dos seus falsos positivos são borda errada sobre citação
real). Mas quem carrega o recall é a LLM.

**Medir antes de concluir.** Várias hipóteses plausíveis desta base já se mostraram
erradas quando medidas — inclusive as minhas. Um número do log não é medição: o
`Maximum concurrency` do vLLM é estimativa de pior caso e não descreve o que acontece.

**Uma variável por vez.** Mudar duas coisas e ver o resultado piorar não diz qual delas
foi. Já custou uma investigação inteira nesta base.

## Arquitetura

```
input/*.txt → blocos ancorados → LLM (por bloco) → verificação → span por token.idx
                                      ↕ união
                                    regex
```

| módulo | papel |
|---|---|
| `preprocessing.py` | parte por `\n{2,}` guardando offset-base; normaliza 1:1; descarta preâmbulo |
| `extraction.py` | prompt, chamada ao vLLM, verificação da resposta |
| `regex_extraction.py` | ramo determinístico |
| `hybrid.py` | une os dois; o acordo entre eles vira confiança |
| `span_recovery.py` | `PhraseMatcher` + `token.idx` → offset absoluto |
| `evaluation.py` | uma execução completa medida contra o gabarito |

**A LLM devolve texto raw.** Trecho literal, sem corrigir OCR, sem expandir abreviação,
sem ajustar acento. Instrução de prompt não é mecanismo — `verify()` confere que a string
existe no bloco e separa o que a LLM reescreveu. Medido: quando a saída não é literal, o
modo de falha é sempre "não encontrado", nunca "encontrado no lugar errado", então a
verificação detecta 100% dos desvios.

**O `trecho` da submissão sai do arquivo cru pelo span** (`goldenset.literal_excerpt`),
nunca da resposta da LLM — 59 dos 225 trechos têm quebra de linha que a normalização
converteu em espaço.

## Testes

`uv run pytest` — segundos, não precisa do modelo no ar.

Os testes verificam **premissas do desenho**, não implementação. Quando um quebra, a
pergunta é se a decisão continua válida, não como fazer o teste passar. As invariantes:

- os 225 spans do gabarito reproduzem `trecho`
- nenhuma citação atravessa fronteira de bloco (o sentencizer do spaCy cortaria 41)
- nenhuma citação cai em bloco descartado
- o texto normalizado é 1:1 com a fatia original
- com entrada literal, a recuperação de span devolve 225/225 exatos

## Ambiente

```bash
uv sync
docker compose up -d llm          # vLLM + Qwen3-8B-FP8, pesos montados de models/
uv run pytest
uv run python scripts/evaluate_phase1.py
```

Pesos **fora da imagem**, montados como volume, com revisão HF fixa — exigência do
pacote de verificação. `WORKERS=1` serializa (reprodutível, ~53s/doc); o padrão é
`os.cpu_count() - 1`.

`--generation-config=vllm` é obrigatório: sem ele o vLLM adota o `generation_config.json`
do Qwen3 (`do_sample: true`, temperature 0.6) como default do servidor e a saída deixa de
ser reprodutível mesmo com `temperature=0` na requisição.

## Restrições do regulamento

Pesos abertos com link HF + revisão fixa, execução **offline** (container sem rede),
1 GPU 24 GB, 8 vCPUs, 32 GB RAM, média ≤ 60 s/documento, teto de 4 h. A re-execução das
top-N não admite queda maior que **5% relativo** no score — e a regra é assimétrica,
então reportar a melhor execução é a escolha mais arriscada.

## Ainda em aberto

Fase 2 inteira. A métrica oficial (`kaggle_metric.py`, prometida para 01/09) — tudo o que
medimos hoje usa o alinhamento do desafio com métrica própria por cima. E o
não-determinismo entre execuções, que a serialização resolve ao custo de tempo.
