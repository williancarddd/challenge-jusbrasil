# Setup: Versão Davi - Verificador de Citações Jurídicas

Esta é a solução desenvolvida por **Davi Esmeraldo** para o desafio BRACIS 2026 de verificação de citações jurídicas.

## 📋 Como Usar Esta Solução

### Pré-requisitos

```bash
python --version  # Python 3.11+
pip install -r requirements.txt
```

### Dados Necessários

Arquivos fornecidos no repositório raiz:

```
challenge-jusbrasil/
├── davi_version/             ← Esta pasta
├── txt/                      ← Documentos de entrada
├── desafio1_bracis.db        ← Base canônica
├── goldenset.csv            ← Gabarito
└── kaggle_metric.py         ← Métrica oficial
```

### Como Rodar

```bash
cd davi_version

# Inferência
python main.py --input ../txt --output ./out --db ../desafio1_bracis.db

# Avaliação
python run_eval.py --txt ../txt --db ../desafio1_bracis.db --goldenset ../goldenset.csv
```

## 🏆 Score Final: 1.0204

- Nível 1: score=0.9989, F1(real)=0.98, F1(inventada)=1.0, F1(incompleta)=0.75
- Nível 2: score=1.0311, F1(real)=0.989, F1(inventada)=1.0, F1(incompleta)=0.829
- **τ = 0.000** (zero alucinações)
- 100% determinístico, 100ms/documento

## 📖 Documentação

- `README.md` — Arquitetura técnica completa
- `APRESENTACAO_PUBLICA.md` — Para públicos diversos
- `DATASET_UPDATES.md` — Análise de otimizações
- `FINAL_SUMMARY.md` — Diagnóstico técnico
- `SUBMISSION_CHECKLIST.md` — Deployment

## ✅ Verificação Rápida

```bash
cd davi_version
python -c "from pipeline import process_documento; print('✓ Pipeline OK')"
ls kb/kb.json
python run_eval.py --quiet
```

## 📁 Estrutura

```
davi_version/
├── main.py, pipeline.py, extract.py, resolve.py
├── normalize.py, confidence.py, make_solution.py, run_eval.py
├── kb/ (build_kb.py, kb.json, leis_sumulas.py)
├── requirements.txt, Dockerfile
└── Documentação (*.md)
```

## ⚠️ Paths Relativos

Scripts assumem:
- `../txt/` → Documentos
- `../desafio1_bracis.db` → Base
- `../goldenset.csv` → Gabarito

Rode sempre de dentro de `davi_version/`.

**Desenvolvido por Davi Esmeraldo para BRACIS 2026**  
Versão: 1.0.204 | 2026-09-23 | Status: Pronto para produção
