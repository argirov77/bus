"""Helpers for logging and throttling public ticket link requests."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from fastapi import HTTPException, Request

from ..auth import RequestContext

logger = logging.getLogger("backend.public_access")


# Rate limiting parameters (can be monkeypatched in tests)
RATE_LIMIT_MAX_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_BURST = 3
RATE_LIMIT_DELAY_SECONDS = 0.25


@dataclass
class _RateLimitEntry:
    count: int
    window_start: float


_rate_limit_store: dict[str, _RateLimitEntry] = {}
_rate_limit_lock = Lock()
_time_fn = time.monotonic
_sleep_fn = time.sleep


def reset_rate_limit_state() -> None:
    """Clear rate limit counters (useful for tests)."""

    with _rate_limit_lock:
        _rate_limit_store.clear()


def _enforce_rate_limit(key: str) -> None:
    """Check rate limit counters for the provided key."""

    now = _time_fn()
    with _rate_limit_lock:
        entry = _rate_limit_store.get(key)
        if entry and now - entry.window_start <= RATE_LIMIT_WINDOW_SECONDS:
            entry.count += 1
        else:
            entry = _RateLimitEntry(count=1, window_start=now)
        _rate_limit_store[key] = entry
        count = entry.count

    if count > RATE_LIMIT_MAX_REQUESTS:
        delay = RATE_LIMIT_DELAY_SECONDS * min(count - RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_BURST)
        if delay > 0:
            _sleep_fn(delay)
        if count > RATE_LIMIT_MAX_REQUESTS + RATE_LIMIT_BURST:
            raise HTTPException(status_code=429, detail="Too many requests")


def _extract_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def guard_public_request(
    request: Request,
    scope: str,
    *,
    ticket_id: Optional[int] = None,
    purchase_id: Optional[int] = None,
    context: Optional[RequestContext] = None,
) -> None:
    """Log public access details and apply a lightweight rate limit."""

    ip = _extract_ip(request)
    token_id: Optional[str] = None
    if context and not context.is_admin:
        token_id = context.jti
    elif context and context.is_admin:
        token_id = "admin"
    else:
        token_id = request.headers.get("X-Ticket-Token") or None

    rate_key = token_id or ip or "unknown"
    _enforce_rate_limit(f"{scope}:{rate_key}")

    logger.info(
        "Public access scope=%s ip=%s token=%s ticket_id=%s purchase_id=%s",
        scope,
        ip,
        token_id or "-",
        ticket_id,
        purchase_id,
    )


__all__ = [
    "guard_public_request",
    "reset_rate_limit_state",
]
