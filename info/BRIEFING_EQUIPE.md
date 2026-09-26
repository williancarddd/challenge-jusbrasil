# Briefing da Equipe — Desafio Caça-Alucinações (BRACIS 2026)

> Documento de onboarding. Leia antes de começar. 5 minutos.

## 1. O que estamos construindo (a ideia em uma frase)

Um sistema que lê um documento judicial e, para **cada citação** (lei ou
jurisprudência), decide se ela é:

| Classe | Significado | O que entregamos |
|---|---|---|
| **real** | O processo/lei existe na base de referência | O `id` do Jusbrasil |
| **inventada** | Dá pra buscar, mas **não existe** nada correspondente na base | nada (`null`) |
| **incompleta** | Não dá pra formular a busca, ou casa com processos demais | nada (`null`) |

É, na prática, um **detector de alucinação de citação jurídica**.

## 2. O fluxo, ponta a ponta

```
txt/gen_n1_001.txt   →   [NOSSO CÓDIGO]   →   JSON por documento   →   submission.csv
   (só o texto)          extrai + consulta       (uma linha/citação)     (json_to_submission.py)
```

- **Entra:** apenas o `.txt` do documento. Sem anotação, sem marcação.
- **Sai:** um JSON por documento — cada citação com `inicio`, `fim`, `trecho`,
  `tipo`, `classificacao` e, se `real`, `resolucao.id_canonico`.
- **Opcional:** `confianca` (0–1) → bônus de calibração de até 10%.

## 3. O que cada arquivo é (não confundir os papéis)

| Arquivo | Papel |
|---|---|
| `txt/*.txt` | **Entrada.** 26 documentos de exemplo. |
| `desafio1_bracis.db` | **Ferramenta de consulta.** 1.018 registros. É contra ele que uma citação é real ou inventada. **NÃO é dado de entrada.** |
| `goldenset.csv` | **Gabarito (ground truth) da amostra de dev.** 225 citações. Serve para medir/depurar nossa solução. |
| `json_to_submission.py` | Converte nossos JSONs no CSV de submissão. |
| `main.py` + `solucoes.py` | Orquestração e avaliação. `solucoes.REGISTRO` está vazio — o baseline de referência foi removido e precisa ser reimplementado. |

**Importante:** não há dataset de treinamento clássico. São só 225 exemplos —
a solução esperada é **regra + consulta ao banco**, não treinar um modelo do zero.

## 4. Os 3 passos técnicos (mapa de tarefas)

1. **Extrair spans** — localizar as citações no texto (`inicio`/`fim` em codepoints Unicode).
2. **Normalizar + consultar** — limpar o identificador e buscar na base via FTS.
   - Nível 2 traz ruído: `REsp`/`R.Esp.`, `1.741.784`/`1741784`, `/PR`/`- PR`/`(PR)`,
     OCR (`0↔O`, `5↔S`), quebras de linha. **Todo ruído é recuperável por normalização.**
3. **Contar feitos e classificar:**
   - exatamente **1 feito** → `real` (devolve o `id`)
   - **0** → `inventada`
   - **2+ feitos** sem desempate → `incompleta`

## 5. As 2 armadilhas que mais custam nota

1. **ID errado:** devolver `documento_id` (`doc_0201`) em vez da coluna `id`
   (`2566535283`). O `id_canonico` é SEMPRE a coluna `id` do Jusbrasil.
2. **Distratores do cabeçalho:** número dos autos do próprio documento, OAB,
   protocolo, `fls. 234/567`, valor da causa — **parecem citação e não são**.
   Extraí-los conta como falso positivo.

## 6. Como somos avaliados

- Alinhamento predição↔gabarito por **sobreposição de spans, IoU ≥ 0,5**.
- Não achou o span → não classifica → conta como erro de recall.
- **Nível 1 pesa 1×, Nível 2 pesa 2×.**
- O **dataset do ranking é cego**: não está com a gente. A organização roda o
  **nosso código** sobre ele ao fim da janela. Logo: o código precisa rodar
  sozinho, de ponta a ponta, sem ajustes manuais por documento.

## 7. Estado atual do baseline (referência a superar)

O baseline de referência (extração + normalização + `Resolvedor` de consulta
ao `.db`) foi removido do repositório e ainda não tem substituto. `python
main.py` roda sem erro, mas com `solucoes.REGISTRO` vazio não produz nenhuma
solução para avaliar. Os números abaixo são os últimos medidos com o baseline
removido, mantidos aqui só como referência histórica do patamar a reproduzir:

| nível | span-F1 | classe@match | id@real |
|---|---|---|---|
| 1 | 0.804 | 0.881 | 0.794 |
| 2 | 0.600 | 0.804 | 0.632 |

Nota ponderada (F1×classe, N2=2×): **0.558**. Gargalo conhecido: recall de span
no nível 2 (o ruído derruba o regex antes da normalização agir).

## 8. Divisão sugerida de trabalho

| Frente | Responsável | Entregável |
|---|---|---|
| Extração de spans + filtro de distratores | | função `extrair(texto) -> [spans]` |
| Normalização de identificadores (nível 2) | | função `normalizar(str) -> forma canônica` |
| Consulta à base + agrupamento por feito | | função `resolver(num, tribunal) -> id \| None` |
| Leis/súmulas (18 registros, casar por texto) | | dicionário em memória |
| Avaliação local contra o goldenset (IoU) | | `main.py` (já reporta nota por nível) |
