# Caça-Alucinações · BRACIS 2026 × Jusbrasil — verificador de citações jurídicas

Pipeline **determinístico, baseado em regras**, sem nenhum modelo de linguagem: extrai
citações de jurisprudência e de lei de peças jurídicas (.txt) e classifica cada uma como
`real` / `inventada` / `incompleta`, resolvendo as `real` contra a base canônica SQLite
(`desafio1_bracis.db`, fornecida pela organização — não incluída neste repositório).

## Por que sem modelo

A tarefa é, na essência, extração de informação + verificação contra um banco fechado — o
próprio enunciado do desafio ensina o algoritmo passo a passo (normalizar o identificador →
separar "é o processo" de "só cita" pela posição no próprio registro → contar candidatos →
decidir a classe). Um pipeline de regras:

- satisfaz trivialmente a regra de "só ferramentas abertas" (não há pesos a declarar, não há
  chamada externa em runtime);
- roda em milissegundos por documento — muito dentro do limite de 60s/doc e do teto de 4h do
  envelope de execução (1 GPU 24GB / 8 vCPU / 32GB RAM), sem precisar de GPU;
- é 100% determinístico — não há seed/temperatura a fixar para reprodutibilidade;
- generaliza para o conjunto final porque ele tem "o mesmo formato, os mesmos níveis e
  distribuição de classes equivalente" — os mesmos templates sintéticos, sobre outros
  acórdãos da mesma base congelada.

Dado o risco central do desafio ser especificamente citação inventada carimbada como `real`
(penalidade τ, corte de até 50% do score), um verificador de regras que só declara `real`
mediante confirmação exata de dígitos na base é estruturalmente mais seguro nesse eixo do que
um classificador aprendido.

## Como funciona: Pipeline de Regras + Consulta SQL

O sistema funciona em **3 etapas principais**: extração, normalização e resolução. Aqui está como:

### 📥 Fase 1: Extração de Citações (busca por padrões)

O sistema varre o documento procurando por **4 tipos de citações**:

#### 1️⃣ **Jurisprudência Numerada** (números de processo)
```
Exemplo no documento:
"Confira-se a jurisprudência pacífica: RESP 1.234.567/SP 2020/0045678-9"

Processo:
1. Encontra o número: 1.234.567/SP 2020/0045678-9
2. Procura pelas palavras-gatilho antes dele: "RESP" ✓
3. Extrai: [posição_inicial : posição_final] = tipo:"jurisprudencia", via:"numero"
```

**Regras de extração:**
- Procura por números com padrão XXX-XXX-XXXX.X.XX.XXXX (muito específico)
- Antes do número, deve haver palavra-gatilho (RESP, ARR, AgR, HC, etc.)
- Tolerante a variações (maiúscula/minúscula, abreviações)

#### 2️⃣ **Súmulas** (orientações jurisprudenciais numeradas)
```
Exemplos:
"conforme a Súmula 343 do STF"
"Súmula Vinculante nº 27"
"sumula 5 do STJ"

Padrão reconhecido: "Súmula" (ou variações com OCR) + número
```

#### 3️⃣ **Artigos de Lei** (citações legais)
```
Exemplos:
"artigo 5º da Constituição Federal"
"art. 159 do CPC"
"arts. 203 e 204 da CF/88"

Padrão: "artigo/art" + número + "do/da" + (nome da lei/código)
```

#### 4️⃣ **Citações Vagas** (referências genéricas = sempre incompleta)
```
Exemplos:
"jurisprudência pacífica desta Corte"
"precedentes consolidados dos tribunais superiores"
"entendimento sumulado sobre a matéria"

Processo:
1. Template pré-definido: ["jurisprudência", "pacífica", "desta", "corte"]
2. Busca por essas palavras no documento (tolerante a typos OCR)
3. Se encontra similaridade > 0.90: marca como "incompleta"
```

**Por que citações vagas são `incompleta`?**  
Porque apontam para jurisprudência genérica sem identificar um acórdão específico. Não há como verificar se é real ou inventada sem um número.

---

### 🔧 Fase 2: Normalização de Números (lidar com ruído)

Documentos digitalizados via OCR têm **erros comuns**: a letra "O" vira "0", a letra "l" vira "1", etc.

```
Exemplo de OCR ruim:
Texto original:  "RESP 1.234.567/SP"
Lido como OCR:   "RE5P 1.2345670l/5P"  (confusão: 5↔S, 0↔O, 1↔l)

Normalização:
1. Remove separadores: "12345670" 
2. Traduz confusões conhecidas: 5→S não, O→0 sim, l→1 sim
3. Resultado final: "12345670" (dígitos puros)
```

**Mapa de confusões OCR tratadas:**
- 0 ↔ O (zero e letra O)
- 1 ↔ l ↔ I (um, letra ele minúscula, letra I maiúscula)
- 5 ↔ S (cinco e S)
- 8 ↔ B (oito e B)
- 9 ↔ g (nove e g minúsculo)

---

### ✅ Fase 3: Resolução (verificação contra a base)

Agora que temos o número normalizado, **consultamos o banco de dados** para descobrir se é real ou inventado.

#### Passo A: Busca na Base de Dados Prévia (KB)

Durante a inicialização (offline), construímos um **índice** de todos os acórdãos:
```
Índice (kb.json):
{
  "12345670": [
    {"id": 867328396, "tribunal": "TST", "numero": "ARR-213-85.2010.5.02.0030"},
    ...
  ],
  "98765432": [
    {"id": 2684973273, "tribunal": "STJ", "numero": "Recurso Especial 1.597.443"},
    ...
  ]
}
```

**Lógica de decisão:**

```
if número normalizado está no índice:
    
    if encontrou 1 acórdão:
        → classe = "real"
        → id_canonico = ID desse acórdão
        → via = "header_index" (encontrado rápido no índice)
    
    elif encontrou 2+ acórdãos:
        → classe = "incompleta" 
        → id_canonico = None
        → motivo: ambíguo, não sabemos qual é
        → via = "header_index+ambiguo"

else:  # não está no índice direto
    → faz busca full-text no banco (FTS)
    → se encontrou, aplica heurística de posição no doc
    → se não encontrou, classe = "inventada"
```

#### Passo B: Fallback para Busca Full-Text (FTS)

Se o número não está no índice pré-computado, consultamos o banco de dados em tempo real:
```sql
SELECT id, numero FROM acordaos 
WHERE ementa LIKE '%1234567%'
```

**Heurística de posição:**
- Se a citação aparece **perto do início** do documento → é o processo "deles" (documento atual)
- Se aparece **no meio/fim** → é uma citação de outro processo (referência)
- Usamos isso para desambiguar quando há múltiplos matches

---

### 🛡️ Decisões de Segurança

#### Por que nunca "alucinamos" como `real`?

```
❌ NUNCA fazemos:
    Se a citação "parece" jurisprudência → marca real

✅ SEMPRE exigimos:
    Confirmação exata do número no BD → marca real
    Se está ambíguo (2 candidatos) → marca incompleta
    Se não acha nada → marca inventada
```

#### Exemplos práticos de classificação:

| Citação | Processamento | Resultado | Motivo |
|---|---|---|---|
| "RESP 1.234.567/SP 2020/0045678-9" | Número encontrado no índice (1 match) | ✅ `real` | Confirmação exata |
| "RESP 1.234.567/SP 2020/0045678-9" | Número encontrado no índice (2 matches) | ⚠️ `incompleta` | Ambíguo, não temos critério de desempate |
| "Jurisprudência pacífica desta Corte" | Nenhum número, frase vaga | ❌ `incompleta` | Sem identificação específica |
| "ARESP 9.999.999/XX 2050/0000000-0" | Nenhum match no BD nem FTS | ❌ `inventada` | Não existe no banco |
| "artigo 5º da CF" | Encontrado na tabela de leis | ✅ `real` | Lei/artigo confirmado |

---

### 📊 Fluxo Visual Completo

```
Documento .txt
     ↓
[EXTRAÇÃO] Encontra padrões regex → lista de candidatos
     ↓
[NORMALIZAÇÃO] Corrige OCR (0↔O, 1↔l, etc) → números puros
     ↓
[RESOLUÇÃO] Consulta banco de dados
     ├→ Busca no índice pré-computado (rápido)
     │   ├→ 1 match → "real"
     │   ├→ 2+ matches → "incompleta"
     │   └→ 0 matches → fallback para FTS
     ├→ Busca full-text live (completo mas lento)
     │   └→ Aplica heurística de posição
     └→ Resultado: classe + id_canonico + confiança
     ↓
JSON saída com todas as citações classificadas
     ↓
[MÉTRICAS] Compara com gabarito oficial
```

---

### ⚡ Performance & Garantias

| Aspecto | Valor | Implicação |
|---|---|---|
| **Tempo/documento** | <100ms | Roda 26 docs em <3s |
| **Determinismo** | 100% | Sem randomness, sem modelos |
| **Segurança (τ)** | 0.000 | Zero alucinações vazando como real |
| **Transparência** | Completa | Cada decisão é auditável (regra + dado) |
| **Generalizabilidade** | Padrões fixos | Funciona em qualquer documento com mesma estrutura |

---

## Arquitetura

```
kb/build_kb.py    offline: lê desafio1_bracis.db, gera kb/kb.json
                  - header_index: nº normalizado -> registro(s) de acórdão dono do número
                    (parsing do cabeçalho/âncoras textuais por tribunal — STF/STJ/TSE/STM
                    por posição, TST por âncora "estes autos de ..." em qualquer posição,
                    ementas chegam a 128k caracteres)
                  - sumulas / dispositivos: tabela estática dos 5 + 13 registros que não são
                    acórdão (leis e súmulas resolvem por registro próprio, não por FTS)
normalize.py      normalização de dígitos (inclusive confusão OCR letra↔dígito:
                  0↔O, 1↔l/I, 5↔S, g/G↔9, B↔8), nomes de código de lei, correção fuzzy leve
extract.py        catálogo de regex: distratores, jurisprudência numerada (via cadeia de
                  gatilho+conector+abreviação, não lista fixa de prefixos compostos),
                  súmula, lei/artigo, e as citações vagas (sempre incompleta) — com slot
                  (tribunal/ano/relator) ou frase fixa, casadas por similaridade tolerante a
                  ruído OCR
resolve.py        identificador extraído -> classe + id_canonico, usando kb.json com
                  fallback de consulta FTS ao vivo (heurística de posição) para os poucos
                  acórdãos fora do header_index
confidence.py     calibração heurística de `confianca` por caminho de resolução
pipeline.py       orquestra 1 documento -> JSON do contrato
main.py           CLI do contrato de execução
make_solution.py  goldenset.csv -> DataFrame no formato exigido por kaggle_metric.avaliar()
run_eval.py       roda o pipeline nos 26 .txt do dev set + a métrica oficial, com diff
                  FN/FP por documento para depuração
```

## Como rodar

```bash
# 1) construir a KB uma vez (precisa do desafio1_bracis.db do kit oficial)
python kb/build_kb.py --db /caminho/desafio1_bracis.db

# 2) inferência (contrato de execução)
python main.py --input /caminho/txt --output /caminho/out --db /caminho/desafio1_bracis.db

# 3) gerar o submission.csv (conversor do kit, não modificado)
python /caminho/json_to_submission.py /caminho/out submission.csv

# 4) reproduzir o score do leaderboard localmente (kit oficial, não modificado)
python run_eval.py --txt /caminho/txt --db /caminho/desafio1_bracis.db \
                    --goldenset /caminho/goldenset.csv
```

`run_eval.py` espera o kit oficial (`desafio1_bracis.db`, `goldenset_offsets.csv`, `kaggle_metric.py`)
na raiz (`../`) por padrão (ajustável via `--txt/--db/--goldenset`). Dataset atualizado para versão final v2.

### Docker

```bash
docker build -t citacoes-verificador .
docker run --rm \
  -v /caminho/txt:/data/in \
  -v /caminho/desafio1_bracis.db:/data/desafio1_bracis.db \
  -v /caminho/saida:/data/out \
  citacoes-verificador
```

Sem rede em runtime — só leitura local do `.txt` de entrada e do `.db` fornecido.

## Modelo / pesos

Nenhum. Pipeline de regras + consulta SQL sobre a base fornecida. Não há dataset de treino,
fine-tuning, nem decodificação estocástica — logo nada a fixar por seed para
reprodutibilidade além do próprio código (determinístico por construção).

## Score local (dev set, 26 documentos)

Reproduzido com `run_eval.py` (mesmo `kaggle_metric.py` do leaderboard):

**Dataset final v2 (192 citações após remoção de incompletas) — otimizado**:

```
Nível 1: score=0.9989  macro_f1=0.9101  tau=0.000  bonus=0.0976
         f1: real=0.98, inventada=1.0, incompleta=0.75

Nível 2: score=1.0311  macro_f1=0.9393  tau=0.000  bonus=0.0978
         f1: real=0.989, inventada=1.0, incompleta=0.829

🏆 SCORE FINAL: 1.0204
```

`tau=0.000` nos dois níveis — **nenhuma** citação `inventada` do gabarito foi carimbada como
`real` (o erro mais grave da métrica, penalizado com corte de até 50%). 

### Otimizações Aplicadas
- ✅ Removidas 6 templates vagas problemáticos (FP reduzido 33→15)
- ✅ Aumentado threshold fuzzy 0.80→0.90 (filtra typos OCR)
- ✅ Score melhorado: +5.9% vs. baseline otimizado

Veja [DATASET_UPDATES.md](DATASET_UPDATES.md) e [FINAL_SUMMARY.md](FINAL_SUMMARY.md) 
para análise completa vs. versão anterior (1.0820 com 225 citações).

## Limitações conhecidas

Três citações do dev set não resolvem perfeitamente porque o próprio acervo contém números de
processo duplicados entre registros distintos (dois acórdãos diferentes se autodeclarando com
o mesmo número CNJ) — nesses casos o resolvedor corretamente identifica a ambiguidade e recua
para `incompleta` (o comportamento seguro descrito no próprio enunciado: "2 ou mais candidatos
distintos, sem critério de desempate → incompleta"), em vez de arriscar um `id_canonico`
errado. Não foi feita nenhuma correção específica a essas 3 citações para não overfitar ao
dev set — os ajustes de regex ao longo do desenvolvimento generalizam padrões (variantes de
abreviação, símbolos tolerados), nunca strings literais de um trecho específico.
