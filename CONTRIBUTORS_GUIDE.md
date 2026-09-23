# Guia para Contribuidores - Challenge JusBrasil

Este repositório é compartilhado entre múltiplos contribuidores para o desafio BRACIS 2026.

## 📁 Estrutura de Pastas

```
challenge-jusbrasil/
├── davi_version/          ← Solução de Davi Esmeraldo ✓
├── txt/                   ← Documentos de teste (compartilhados)
├── desafio1_bracis.db     ← Base de dados (compartilhada)
├── goldenset.csv          ← Gabarito (compartilhado)
├── README.md              ← Overview geral
├── CONTRIBUTORS_GUIDE.md  ← Este arquivo
└── [outras soluções podem ir aqui]
```

## 🚀 Como Adicionar Sua Solução

Se você quer contribuir com sua própria solução:

1. **Crie uma pasta com seu nome**:
   ```bash
   git clone https://github.com/williancarddd/challenge-jusbrasil.git
   cd challenge-jusbrasil
   mkdir seu_nome_version
   cp seus_arquivos ./seu_nome_version/
   ```

2. **Não modifique arquivos compartilhados**:
   - ❌ Não edite `txt/`, `desafio1_bracis.db`, `goldenset.csv`
   - ✅ Trabalhe apenas dentro de sua pasta

3. **Use paths relativos**:
   - Acesse dados com: `../txt/`, `../desafio1_bracis.db`, etc.
   - Exemplo em Python:
     ```python
     HERE = Path(__file__).resolve().parent
     TXT_DIR = HERE.parent / "txt"
     DB_PATH = HERE.parent / "desafio1_bracis.db"
     ```

4. **Adicione documentação**:
   - `SETUP_[NOME].md` — Como rodar sua solução
   - `README.md` — Explicação da arquitetura

5. **Commit sem deletar**:
   ```bash
   git add seu_nome_version/
   git commit -m "feat: Adicionar solução de [seu nome]"
   git push origin main
   ```

## 📋 Soluções Atuais

### ✅ davi_version (Davi Esmeraldo)
- **Score**: 1.0204
- **Características**: Rule-based, determinístico, sem ML
- **Status**: Pronto para produção
- **Setup**: Ver `davi_version/SETUP_DAVI_VERSION.md`

## ⚠️ Boas Práticas

### ✅ Faça
- Teste sua solução localmente antes de fazer push
- Use paths relativos (nunca caminhos absolutos)
- Documente como rodar sua solução
- Respeite a estrutura de pastas
- Use `git add seu_nome_version/` (não git add .)

### ❌ Não faça
- ❌ Modifique arquivos fora de sua pasta
- ❌ Delete ou sobrescreva dados compartilhados
- ❌ Use hardcoded paths com nomes de usuários
- ❌ Comite arquivos de cache (__pycache__, .pyc)
- ❌ Faça push de arquivos muito grandes

## 🔍 Como Avaliar Sua Solução

1. **Dentro de sua pasta**:
   ```bash
   cd seu_nome_version
   python run_eval.py --quiet
   ```

2. **Resultado esperado**:
   ```
   Nível 1: score=X.XXXX
   Nível 2: score=X.XXXX
   SCORE FINAL: X.XXXX
   ```

## 📊 Comparação de Soluções

Para comparar resultados:

```bash
cd davi_version && python run_eval.py --quiet
cd ../seu_nome_version && python run_eval.py --quiet
```

## 🆘 Troubleshooting

**"No such file or directory: ../txt"**
→ Você precisa estar dentro de sua pasta (seu_nome_version/)

**"desafio1_bracis.db not found"**
→ Verifique que o arquivo está na raiz do repositório

**"git refused to merge"**
→ Não modifique arquivos fora de sua pasta
