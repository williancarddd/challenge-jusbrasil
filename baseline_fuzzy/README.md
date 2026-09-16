# Baseline — Fuzzy (RapidFuzz + OCR)

Mesmo pipeline do baseline de regra (**extrair → normalizar → consultar →
contar feitos**), com matching fuzzy via [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz)
(Levenshtein + `partial_ratio`) para ruído do nível 2.

```bash
uv venv .venv
uv pip install -r requirements.txt
.venv/bin/python main.py
```

## Estrutura

| Módulo | Passo | O que faz |
|---|---|---|
| `fuzzy.py` | — | `proximo` / `iter_proximos` / `melhor_rotulo` em cima do RapidFuzz. |
| `extrair.py` | 1 | Cadeia de classes + número ruidoso; súmula/vaga/tema por âncora fuzzy. |
| `normalizar.py` | 2 | Hipóteses de OCR letra↔dígito e formas de busca (CNJ, milhar, cru). |
| `resolver.py` | 3 | FTS + LIKE; lei desambiguada por `partial_ratio` contra o texto do dispositivo. |
