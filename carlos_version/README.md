# Caça-Alucinações — BRACIS 2026 × Jusbrasil

## Instalação

```bash
uv sync
```

## Execução

```bash
uv run main.py --data data/final --input data/final/txt
```

| argumento | o que é | padrão |
| --- | --- | --- |
| `--data` | pasta com a base canônica `desafio1_bracis.db` | obrigatório |
| `--input` | pasta com os `.txt` a processar | obrigatório |
| `--output` | onde gravar os resultados | `output/` |
| `--model` | pasta dos pesos do modelo | `models/Qwen3-8B-FP8` |

## Observações

- `WORKERS=1 uv run main.py ...` serializa as chamadas à LLM: mais lento, mas
  reprodutível. O padrão é uma chamada por CPU, menos uma.
- Se já houver um servidor vLLM respondendo em `localhost:8000`, o `main.py` o reaproveita
  em vez de subir outro.
- Em GPU com menos memória livre, ajuste `--gpu-memory-utilization` em
  `src/cacador_alucinacoes/llm_server.py`.
