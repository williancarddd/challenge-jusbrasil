#!/usr/bin/env bash
set -e

# Validação dos argumentos
if [ "$#" -lt 3 ]; then
    echo "Uso incorreto!"
    echo "Sintaxe: bash run.sh <caminho_db> <pasta_txt> <arquivo_saida>"
    exit 1
fi

CAMINHO_DB="$1"
PASTA_TXT="$2"
ARQUIVO_SAIDA="$3"

# Ajustar PYTHONPATH se necessário para garantir o carregamento do pacote
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Execução do ponto de entrada
python3 -m challenge_jusbrasil.cli "$CAMINHO_DB" "$PASTA_TXT" "$ARQUIVO_SAIDA"
