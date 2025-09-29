"""Utilities for issuing and verifying ticket access links."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable

import jwt


class TicketLinkError(Exception):
    """Base class for ticket link errors."""


class SecretNotConfigured(TicketLinkError):
    """Raised when the ticket link secret is missing."""


class TokenNotFound(TicketLinkError):
    """Raised when a token jti is not present in the blacklist table."""


class TokenRevoked(TicketLinkError):
    """Raised when a token has been explicitly revoked."""


class TokenExpired(TicketLinkError):
    """Raised when a token is expired."""


class TokenInvalid(TicketLinkError):
    """Raised when the JWT payload is invalid."""


@dataclass
class TicketLinkPayload:
    ticket_id: int
    purchase_id: int | None
    scopes: Iterable[str]
    lang: str
    exp: int
    jti: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "purchase_id": self.purchase_id,
            "scopes": list(self.scopes),
            "lang": self.lang,
            "exp": self.exp,
            "jti": self.jti,
        }


DEFAULT_TTL_DAYS = 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_connection():
    from backend import database

    return database.get_connection()


def _ensure_secret() -> str:
    secret = os.getenv("TICKET_LINK_SECRET")
    if not secret:
        secret = "dev-ticket-secret"
    return secret


def _get_ttl_days() -> int:
    raw = os.getenv("TICKET_LINK_TTL_DAYS")
    if not raw:
        return DEFAULT_TTL_DAYS
    try:
        ttl = int(raw)
    except ValueError as exc:
        raise TicketLinkError("TICKET_LINK_TTL_DAYS must be an integer") from exc
    if ttl <= 0:
        raise TicketLinkError("TICKET_LINK_TTL_DAYS must be positive")
    return ttl


def _normalize_departure(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _compute_expiration(departure_dt: datetime) -> tuple[int, datetime]:
    now = _utcnow()
    departure_aware = _normalize_departure(departure_dt)
    ttl_days = _get_ttl_days()
    exp_dt = min(
        departure_aware + timedelta(days=1),
        now + timedelta(days=ttl_days),
    )
    # JWT exp should be an int timestamp (seconds)
    exp_ts = int(exp_dt.timestamp())
    return exp_ts, exp_dt


def issue(
    ticket_id: int,
    purchase_id: int | None,
    scopes: Iterable[str],
    lang: str,
    departure_dt: datetime,
    *,
    conn=None,
) -> str:
    """Issue a signed JWT for accessing ticket resources.

    When ``conn`` is provided the caller is responsible for managing the
    surrounding transaction (commit/rollback and connection closing). This
    allows callers that already operate inside a transaction to keep token
    issuance atomic with the rest of the purchase workflow.
    """

    secret = _ensure_secret()
    exp_ts, exp_dt = _compute_expiration(departure_dt)
    jti = str(uuid.uuid4())
    payload = TicketLinkPayload(
        ticket_id=ticket_id,
        purchase_id=purchase_id,
        scopes=scopes,
        lang=lang,
        exp=exp_ts,
        jti=jti,
    )

    token = jwt.encode(payload.to_dict(), secret, algorithm="HS256")

    owns_connection = conn is None
    connection = conn or _get_connection()
    cur = connection.cursor()
    try:
        cur.execute(
            """
            UPDATE ticket_link_tokens
               SET revoked_at = NOW()
             WHERE ticket_id = %s
               AND revoked_at IS NULL
            """,
            (ticket_id,),
        )
        cur.execute(
            """
            INSERT INTO ticket_link_tokens (
                jti, ticket_id, purchase_id, scopes, lang, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                jti,
                ticket_id,
                purchase_id,
                json.dumps(list(scopes)),
                lang,
                exp_dt,
            ),
        )
        if owns_connection:
            connection.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        if owns_connection:
            connection.close()

    return token


def verify(token: str) -> Dict[str, Any]:
    """Verify a ticket link JWT and return its payload."""

    secret = _ensure_secret()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={
                "require": ["exp", "jti", "ticket_id", "scopes", "lang"],
                "verify_exp": False,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired("Token signature has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalid("Invalid token") from exc

    jti = payload.get("jti")
    if not jti:
        raise TokenInvalid("Token missing jti")

    now = _utcnow()

    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT revoked_at, expires_at
                FROM ticket_link_tokens
                WHERE jti = %s
                """,
                (jti,),
            )
            row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    if not row:
        raise TokenNotFound("Token not found")

    revoked_at, expires_at = row

    if revoked_at is not None:
        raise TokenRevoked("Token has been revoked")

    try:
        exp_ts = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenInvalid("Token has invalid exp") from exc

    if exp_ts <= int(now.timestamp()):
        raise TokenExpired("Token has expired")

    expires_at = _normalize_departure(expires_at)
    if expires_at <= now:
        raise TokenExpired("Token has expired")

    return payload


def revoke(jti: str) -> bool:
    """Mark the provided token identifier as revoked.

    Returns True if a token record was updated.
    """

    if not jti:
        return False

    conn = _get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE ticket_link_tokens
               SET revoked_at = NOW()
             WHERE jti = %s
               AND revoked_at IS NULL
            """,
            (jti,),
        )
        cur.execute(
            "SELECT revoked_at, expires_at FROM ticket_link_tokens WHERE jti = %s",
            (jti,),
        )
        updated_row = cur.fetchone()
        updated = 1 if updated_row and updated_row[0] is not None else 0
        conn.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()

    return updated > 0
