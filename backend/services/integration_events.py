from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from ..database import get_connection

_SENSITIVE_KEYS = {
    "token", "access_token", "refresh_token", "secret", "password", "signature",
    "authorization", "auth", "api_key", "private_key", "card", "pan", "cvv", "cvc",
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if any(s in key.lower() for s in _SENSITIVE_KEYS):
                out[key] = "***"
            else:
                out[key] = _sanitize(v)
        return out
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize(v) for v in value]
    if isinstance(value, (datetime, Decimal)):
        return str(value)
    return value


def record_event(
    *,
    provider: str,
    event_type: str,
    status: str,
    purchase_id: int | None = None,
    ticket_id: int | None = None,
    external_id: str | None = None,
    payload: Any | None = None,
    error_message: str | None = None,
) -> None:
    payload_json = json.dumps(_sanitize(payload), ensure_ascii=False) if payload is not None else None
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO integration_events
              (provider, event_type, purchase_id, ticket_id, external_id, status, payload_json, error_message, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """,
            (provider, event_type, purchase_id, ticket_id, external_id, status, payload_json, error_message),
        )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
