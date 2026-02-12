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


def build_purchase_result_url(purchase_id: int) -> str:
    """Build a canonical client result URL for a purchase."""

    return f"{get_client_app_base()}/purchase/{int(purchase_id)}"


def build_liqpay_result_url() -> str:
    """Build the URL where LiqPay should redirect the customer."""

    return f"{get_client_app_base()}/return"


def build_liqpay_server_url() -> str:
    """Build the public callback URL that LiqPay can call."""

    return f"{get_client_app_base()}/api/public/payment/liqpay/callback"
