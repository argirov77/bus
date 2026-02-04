"""Helpers for resolving the client application base URL."""

from __future__ import annotations

import os
from urllib.parse import urlparse


def get_client_app_base() -> str:
    """Return the normalized client app base URL."""

    base_url = os.getenv("CLIENT_APP_BASE")
    if not base_url:
        raise ValueError("CLIENT_APP_BASE is required to build client app links")
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    if "localhost" in hostname or hostname in {"127.0.0.1", "::1"}:
        raise ValueError("CLIENT_APP_BASE must not point to localhost")
    return normalized
