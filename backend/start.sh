#!/bin/sh
set -e

# Allow overriding the UVicorn app path for advanced deployments while keeping
# the default backwards-compatible.
APP_PATH="${BACKEND_APP_PATH:-backend.main:app}"
PORT="${BACKEND_PORT:-8000}"

# Build the command line step-by-step to avoid word-splitting bugs.
set -- uvicorn "$APP_PATH" --host 0.0.0.0 --port "$PORT"

if [ -n "$BACKEND_SSL_CERTFILE" ] && [ -n "$BACKEND_SSL_KEYFILE" ]; then
    set -- "$@" --ssl-certfile "$BACKEND_SSL_CERTFILE" --ssl-keyfile "$BACKEND_SSL_KEYFILE"

    if [ -n "$BACKEND_SSL_KEYFILE_PASSWORD" ]; then
        set -- "$@" --ssl-keyfile-password "$BACKEND_SSL_KEYFILE_PASSWORD"
    fi

    if [ -n "$BACKEND_SSL_CA_FILE" ]; then
        set -- "$@" --ssl-ca-certs "$BACKEND_SSL_CA_FILE"
    fi
fi

exec "$@"
