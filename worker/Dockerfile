FROM python:3.9-slim

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/main.py .

COPY shared ./shared

ENV PYTHONPATH=/app:/app/shared

CMD ["python", "main.py"]
