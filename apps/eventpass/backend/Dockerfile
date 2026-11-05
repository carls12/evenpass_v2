FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY *.py default_badge_bg.jpg default_logo.png ./
COPY fonts ./fonts
COPY email_templates ./email_templates

# Unprivileged user; /data is the persistent volume (database, uploads, backups).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data && chown app:app /data
USER app
VOLUME /data

ENV EVENTPASS_ENV=production \
    EVENTPASS_DB_PATH=/data/eventpass.sqlite3 \
    EVENTPASS_ASSETS_DIR=/data/badge_assets \
    EVENTPASS_BACKUP_DIR=/data/backups

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/eventpass/health', timeout=4)"

# One worker: SQLite + the in-process login throttle expect a single process.
# Only Caddy can reach this port (internal Docker network), so forwarded headers are trusted.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
