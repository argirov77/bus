"""Telegram notification service for staff chat notifications."""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_TELEGRAM_API_URL = "https://api.telegram.org"
_HTTP_TIMEOUT = 5.0


def is_enabled() -> bool:
    """Return True if Telegram notifications are configured and enabled."""
    if os.getenv("TELEGRAM_ENABLED", "false").strip().lower() not in {"true", "1", "yes"}:
        return False
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def send_message(text: str, parse_mode: Optional[str] = "HTML") -> bool:
    """Send a message to the configured Telegram chat.

    Returns True on success, False otherwise. Never raises — failures are
    logged so they do not break the main request flow.
    """
    if not is_enabled():
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    api_url = os.getenv("TELEGRAM_API_URL", _TELEGRAM_API_URL).rstrip("/")

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    url = f"{api_url}/bot{token}/sendMessage"
    try:
        response = httpx.post(url, data=payload, timeout=_HTTP_TIMEOUT)
        if response.status_code >= 400:
            logger.error(
                "Telegram sendMessage failed: status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            return False
        return True
    except Exception:
        logger.exception("Telegram sendMessage raised an exception")
        return False
