"""Helpers for resolving the client application base URL."""

from __future__ import annotations

import os
from urllib.parse import urlparse


def get_client_app_base() -> str:
    """Return the normalized client app base URL."""

    base_url = os.getenv("CLIENT_APP_BASE") or os.getenv("APP_PUBLIC_URL")
    if not base_url:
        raise ValueError(
            "CLIENT_APP_BASE is required to build client app links (or set APP_PUBLIC_URL)"
        )
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    if "localhost" in hostname or hostname in {"127.0.0.1", "::1"}:
        raise ValueError("CLIENT_APP_BASE must not point to localhost")
    return normalized


def get_client_app_base_https() -> str:
    """Return client base URL and enforce HTTPS for payment provider callbacks."""

    base_url = get_client_app_base()
    parsed = urlparse(base_url)
    if parsed.scheme.lower() != "https":
        raise ValueError("CLIENT_APP_BASE must use https for LiqPay URLs")
    return base_url


def build_purchase_result_url(_purchase_id: int) -> str:
    """Build a canonical LiqPay return URL in client app."""

    return f"{get_client_app_base_https()}/return"


def build_liqpay_server_url() -> str:
    """Build a public callback URL for LiqPay server notifications."""

    return f"{get_client_app_base_https()}/api/public/payment/liqpay/callback"
