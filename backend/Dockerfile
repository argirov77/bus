# --- STAGE 1: build a venv & install deps ---
FROM python:3.12-slim AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install dependencies from the root requirements.txt
COPY requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# copy your package as a subdirectory
COPY backend ./backend

# --- STAGE 2: final image ---
FROM python:3.12-slim

WORKDIR /app

# install curl so the healthcheck can run
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# bring in the venv & code
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/backend /app/backend

RUN chmod +x /app/backend/start.sh

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
  CMD ["sh", "-c", "curl -fk \"${BACKEND_HEALTHCHECK_URL:-http://localhost:${BACKEND_PORT:-8000}/health}\" || exit 1"]

# ← run backend through a small launcher that enables optional HTTPS support.
CMD ["/app/backend/start.sh"]
