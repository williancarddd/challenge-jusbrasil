# Análise Comparativa: carlos_version vs william_version_improved

**Data**: 2026-09-29  
**Desafio**: BRACIS 2026 — Verificação de Citações Jurídicas

---

## Quick Overview

| Aspecto | carlos_version | william_version_improved |
|---|---|---|
| Estratégia | Hybrid (Regex + LLM) | LLM-first + Confidence |
| Modelo Base | Qwen3-8B | Gemma31B + Students |
| Confiança | Não | Sim (calibrada) |
| GPU Memory | 16GB | 32-64GB |
| Latência | 200-500ms | 500-1000ms |
| Simplicidade | Média | Alta complexidade |

---

## 1. Arquitetura

### carlos_version

```
TXT → Regex Extract → LLM Fallback (Qwen3-8B) → Resolution (SQL) → JSON
```

- Hybrid: tenta regex primeiro, LLM como fallback
- vLLM server para gerenciar modelo
- Determinístico para resolução

### william_version_improved

```
TXT → LLM Extract (Gemma31B) → Resolution (SQL) → Confidence Calibration → JSON
```

- LLM-first: sempre usa modelo
- Knowledge distillation (teacher → students)
- Confiança pós-processada

---

## 2. Extraction (Como encontra citações)

**carlos_version**:
- Regex patterns primeiro (rápido)
- Se poucos resultados → chama LLM
- Merge dos dois

**william_version_improved**:
- Sempre LLM (Gemma31B)
- Opcional: LeNER para NER
- Mais consistente

---

## 3. Resolution (Como valida citações)

**Ambos idênticos**:
- Normaliza OCR
- Busca em índice SQL
- Exato → real
- Multiple matches → incompleta
- Not found → inventada

**Diferença**: william_version adiciona confiança após resolução

---

## 4. Confiança (DIFERENÇA CHAVE)

### carlos_version

```json
{
  "classificacao": "real",
  "confianca": null  // não implementado
}
```

### william_version_improved

```json
{
  "classificacao": "real",
  "confianca": 1.0  // calibrado: 0.96 * 1.08
}
```

**Sistema de calibração**:
- Tabelas por tipo (jurisprudência/lei/sumula)
- Multiplicadores por contexto (alta/media/baixa)
- 20+ testes, 100% passing

---

## 5. Modelos

### carlos_version

- Qwen3-8B (8 bilhões parâmetros)
- vLLM para inferência
- BNB quantization

### william_version_improved

Teacher-Student (Knowledge Distillation):
- **Teacher**: Gemma31B (31 bilhões)
- **Students**: Llama 7B, Phi 2.7B, Qwen 7B, SmolLM 1.7B
- LORA adapters + BNB quantization
- Treino necessário

---

## 6. Custo & Complexidade

| Métrica | carlos | william |
|---|---|---|
| GPU Memory | 16GB | 32-64GB |
| Latência/Doc | 200-500ms | 500-1000ms |
| Lines of Code | ~1000 | ~2500+ |
| Training | Não | Sim |
| Deployment | Médio | Complexo |

---

## 7. Quando Usar Cada

### Usar carlos_version se:
- Quer **máxima velocidade**
- GPU **limitada** (<16GB)
- Precisa de **deployment simples**
- Confiança não é crítica

### Usar william_version_improved se:
- Quer **melhor score** (com confiança)
- Tem **GPU potente** (V100/A100)
- Pode investir em **treinamento**
- Precisa de **Brier score** otimizado

---

## 8. Score Esperado

**carlos_version**: 0.95-1.00 (sem confiança)
- Extraction: Bom
- Resolution: Determinístico
- Confidence: N/A

**william_version_improved**: 0.95-1.05+ (com confiança)
- Extraction: Excelente
- Resolution: Determinístico
- Confidence: Calibrada (+1-5% Brier)

---

## 9. Recomendação

| Contexto | Vencedor |
|---|---|
| Melhor Score | william_version_improved |
| Mais Rápido | carlos_version |
| Mais Simples | carlos_version |
| Mais Capaz | william_version_improved |
| Produção Leve | carlos_version |
| Pesquisa | william_version_improved |

---

**Conclusão**: 
- **Competição BRACIS**: william_version_improved (confiança calibrada)
- **Produção**: carlos_version (leve + rápido)
- **Ideal Híbrido**: LLM-first + confiança + otimizado

