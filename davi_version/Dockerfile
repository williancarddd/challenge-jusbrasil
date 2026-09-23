FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY kb/ ./kb/

# A base canônica (desafio1_bracis.db) e os .txt de entrada são montados em
# runtime pela organização — não vão dentro da imagem (ver README).
ENTRYPOINT ["python", "main.py"]
CMD ["--input", "/data/in", "--output", "/data/out", "--db", "/data/desafio1_bracis.db"]
