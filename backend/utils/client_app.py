"""Helpers for resolving the client application base URL."""

from __future__ import annotations

import os


def get_client_app_base() -> str:
    """Return the normalized client app base URL."""

    base_url = os.getenv("CLIENT_APP_BASE")
    if not base_url:
        raise ValueError("CLIENT_APP_BASE is required to build client app links")
    return base_url.rstrip("/")
