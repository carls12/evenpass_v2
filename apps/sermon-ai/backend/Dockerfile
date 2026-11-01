FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py ai.py export.py backup.py ./
COPY fonts ./fonts

# Unprivileged user; /data is the persistent volume (database, audio, backups).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data && chown app:app /data
USER app
VOLUME /data

ENV SERMON_ENV=production \
    SERMON_DB_PATH=/data/sermon.sqlite3 \
    SERMON_AUDIO_DIR=/data/audio \
    SERMON_BACKUP_DIR=/data/backups

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/sermon-ai/health', timeout=4)"

# One worker: SQLite, the login throttle and the in-process job threads expect a single process.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
