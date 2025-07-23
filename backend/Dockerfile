# --- STAGE 1: build a venv & install deps ---
FROM python:3.12-slim AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
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

# bring in the venv & code
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/backend /app/backend

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
  CMD curl -f http://localhost:$BACKEND_PORT/health || exit 1

# ← run as module inside the "backend" package. Allow custom port via BACKEND_PORT
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8000}"]
