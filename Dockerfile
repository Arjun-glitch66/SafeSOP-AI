# Backend API. Build: docker build -t safesop-api .   (docker-compose.yml builds everything)
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    SAFESOP_DATA_DIR=/data LOG_FORMAT=json

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py alembic.ini ./
COPY app ./app
COPY src ./src
COPY migrations ./migrations
COPY evaluation ./evaluation

RUN useradd --create-home --uid 10001 safesop && mkdir -p /data && chown safesop /data
USER safesop
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/readyz').status != 200)"

# One process: background jobs and the per-minute rate limit live in memory (see app/services/jobs.py).
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
