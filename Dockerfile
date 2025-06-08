# --------- Frontend build stage ---------
FROM node:20 AS frontend-build
WORKDIR /app/frontend
# Install dependencies
COPY frontend/package.json ./
RUN npm install
# Copy source and build
COPY frontend .
RUN npm run build

# --------- Backend stage ---------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VENV_PATH="/opt/venv"
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR /app

COPY requirements.txt ./
RUN python -m venv $VENV_PATH \
    && $VENV_PATH/bin/pip install --upgrade pip \
    && $VENV_PATH/bin/pip install --no-cache-dir -r requirements.txt

# Copy backend code and compiled frontend
COPY backend ./backend
COPY --from=frontend-build /app/frontend/build ./frontend/build

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
