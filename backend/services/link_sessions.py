"""Utilities for managing short-lived ticket link sessions."""

from __future__ import annotations
import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Iterable, Tuple

import jwt

from ..database import get_connection
from . import ticket_links


_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()


def _ensure_schema(connection) -> None:
    """Create the ``link_sessions`` table on demand."""

    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return

        with connection.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS link_sessions (
                    id SERIAL PRIMARY KEY,
                    ticket_id INTEGER NOT NULL,
                    scope VARCHAR(32) NOT NULL,
                    opaque VARCHAR(128) NOT NULL UNIQUE,
                    token TEXT NOT NULL,
                    jti UUID NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    revoked_at TIMESTAMPTZ
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_link_sessions_ticket_scope
                    ON link_sessions (ticket_id, scope)
                    WHERE revoked_at IS NULL
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_link_sessions_jti
                    ON link_sessions (jti)
                """
            )

        _SCHEMA_READY = True


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_departure(dt: datetime | None) -> datetime:
    if dt is None:
        return _utcnow()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _decode_payload(token: str) -> tuple[str, datetime | None]:
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return "", None

    jti = str(payload.get("jti") or "")
    exp_value = payload.get("exp")
    expires_at: datetime | None = None
    if isinstance(exp_value, (int, float)):
        expires_at = datetime.fromtimestamp(int(exp_value), tz=timezone.utc)

    return jti, expires_at


def _opaque_from_jti(jti: str) -> str:
    cleaned = "".join(ch for ch in jti if ch.isalnum())
    if cleaned:
        return cleaned.lower()
    return secrets.token_urlsafe(18)


def _insert_session(
    connection,
    *,
    ticket_id: int,
    scope: str,
    token: str,
    jti: str,
    expires_at: datetime,
) -> Tuple[str, datetime]:
    opaque = _opaque_from_jti(jti)
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO link_sessions (ticket_id, scope, opaque, token, jti, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING opaque, expires_at
            """,
            (ticket_id, scope, opaque, token, jti, expires_at),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("Failed to create link session")
    return row[0], row[1]


def _select_active_session(connection, *, ticket_id: int, scope: str) -> tuple[str, datetime] | None:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT opaque, expires_at
              FROM link_sessions
             WHERE ticket_id = %s
               AND scope = %s
               AND revoked_at IS NULL
               AND expires_at > NOW()
             ORDER BY expires_at DESC
             LIMIT 1
            """,
            (ticket_id, scope),
        )
        row = cur.fetchone()
    if not row:
        return None
    return row[0], row[1]


def get_or_create_view_session(
    ticket_id: int,
    *,
    purchase_id: int | None,
    lang: str,
    departure_dt: datetime | None,
    scopes: Iterable[str] | None = None,
    conn=None,
) -> tuple[str, datetime]:
    """Return an opaque identifier for the ticket view session."""

    if ticket_id <= 0:
        raise ValueError("ticket_id must be positive")

    lang_value = (lang or "bg").lower()
    actual_scopes = tuple(scopes or ("view",))
    departure_value = _normalize_departure(departure_dt)

    owns_connection = conn is None
    connection = conn or get_connection()

    try:
        _ensure_schema(connection)

        existing = _select_active_session(connection, ticket_id=ticket_id, scope="view")
        if existing:
            return existing

        token = ticket_links.issue(
            ticket_id=ticket_id,
            purchase_id=purchase_id,
            scopes=actual_scopes,
            lang=lang_value,
            departure_dt=departure_value,
            conn=connection,
        )

        jti, token_exp = _decode_payload(token)
        if not jti:
            jti = str(uuid.uuid4())

        expires_at = token_exp or departure_value

        opaque, expires = _insert_session(
            connection,
            ticket_id=ticket_id,
            scope="view",
            token=token,
            jti=jti,
            expires_at=expires_at,
        )

        if owns_connection:
            connection.commit()
        return opaque, expires
    finally:
        if owns_connection:
            try:
                connection.close()
            except Exception:
                pass


__all__ = ["get_or_create_view_session"]

