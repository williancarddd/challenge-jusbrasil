# Análise do Sistema de Confiança — william_version

## Status Atual

### Confiança Não Implementada
- **Pipeline**: Todas as citações retornam `"confianca": None`
- **Archivos afetados**:
  - `pipeline.py:132` — inicializa citações com `confianca: None`
  - `lener.py` — também inicializa com `confianca: None`
  
### Sistema de Avaliação Pronto
O `kaggle_metric.py` já suporta avaliação de confiança:
```python
# Métricas de calibração (Brier Score)
acc["brier_termos"].append((confianca_predita - y_real) ** 2)

# Bonus aplicado se confiança é informada
if confianca is not None:
    bonus = apply_brier_bonus(confianca_erros)
else:
    bonus = 0.0  # sem confiança = sem bonus/punição
```

---

## 📊 Resolvers Disponíveis

Cada resolver retorna: `(classe, id_canonico, detalhes_resolucao)`

### 1. **resolver/acordao.py** — Acórdãos (jurisprudência)
Responsável por resolver acórdãos contra o banco de dados.

### 2. **resolver/lei.py** — Leis e Artigos
Resolve artigos e leis específicas.

### 3. **resolver/sumula.py** — Súmulas
Resolve súmulas e jurisprudência sumulada.

### 4. **resolver/comum.py** — Resolução Comum
Orquestra os três resolvers acima.

---

## 🔍 Oportunidades de Confiança

### Por Tipo de Citação

**Jurisprudência (Acórdãos)**:
- Número exato encontrado → alta confiança (0.95-0.99)
- Número fuzzy/parcial → confiança média (0.60-0.80)
- Ambíguo (2+ matches) → confiança baixa (0.30-0.50)
- Não encontrado → muito baixa (0.05-0.15)

**Leis e Artigos**:
- Artigo específico encontrado → muito alta (0.98-1.0)
- Referência genérica → média (0.50-0.70)
- Não encontrado → baixa (0.10-0.20)

**Súmulas**:
- Número exato → muito alta (0.98-1.0)
- Ambíguo → média (0.50-0.70)
- Não encontrado → baixa (0.10-0.20)

### Por Qualidade de Match

- **Exact match** (100% correspondência): 0.95-0.99
- **Fuzzy match** (85-99%): 0.75-0.90
- **Partial/ambiguous** (2+ candidatos): 0.30-0.60
- **FTS fallback** (busca full-text): 0.50-0.80
- **Not found** (inventada): 0.05-0.20

---

## 🛠️ Estratégia de Implementação

### Fase 1: Análise
- [ ] Examinar cada resolver para entender como retorna resultados
- [ ] Mapear quais informações de confiança estão disponíveis
- [ ] Estudar dados de erro (false positives/negatives)

### Fase 2: Prototipagem
- [ ] Criar `confidence.py` com funções básicas
- [ ] Implementar calibração por tipo de citação
- [ ] Integrar com pipeline existente

### Fase 3: Validação
- [ ] Testar confiança em subset de dados
- [ ] Validar calibração (high conf → low error)
- [ ] Medir impacto no score (bonus Brier)

### Fase 4: Otimização
- [ ] Ajustar thresholds baseado em dados
- [ ] Testar diferentes estratégias
- [ ] Documentar trade-offs

---

## 📝 Próximos Passos

1. **Ler resolver/comum.py** para entender outputs disponíveis
2. **Ler resolver/acordao.py, lei.py, sumula.py** para mapear paths de resolução
3. **Criar confidence.py** com calibração básica
4. **Integrar com pipeline.py** para retornar confiança
5. **Testar e validar** contra dados locais

---

**Status**: Análise concluída, pronto para implementação  
**Branch**: william_version_add_confianca  
**Data**: 2026-09-29
