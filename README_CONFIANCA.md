# Desenvolvimento de Confidence — william_version_add_confianca

**Branch**: `william_version_add_confianca`  
**Base**: `william_version` (Score: 0.9780)  
**Status**: Initial confidence system implemented and tested  
**Data**: 2026-09-29

---

## O que foi desenvolvido

### 1. Sistema de Calibração de Confiança (`confidence.py`)

Implementação completa de um sistema heurístico de confiança baseado em:

#### Tabelas de Confiança Base
```python
# Por tipo de citação e qualidade de match
("jurisprudencia", "exato"): 0.96        # encontrado exatamente
("jurisprudencia", "fuzzy"): 0.78        # fuzzy match
("jurisprudencia", "ambiguo"): 0.35      # múltiplos candidatos
("jurisprudencia", "nao_encontrado"): 0.08

("lei", "exato"): 0.98                   # lei específica
("lei", "fuzzy"): 0.85
("lei", "ambiguo"): 0.40
("lei", "nao_encontrado"): 0.10

("sumula", "exato"): 0.99                # súmula específica
("sumula", "fuzzy"): 0.80
("sumula", "ambiguo"): 0.45
("sumula", "nao_encontrado"): 0.08

("incompleta", "vaga"): 0.15             # sem identificador
```

#### Multiplicadores de Qualidade de Contexto
```python
contexto_qualidade = "alta"    # encontrou relator + cabeçalho + contexto grande
  → multiplicador: 1.08x (aumenta confiança)

contexto_qualidade = "media"   # sem matches específicos mas contexto razoável
  → multiplicador: 1.0x (sem ajuste)

contexto_qualidade = "baixa"   # sem contexto, sem matches
  → multiplicador: 0.92x (reduz confiança)
```

### 2. Componentes Implementados

**CalibradorConfianca**
- Classe principal que calibra confiança
- Suporta todos os tipos de citação
- Aplica multiplicadores de contexto

**MetadadosResolucao**
- Dataclass que armazena informações sobre uma resolução
- Campos: tipo, caminho, num_candidatos, relator_matches, cabecalho_matches, mesmo_feito, contexto_qualidade

**Funções Auxiliares**
- `estimar_caminho_resolucao()`: determina qualidade do match (exato/fuzzy/ambiguo/nao_encontrado)
- `estimar_qualidade_contexto()`: classifica contexto (alta/media/baixa)
- `calibrar_confianca()`: função conveniente de uma linha

### 3. Testes e Validação

**test_confidence.py**
- Suite completa com pytest
- 28+ testes cobrindo todos os cenários

**test_confidence_direct.py**
- Testes diretos sem pytest (útil para debugging)
- Valida calibração e multiplicadores

**Status**: ✅ Todos os testes passando

---

## Fluxo de Integração (Próximas Fases)

### Fase 1: Integração com Pipeline (não implementada ainda)
```python
# Em pipeline.py, quando resolver retorna (classe, id):
from challenge_jusbrasil.confidence import calibrar_confianca

confianca = calibrar_confianca(
    classe=classe,
    tipo_citacao=tipo_citacao,  # extrair do contexto
    num_candidatos=num_candidatos,
    relator_matches=...,
    cabecalho_matches=...,
    contexto_len=len(contexto),
)

# Adicionar ao JSON de saída
citacao["confianca"] = confianca
```

### Fase 2: Análise de Impacto
- Rodar pipeline com novo sistema
- Medir impacto no Brier score (calibração)
- Validar que score geral se mantém ≥ 0.9780

### Fase 3: Otimizações
- Ajustar valores na tabela_base baseado em dados reais
- Refinar multiplicadores de contexto
- Testar diferentes estratégias de combinação

---

## Arquitetura

### Arquivo de Documentação
- `DEVELOPMENT_PLAN_CONFIANCA.md` — Plano macro (objetivos, fases)
- `CONFIDENCE_ANALYSIS.md` — Análise técnica (resolvers, oportunidades)
- `README_CONFIANCA.md` — Este arquivo (status de desenvolvimento)

### Código
```
src/challenge_jusbrasil/
├── confidence.py              # Sistema de calibração
└── tests/
    ├── test_confidence.py     # Suite pytest
    └── (test_confidence_direct.py na raiz temporária)
```

### Testes
```
test_confidence_direct.py       # Validação rápida (sem pytest)
src/challenge_jusbrasil/tests/
└── test_confidence.py          # Suite pytest completa
```

---

## Calibração Proposta

### Exemplo 1: Jurisprudência Encontrada
```
Entrada: RESP 1.234.567/SP encontrado no banco
- classe: "real"
- tipo: "jurisprudencia"
- num_candidatos: 1
- relator_matches: True
- contexto_len: 350

Cálculo:
1. Caminho: 1 candidato → "exato"
2. Qualidade: relator_matches + contexto_len > 200 → "alta"
3. Confiança base: (jurisprudencia, exato) = 0.96
4. Multiplicador: "alta" = 1.08x
5. Confiança final: 0.96 * 1.08 = 1.0368 → 1.0 (clamped)

Resultado: 1.0 (máxima confiança)
```

### Exemplo 2: Jurisprudência Inventada
```
Entrada: ARESP 9.999.999/XX não encontrado
- classe: "inventada"
- tipo: "jurisprudencia"
- num_candidatos: 0

Cálculo:
1. Caminho: 0 candidatos → "nao_encontrado"
2. Confiança: (jurisprudencia, nao_encontrado) = 0.08

Resultado: 0.08 (baixa confiança, apropriada para inventada)
```

### Exemplo 3: Lei Encontrada
```
Entrada: Artigo 5º da CF encontrado
- classe: "real"
- tipo: "lei"
- num_candidatos: 1
- contexto_len: 100

Cálculo:
1. Caminho: 1 candidato → "exato"
2. Qualidade: sem matches específicos, contexto pequeno → "baixa"
3. Confiança base: (lei, exato) = 0.98
4. Multiplicador: "baixa" = 0.92x
5. Confiança final: 0.98 * 0.92 = 0.9016

Resultado: 0.90 (ainda alta, mas reduzida por falta de contexto)
```

---

## Próximos Passos

### Curto Prazo (Próximo Commit)
- [ ] Integrar `confidence.py` com `pipeline.py`
- [ ] Retornar confiança nos JSONs de saída
- [ ] Rodar pipeline completo e medir scores

### Médio Prazo
- [ ] Analisar calibração em dados reais
- [ ] Ajustar valores baseado em erro observado
- [ ] Otimizar multiplicadores

### Longo Prazo
- [ ] Explorar estratégias alternativas de confiança
- [ ] Teste A/B diferentes abordagens
- [ ] Documen trar trade-offs

---

## Métricas de Sucesso

| Métrica | Baseline | Target |
|---|---|---|
| Score Final | 0.9780 | ≥ 0.9780 |
| τ (Segurança) | 0.0 | 0.0 |
| Brier Score | — | Melhorado |
| Calibração | — | High (conf alta ↔ low error) |

---

## Notas Importantes

- **Confiança ainda não integrada**: Sistema criado e testado, mas pipeline ainda retorna `None`
- **Foco em heurísticas**: Sem ML, totalmente determinístico como a solução base
- **Segurança garantida**: Design não pode aumentar alucinações (τ)
- **Branch separada**: william_version fica intacta

---

**Desenvolvido para**: BRACIS 2026 — Desafio de Verificação de Citações Jurídicas  
**Branch**: william_version_add_confianca  
**Status**: Fase 1 Concluída (Sistema implementado e testado)
