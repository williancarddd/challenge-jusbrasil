# Challenge Jusbrasil — Caça-Alucinações (BRACIS 2026)

## Como foi feito:

Treinamento professor-aluno usando Gemma-4-31B e Qwen3-8b, respectivamente

## Comandos

#### Docker build
```
docker build -t challenge-jusbrasil .
```

#### Docker run
```
docker run --rm challenge-jusbrasil /caminho/do/banco.db /caminho/da/pasta_txt /caminho/da/saida.csv
```
- `--rm` é opcional mas recomendo, e serve apenas para remover o conteiner após sua execução

Exemplo para esse repositório:
```
docker run challenge-jusbrasil ./data/desaio1_bracis.db ./data/txt/ ./resultados.csv
```
