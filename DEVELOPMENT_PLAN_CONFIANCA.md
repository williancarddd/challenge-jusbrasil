# Plano de Desenvolvimento: Sistema de Confiança para william_version

**Branch**: `william_version_add_confianca`  
**Objetivo**: Implementar e testar sistema robusto para geração/calibração de confiança  
**Base**: `william_version` (Score: 0.9780, τ=0.0)

---

## 🎯 Objetivos Principais

1. **Análise de Confiança Atual**
   - Entender como confiança é calculada atualmente
   - Identificar problemas e gaps

2. **Desenvolvimento de Métricas**
   - Criar métricas de confiança por tipo de citação
   - Calibrar baseado em performance observada

3. **Teste e Validação**
   - Rodar pipeline com novo sistema de confiança
   - Avaliar impacto no score geral

4. **Melhorias Exploratórias**
   - Testar diferentes abordagens
   - Documentar trade-offs

---

## 📊 Arquivos a Explorar/Modificar

### Existentes
```
src/challenge_jusbrasil/
├── confidence.py          ← Onde confiança é calculada AGORA
├── settings.py            ← Parâmetros de configuração
├── resolver/
│   ├── acordao.py         ← Resolução de acórdãos
│   ├── lei.py             ← Resolução de leis
│   └── sumula.py          ← Resolução de súmulas
└── pipeline.py            ← Onde confiança é usada
```

### A Criar
```
src/challenge_jusbrasil/
├── confidence_v2.py       ← Novo sistema de confiança (experimental)
├── confidence_metrics.py  ← Análise de calibração
└── tests/
    └── test_confidence.py ← Validação
```

---

## 🔍 Áreas de Melhoria Propostas

### 1. Confiança por Tipo de Citação
```python
# Atual: confiança por path de resolução
# Proposto: também por tipo de entidade + tribunal

CONFIDENCE_BY_TYPE = {
    "jurisprudencia": {
        "acordao": {"real": 0.95, "inventada": 0.05},
        "lei": {"real": 0.92, "inventada": 0.08},
        "sumula": {"real": 0.98, "inventada": 0.02},
    },
    "lei": {
        "artigo": {"real": 0.97, "inventada": 0.03},
    }
}
```

### 2. Confiança por Tribunal
```python
# Adicionar tribunal-specific calibration
# Alguns tribunais têm mais dados/padrões claros

CONFIDENCE_BY_TRIBUNAL = {
    "STF": 0.98,   # Mais estruturado
    "STJ": 0.95,   # Bom padrão
    "TST": 0.90,   # Menos estruturado
    "TSE": 0.93,   # Médio
}
```

### 3. Confiança por Path de Resolução
```python
# Expandir além do modelo atual
# Considerar:
# - Exatidão do match (100% vs 85%)
# - Número de candidatos encontrados
# - Contexto semântico da citação

CONFIDENCE_PATH_WEIGHTS = {
    "header_index_exact": 0.99,
    "header_index_fuzzy": 0.92,
    "fts_position_high": 0.88,
    "fts_position_medium": 0.75,
    "fts_fallback": 0.60,
}
```

### 4. Análise de Erros Anteriores
```python
# Estudar onde o modelo atual falha:
# - Quais tipos de citação causam FP/FN?
# - Em qual tribunal falha mais?
# - Que padrão de erro é mais comum?

# Ajustar confiança baseado em erros históricos
```

---

## 🧪 Plano de Testes

### Fase 1: Baseline
```bash
# Rodar pipeline atual sem mudanças
python -m challenge_jusbrasil.pipeline
# Score: 0.9780 (referência)
```

### Fase 2: Novo Sistema de Confiança
```bash
# Usar novo sistema de confiança
# CONFIDENCE_VERSION=v2 python -m challenge_jusbrasil.pipeline
# Esperar score similar ou melhor
```

### Fase 3: Ablation Study
```bash
# Testar cada componente isoladamente
# - Apenas by_type
# - Apenas by_tribunal
# - Apenas by_path (baseline melhorado)
# - Combinações
```

### Fase 4: Validação
```bash
# Comparar confiança predita vs erro real
# - Citações com alta confiança devem ter baixo erro
# - Citações com baixa confiança devem ser mais incertas
```

---

## 📈 Métricas de Sucesso

| Métrica | Baseline | Target |
|---|---|---|
| Score Final | 0.9780 | ≥ 0.9780 |
| τ (Segurança) | 0.0 | 0.0 (mantém) |
| Calibração | ? | Melhorada |
| F1(incompleta) | 0.75-0.77 | ≥ 0.78 |

---

## 🛠️ Como Começar

### 1. Análise Inicial
```bash
# Entender o sistema atual
grep -r "confidence" src/challenge_jusbrasil/

# Ver como confiança é usada
grep -r "confianca\|confidence" src/challenge_jusbrasil/ --include="*.py"
```

### 2. Implementação de v2
```bash
# Criar novo arquivo confidence_v2.py
# Copiar estrutura de confidence.py
# Adicionar novas métricas
# Testar sem quebrar o original
```

### 3. Testes
```bash
# Rodar pipeline com nova confiança
# Comparar contra baseline
# Documentar mudanças
```

### 4. Validação
```bash
# Análise de calibração
# Estudo de erro
# Documentação de trade-offs
```

---

## 📝 Commits Esperados

1. **feat: Add confidence analysis tools**
   - Novo arquivo confidence_metrics.py
   - Funções para analisar calibração

2. **feat: Implement confidence_v2 system**
   - Novo arquivo confidence_v2.py
   - Métricas por tipo, tribunal, path

3. **test: Add confidence validation tests**
   - Testes de sanidade
   - Validação de calibração

4. **docs: Document confidence improvements**
   - Análise de resultados
   - Trade-offs explorados

---

## 🚀 Próximas Etapas Imediatas

- [ ] Ler e entender confidence.py atual
- [ ] Analisar como confiança impacta score
- [ ] Coletar dados de erro por tipo/tribunal
- [ ] Prototipar novo sistema
- [ ] Validar contra baseline
- [ ] Documentar findings

---

## 📌 Notas Importantes

- **Não quebrar o baseline**: manter τ=0.0
- **Iterativo**: testar incrementalmente
- **Documentado**: explicar cada mudança
- **Reversível**: fácil rollback se necessário
- **Branch separada**: william_version fica intacta

---

**Status**: Preparado para desenvolvimento  
**Base**: william_version (Score: 0.9780)  
**Data**: 2026-09-29
