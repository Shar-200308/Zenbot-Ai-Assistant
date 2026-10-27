# ============================================================
#  Zenbot — Production Dockerfile
#  Disadvantage #6 fix: containerized deployment
#
#  Build:   docker build -t zenbot .
#  Run:     docker run -p 8000:8000 --env-file .env zenbot
# ============================================================

# ── Stage 1: Builder (install Python deps) ────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system build deps (for psycopg2, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into /app/.venv
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Production image ─────────────────────────────────────────────────
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Runtime system deps only (libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy project files
COPY . .

# Collect static files (uses STATIC_ROOT = /app/staticfiles)
RUN python manage.py collectstatic --noinput --settings=Zenbot.settings 2>/dev/null || true

# Create non-root user for security
RUN addgroup --system zenbot && adduser --system --ingroup zenbot zenbot
RUN chown -R zenbot:zenbot /app
USER zenbot

# Expose application port
EXPOSE 8000

# Start production WSGI server (waitress — already in requirements.txt)
# For Gunicorn: replace with: gunicorn Zenbot.wsgi:application --bind 0.0.0.0:8000 --workers 2
CMD ["python", "-m", "waitress", "--port=8000", "--call", "Zenbot.wsgi:get_wsgi_application"]
