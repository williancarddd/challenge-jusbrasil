# Guia para Contribuidores - Challenge JusBrasil

Este repositório é compartilhado entre múltiplos contribuidores para o desafio BRACIS 2026.

## 📁 Estrutura de Versões

Cada solução tem sua própria **branch dedicada**:

```
Branches de Solução:
├── davi_version_rule_based    ← Solução Rule-based determinística
│   └── Score: 1.0204 | τ=0.0 | Sem ML
├── william_version             ← Solução LLM-based (Teacher-Student)
│   └── Score: 0.9780 | τ=0.0 | Com vLLM
├── carlos_version              ← Solução ...
│   └── Score: ...
└── org                         ← Branch organizacional

Main:
├── txt/                   ← Documentos de teste (compartilhados)
├── desafio1_bracis.db     ← Base de dados (compartilhada)
├── goldenset.csv          ← Gabarito (compartilhado)
├── README.md              ← Overview geral
└── [arquivos compartilhados]
```

## 🚀 Como Trabalhar com as Versões

### Clonar uma Versão Específica

```bash
# Clonar a versão rule-based de Davi
git clone --branch davi_version_rule_based https://github.com/williancarddd/challenge-jusbrasil.git

# Clonar a versão LLM de William
git clone --branch william_version https://github.com/williancarddd/challenge-jusbrasil.git

# Clonar main (acesso aos dados compartilhados)
git clone https://github.com/williancarddd/challenge-jusbrasil.git
```

### Criar Sua Própria Versão

1. **Crie uma branch nova a partir de main**:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b seu_nome_version main
   ```

2. **Adicione sua solução**:
   ```bash
   # Copiar arquivos da solução para raiz da branch
   # Manter txt/, desafio1_bracis.db, goldenset.csv acessíveis
   ```

3. **Documente sua abordagem**:
   - README.md - Explicação técnica
   - SETUP.md - Como rodar
   - Documentação adicional conforme necessário

4. **Faça commit e push**:
   ```bash
   git add .
   git commit -m "feat: Adicionar solução seu_nome_version

   Score: X.XXXX
   Abordagem: [descrição]
   Status: [alpha/beta/ready]"
   git push -u origin seu_nome_version
   ```

## 📊 Soluções Atuais

### ✅ davi_version_rule_based (Davi Esmeraldo)
- **Score**: 1.0204
- **τ (Segurança)**: 0.0
- **Características**: Rule-based, determinístico, sem ML
- **Tech**: Python 3.11+, stdlib-only
- **Status**: Pronto para produção
- **Setup**: Ver `README.md` na branch

### ✅ william_version (William)
- **Score**: 0.9780
- **τ (Segurança)**: 0.0
- **Características**: LLM-based (Teacher-Student)
- **Tech**: vLLM, PyTorch, Quantização 4-bit
- **Status**: Em desenvolvimento
- **Setup**: Ver branch para documentação

### ✅ carlos_version (Carlos)
- **Score**: [consultar branch]
- **Status**: [consultar branch]

## ⚠️ Boas Práticas

### ✅ Faça
- Trabalhe na sua branch separada
- Mantenha txt/, db, csv em sincronismo com main
- Documente sua abordagem
- Teste contra o gabarito local
- Use paths relativos em sua solução

## 🔍 Compartilhando Dados

### Acessar Dados da Main

Se sua branch precisa dos dados compartilhados:

```bash
# Opção 1: Fazer merge de main
git merge main --no-commit  # Verifica mudanças
git reset HEAD~ # Reseta o merge
git checkout main -- txt/ desafio1_bracis.db goldenset.csv

# Opção 2: Symlink (em desenvolvimento)
ln -s ../txt ./txt
ln -s ../desafio1_bracis.db ./desafio1_bracis.db
```

### Sincronizar Dados
```bash
# Atualizar dados quando main mudar
git pull origin main -- txt/ desafio1_bracis.db goldenset.csv
```

## 📋 Checklist para Nova Versão

- [ ] Branch criada a partir de main
- [ ] Solução funciona localmente
- [ ] Score calculado e documentado
- [ ] README.md escrito
- [ ] SETUP.md escrito
- [ ] Commit com mensagem descritiva
- [ ] Push para origin
- [ ] Nenhuma modificação acidental em shared files

## 🤝 Comparação de Versões

Para comparar resultados entre versões:

```bash
# Ver documentação de cada branch
for branch in davi_version_rule_based william_version carlos_version; do
  echo "=== $branch ==="
  git show $branch:README.md | head -30
done

# Clonar múltiplas versões
git clone --branch davi_version_rule_based ... davi_version
git clone --branch william_version ... william_version
git clone --branch carlos_version ... carlos_version
```

## 📈 Métricas Resumidas

| Versão | Score | τ | Abordagem | Requer GPU |
|---|---|---|---|---|
| davi_version_rule_based | 1.0204 | 0.0 | Rule-based | NÃO |
| william_version | 0.9780 | 0.0 | LLM-based | SIM |
| carlos_version | ? | ? | ? | ? |

---

**Última atualização**: 2026-09-29  
**Status**: Branches separadas ✓
**Dados compartilhados em main**: ✓
