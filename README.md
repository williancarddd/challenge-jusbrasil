# Challenge Jusbrasil — Caça-Alucinações (BRACIS 2026)

Materiais e utilitários para o desafio de detecção, classificação e resolução de
**citações jurídicas** (leis e jurisprudência) em textos gerados, com foco em
identificar alucinações (citações **inventadas** ou **incompletas**) frente a
citações **reais**.

## Conteúdo do repositório

| Caminho | Descrição |
|---|---|
| `Dados do Caça-Alucinações - BRACIS 2026.pdf` | Especificação do desafio (dados, formato e métrica). |
| `desafio1_bracis.db` | Base SQLite com 1.018 documentos (tabela `documentos` + índice FTS). Versionado via **Git LFS**. |
| `goldenset.csv` | Conjunto anotado de referência (225 citações rotuladas). |
| `txt/` | 26 documentos de exemplo em texto puro (`gen_n1_*.txt`). |
| `json_to_submission.py` | Converte os JSONs do contrato de saída no `submission.csv` do Kaggle. |

## Formato dos dados

**`goldenset.csv`** — uma linha por citação anotada:

`nivel, documento_id, citacao_id, inicio, fim, trecho, tipo, classificacao, id_canonico`

- `tipo` ∈ {`lei`, `jurisprudencia`}
- `classificacao` ∈ {`real`, `incompleta`, `inventada`}
- `inicio`/`fim` — span de caracteres no texto do documento.

**`desafio1_bracis.db`** — tabela `documentos` com colunas
`documento_id, id, tribunal, ano, relator, natureza, tipo, texto, texto_len`,
mais uma tabela FTS (`documentos_fts`) para busca full-text.

## Uso

Gerar o CSV de submissão a partir de uma pasta de JSONs no formato do contrato:

```bash
python json_to_submission.py <pasta_com_jsons> [submission.csv]
```

Saída: uma linha por documento — `documento_id, citacoes`, onde `citacoes` é
`inicio,fim,classe,id_canonico,confianca` separado por `|` (`-` quando ausente).

## Git LFS

O arquivo `desafio1_bracis.db` (~90 MB) é rastreado por **Git LFS**. Após clonar:

```bash
git lfs install
git lfs pull
```
