# Baseline — Regra completa (determinístico)

Pipeline de referência do enunciado: **extrair → normalizar → consultar → contar
feitos**. Sem treino, sem modelo — só regex + SQLite FTS + regra de cardinalidade.

## Estrutura

| Módulo | Passo | O que faz |
|---|---|---|
| `extrair.py` | 1 | Regex acha spans (juris com nº, súmula, dispositivo, formas vagas); filtra distratores do cabeçalho. |
| `normalizar.py` | 2 | Reconstrói a forma canônica do identificador (dígitos de 3 em 3, CNJ, OCR seguro). |
| `resolver.py` | 3 | Consulta `documentos_fts` por frase, separa "é o processo" de "só cita" (posição ≤120), conta feitos → classe. |

A orquestração (`texto → JSON`) e a avaliação por IoU ≥ 0,5 ficam no
`main.py` da raiz do projeto, junto do registro de soluções (`solucoes.py`).

## Como rodar

```bash
python main.py        # a partir da raiz do projeto
```

## Resultado atual (amostra de desenvolvimento, 26 docs)

| nível | span-P | span-R | span-F1 | classe@match | id@real |
|---|---|---|---|---|---|
| 1 | 0.903 | 0.724 | **0.804** | 0.881 | 0.794 |
| 2 | 0.836 | 0.468 | **0.600** | 0.804 | 0.632 |

**Nota ponderada (F1×classe, N2=2×): 0.558**

## Leitura dos números (onde a IA entra)

- **Nível 1 sólido (F1 0,80):** o formato padrão é bem coberto por regex + FTS.
- **Recall de span despenca no nível 2 (0,72 → 0,47):** o extrator casa a
  *superfície*, e o ruído (abreviação, OCR, quebra de linha) faz o padrão falhar
  **antes** de a normalização agir. → **1º alvo de IA: um NER robusto a ruído.**
- **classe@match cai um pouco no N2 (0,88 → 0,80):** dado o span, a classificação
  segura relativamente bem — a regra de contagem de feitos é forte.
- **id@real ~0,63–0,79:** a separação "processo × menção" por limiar de posição
  erra em parte dos casos. → **2º alvo: parser de cabeçalho / classificador de contexto.**

## Limitações conhecidas (deixadas explícitas para a equipe)

- Súmula sem tabela número→id: **não há resolução implementada** — toda súmula cai em `incompleta`.
- Dispositivo de lei casado só por "art N" — não desambigua o código (CPC vs CPP).
- Bordas das citações vagas ficam mais largas que o gabarito (ainda passam no IoU≥0,5).

Estes são os pontos abertos para melhoria da referência.
