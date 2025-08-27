# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps (für uvloop/httptools - kompakt halten)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Jetzt den App-Code (Kontext ist ./backend)
COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000","--loop","uvloop","--http","httptools","--limit-max-request","52428800"]
