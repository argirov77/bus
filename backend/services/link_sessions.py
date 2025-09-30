from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Tuple

from ..database import get_connection

_DEFAULT_TTL_DAYS = 7


@dataclass(frozen=True)
class LinkSession:
    jti: str
    ticket_id: int
    purchase_id: Optional[int]
    scope: str
    exp: datetime
    redeemed: Optional[datetime]
    used: Optional[datetime]
    revoked: Optional[datetime]
    created_at: datetime


_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_schema(connection) -> None:
    """Ensure the ``link_sessions`` table exists."""

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
                    jti VARCHAR(255) PRIMARY KEY,
                    ticket_id INTEGER NOT NULL,
                    purchase_id INTEGER,
                    scope VARCHAR(32) NOT NULL,
                    exp TIMESTAMPTZ NOT NULL,
                    redeemed TIMESTAMPTZ,
                    used TIMESTAMPTZ,
                    revoked TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_link_sessions_ticket_scope
                    ON link_sessions (ticket_id, scope)
                    WHERE revoked IS NULL
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_link_sessions_purchase_scope
                    ON link_sessions (purchase_id, scope)
                    WHERE revoked IS NULL
                """
            )

        _SCHEMA_READY = True


def _normalize_departure(dt: datetime | None) -> datetime:
    if dt is None:
        return _utcnow()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_ttl_days() -> int:
    raw = os.getenv("LINK_SESSION_TTL_DAYS") or os.getenv("TICKET_LINK_TTL_DAYS")
    if not raw:
        return _DEFAULT_TTL_DAYS
    try:
        ttl = int(raw)
    except ValueError:
        return _DEFAULT_TTL_DAYS
    return max(ttl, 1)


def _compute_expiration(departure_dt: datetime | None) -> datetime:
    now = _utcnow()
    ttl_days = _get_ttl_days()
    expiry_limit = now + timedelta(days=ttl_days)
    if departure_dt is None:
        return expiry_limit
    normalized = _normalize_departure(departure_dt)
    return min(normalized + timedelta(days=1), expiry_limit)


def _generate_opaque() -> str:
    # 24 bytes -> 192 bits of entropy. base64 url-safe without padding.
    return secrets.token_urlsafe(24)


def _row_to_session(row) -> LinkSession:
    return LinkSession(
        jti=row[0],
        ticket_id=row[1],
        purchase_id=row[2],
        scope=row[3],
        exp=row[4],
        redeemed=row[5],
        used=row[6],
        revoked=row[7],
        created_at=row[8],
    )


def _select_active_session(
    connection,
    *,
    ticket_id: int,
    scope: str,
) -> Optional[Tuple[str, datetime]]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT jti, exp
              FROM link_sessions
             WHERE ticket_id = %s
               AND scope = %s
               AND revoked IS NULL
               AND exp > NOW()
             ORDER BY exp DESC
             LIMIT 1
            """,
            (ticket_id, scope),
        )
        row = cur.fetchone()
    if not row:
        return None
    return row[0], row[1]


def _insert_session(
    connection,
    *,
    ticket_id: int,
    purchase_id: int | None,
    scope: str,
    exp: datetime,
) -> Tuple[str, datetime]:
    opaque = _generate_opaque()
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO link_sessions (jti, ticket_id, purchase_id, scope, exp)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING jti, exp
            """,
            (opaque, ticket_id, purchase_id, scope, exp),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("Failed to create link session")
    return row[0], row[1]


def get_or_create_view_session(
    ticket_id: int,
    *,
    purchase_id: int | None,
    lang: str,
    departure_dt: datetime | None,
    scopes: Iterable[str] | None = None,
    conn=None,
) -> Tuple[str, datetime]:
    if ticket_id <= 0:
        raise ValueError("ticket_id must be positive")

    owns_connection = conn is None
    connection = conn or get_connection()

    try:
        _ensure_schema(connection)
        existing = _select_active_session(connection, ticket_id=ticket_id, scope="view")
        if existing:
            return existing

        exp = _compute_expiration(departure_dt)
        opaque, expires = _insert_session(
            connection,
            ticket_id=ticket_id,
            purchase_id=purchase_id,
            scope="view",
            exp=exp,
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


def redeem_session(
    opaque: str,
    *,
    scope: str | None = None,
    conn=None,
) -> Optional[LinkSession]:
    owns_connection = conn is None
    connection = conn or get_connection()
    try:
        _ensure_schema(connection)
        params = [opaque]
        condition = ""
        if scope:
            condition = " AND scope = %s"
            params.append(scope)
        with connection.cursor() as cur:
            cur.execute(
                f"""
                UPDATE link_sessions
                   SET redeemed = COALESCE(redeemed, NOW())
                 WHERE jti = %s{condition}
                   AND revoked IS NULL
                   AND exp > NOW()
                RETURNING jti, ticket_id, purchase_id, scope, exp, redeemed, used, revoked, created_at
                """,
                params,
            )
            row = cur.fetchone()
        if owns_connection:
            connection.commit()
        return _row_to_session(row) if row else None
    finally:
        if owns_connection:
            try:
                connection.close()
            except Exception:
                pass


def get_session(
    opaque: str,
    *,
    scope: str | None = None,
    require_redeemed: bool = False,
    conn=None,
) -> Optional[LinkSession]:
    owns_connection = conn is None
    connection = conn or get_connection()
    try:
        _ensure_schema(connection)
        params = [opaque]
        condition = ""
        if scope:
            condition = " AND scope = %s"
            params.append(scope)
        with connection.cursor() as cur:
            cur.execute(
                f"""
                SELECT jti, ticket_id, purchase_id, scope, exp, redeemed, used, revoked, created_at
                  FROM link_sessions
                 WHERE jti = %s{condition}
                   AND revoked IS NULL
                """,
                params,
            )
            row = cur.fetchone()
        if not row:
            return None
        session = _row_to_session(row)
        if session.exp <= _utcnow():
            return None
        if require_redeemed and session.redeemed is None:
            return None
        return session
    finally:
        if owns_connection:
            try:
                connection.close()
            except Exception:
                pass


def touch_session_usage(
    opaque: str,
    *,
    scope: str | None = None,
    conn=None,
) -> Optional[LinkSession]:
    owns_connection = conn is None
    connection = conn or get_connection()
    try:
        _ensure_schema(connection)
        params = [opaque]
        condition = ""
        if scope:
            condition = " AND scope = %s"
            params.append(scope)
        with connection.cursor() as cur:
            cur.execute(
                f"""
                UPDATE link_sessions
                   SET used = NOW()
                 WHERE jti = %s{condition}
                   AND revoked IS NULL
                   AND exp > NOW()
                RETURNING jti, ticket_id, purchase_id, scope, exp, redeemed, used, revoked, created_at
                """,
                params,
            )
            row = cur.fetchone()
        if owns_connection:
            connection.commit()
        return _row_to_session(row) if row else None
    finally:
        if owns_connection:
            try:
                connection.close()
            except Exception:
                pass


__all__ = [
    "get_or_create_view_session",
    "redeem_session",
    "get_session",
    "touch_session_usage",
    "LinkSession",
]
