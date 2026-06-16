FROM python:3.9-slim

# Build context deve essere la root del progetto
# docker-compose: build.context: .

WORKDIR /app

# Copia modulo condiviso
COPY shared/ /app/shared/

# Copia worker
COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir -r /app/worker/requirements.txt

COPY worker/ /app/worker/

# Directory persistenza identità nodo
RUN mkdir -p /app/data

ENV DATA_DIR=/app/data
ENV PYTHONPATH=/app

WORKDIR /app/worker

CMD ["python", "main.py"]
