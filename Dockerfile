FROM python:3.12-slim

# 1. Copiar o uv da imagem oficial do Astral
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 2. Configurar variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/hf_cache \
    PATH="/app/.venv/bin:$PATH"

# 3. Copiar ficheiros de dependências
# (Substitua por requirements.txt se não usar pyproject.toml / uv.lock)
COPY pyproject.toml uv.lock ./

# 4. Instalar as dependências do projeto usando o uv
RUN uv sync --frozen --no-cache --no-install-project

# 5. Argumento opcional para modelos privados ou restritos (Gated)
# ARG HF_TOKEN


# 6. Baixar o modelo do Hugging Face no momento do build
# Substitua 'unsloth/Qwen3-8B-unsloth-bnb-4bit' pelo modelo desejado
RUN uv run --no-project hf download unsloth/Qwen3-8B-unsloth-bnb-4bit \
--local-dir /app/models/Qwen3-8B

RUN uv run --no-project hf download Morsoleto/Qwen3-8B-cacador-lora \
--local-dir results/train/adapter

# variables:
ENV LORA_BASE="/app/models/Qwen3-8B" \
    LORA_REPO="results/train/adapter"

# 7. Copiar o restante código da aplicação
COPY . .

RUN chmod +x run.sh

# Ponto de entrada
ENTRYPOINT ["bash", "run.sh"]