from __future__ import annotations

import logging
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..database import get_connection

logger = logging.getLogger(__name__)

_DEFAULT_CHALLENGE_TTL_MINUTES = 10
_DEFAULT_TOKEN_TTL_MINUTES = 15


@dataclass
class OTPChallenge:
    id: str
    ticket_id: int
    purchase_id: Optional[int]
    action: str
    code: str
    exp: datetime
    attempts: int
    verified_at: Optional[datetime]
    created_at: datetime


@dataclass
class OperationToken:
    token: str
    ticket_id: int
    purchase_id: Optional[int]
    action: str
    exp: datetime
    created_at: datetime
    used_at: Optional[datetime]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _generate_token() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(48))


def create_challenge(
    ticket_id: int,
    purchase_id: int | None,
    action: str,
    *,
    conn=None,
    ttl_minutes: int = _DEFAULT_CHALLENGE_TTL_MINUTES,
) -> OTPChallenge:
    owns_connection = conn is None
    connection = conn or get_connection()
    try:
        _ensure_schema(connection)
        challenge_id = str(uuid.uuid4())
        code = _generate_code()
        exp = _utcnow() + timedelta(minutes=ttl_minutes)
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO otp_challenge (id, ticket_id, purchase_id, action, code, exp)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, ticket_id, purchase_id, action, code, exp, attempts, verified_at, created_at
                """,
                (challenge_id, ticket_id, purchase_id, action, code, exp),
            )
            row = cur.fetchone()
        if owns_connection:
            connection.commit()
        return OTPChallenge(*row)
    finally:
        if owns_connection:
            connection.close()


def verify_challenge(
    challenge_id: str,
    code: str,
    *,
    conn=None,
    ttl_minutes: int = _DEFAULT_TOKEN_TTL_MINUTES,
    ticket_id: int | None = None,
) -> OperationToken | None:
    owns_connection = conn is None
    connection = conn or get_connection()
    try:
        _ensure_schema(connection)
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT id, ticket_id, purchase_id, action, code, exp, attempts, verified_at, created_at
                  FROM otp_challenge
                 WHERE id = %s
                """,
                (challenge_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            challenge = OTPChallenge(*row)
            if ticket_id is not None and challenge.ticket_id != ticket_id:
                return None
            now = _utcnow()
            if challenge.exp <= now:
                return None
            if challenge.verified_at is not None:
                cur.execute(
                    """
                    SELECT token, ticket_id, purchase_id, action, exp, created_at, used_at
                      FROM op_token
                     WHERE ticket_id = %s
                       AND action = %s
                       AND used_at IS NULL
                       AND exp > NOW()
                     ORDER BY exp DESC
                     LIMIT 1
                    """,
                    (challenge.ticket_id, challenge.action),
                )
                token_row = cur.fetchone()
                if token_row:
                    return OperationToken(*token_row)
                return None
            if challenge.code != code:
                cur.execute(
                    "UPDATE otp_challenge SET attempts = attempts + 1 WHERE id = %s",
                    (challenge_id,),
                )
                connection.commit()
                return None
            token_value = _generate_token()
            token_exp = now + timedelta(minutes=ttl_minutes)
            cur.execute(
                """
                INSERT INTO op_token (token, ticket_id, purchase_id, action, exp)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING token, ticket_id, purchase_id, action, exp, created_at, used_at
                """,
                (token_value, challenge.ticket_id, challenge.purchase_id, challenge.action, token_exp),
            )
            token_row = cur.fetchone()
            cur.execute(
                "UPDATE otp_challenge SET verified_at = %s WHERE id = %s",
                (now, challenge_id),
            )
        if owns_connection:
            connection.commit()
        return OperationToken(*token_row)
    finally:
        if owns_connection:
            connection.close()


def consume_op_token(token: str, action: str, ticket_id: int, *, conn=None) -> bool:
    owns_connection = conn is None
    connection = conn or get_connection()
    try:
        _ensure_schema(connection)
        with connection.cursor() as cur:
            cur.execute(
                """
                UPDATE op_token
                   SET used_at = NOW()
                 WHERE token = %s
                   AND action = %s
                   AND ticket_id = %s
                   AND used_at IS NULL
                   AND exp > NOW()
                RETURNING token
                """,
                (token, action, ticket_id),
            )
            row = cur.fetchone()
        if owns_connection:
            connection.commit()
        return bool(row)
    finally:
        if owns_connection:
            connection.close()


def validate_op_token(token: str, action: str, ticket_id: int, *, conn=None) -> bool:
    owns_connection = conn is None
    connection = conn or get_connection()
    try:
        _ensure_schema(connection)
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                  FROM op_token
                 WHERE token = %s
                   AND action = %s
                   AND ticket_id = %s
                   AND used_at IS NULL
                   AND exp > NOW()
                """,
                (token, action, ticket_id),
            )
            row = cur.fetchone()
        return bool(row)
    finally:
        if owns_connection:
            connection.close()


__all__ = [
    "create_challenge",
    "verify_challenge",
    "consume_op_token",
    "validate_op_token",
    "OTPChallenge",
    "OperationToken",
]
