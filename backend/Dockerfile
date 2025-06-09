# --- STAGE 1: зависимости & сборка backend ---
FROM python:3.12-slim AS builder

# Установим системные зависимости (пр./ git, gcc, libpq-dev и т.д.)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимостти и ставим их
COPY backend/requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Копируем весь код
COPY backend /app

# --- STAGE 2: финальный образ ---
FROM python:3.12-slim

WORKDIR /app

# Копируем venv из билдера
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

ENV PATH="/opt/venv/bin:$PATH"

# Порт, на котором будет слушать FastAPI
EXPOSE 8000

# Healthcheck (необязательно)
HEALTHCHECK --interval=30s --timeout=5s \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
