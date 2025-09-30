from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from fastapi import HTTPException, Request

from ..database import get_connection
from . import link_sessions

_PURCHASE_COOKIE_PREFIX = "minicab_purchase_"


@dataclass
class PurchaseSessionContext:
    """Information about the current purchase session resolved from cookies."""

    session: link_sessions.LinkSession
    ticket_id: int
    purchase_id: int
    cookie_name: str
    cookie_value: str


def _iter_purchase_cookies(request: Request) -> Iterable[tuple[int, str, str]]:
    cookies = request.cookies or {}
    for key, value in cookies.items():
        if not key.startswith(_PURCHASE_COOKIE_PREFIX):
            continue
        if not value:
            continue
        suffix = key[len(_PURCHASE_COOKIE_PREFIX) :]
        if not suffix.isdigit():
            continue
        yield int(suffix), key, value


def _resolve_purchase_id(session: link_sessions.LinkSession, *, conn) -> int:
    if session.purchase_id:
        return int(session.purchase_id)
    with conn.cursor() as cur:
        cur.execute("SELECT purchase_id FROM ticket WHERE id = %s", (session.ticket_id,))
        row = cur.fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Purchase not found for ticket")
    return int(row[0])


def _ensure_ticket_belongs(ticket_id: int, purchase_id: int, *, conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT purchase_id FROM ticket WHERE id = %s", (ticket_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    found_purchase_id = row[0]
    if not found_purchase_id or int(found_purchase_id) != purchase_id:
        raise HTTPException(status_code=403, detail="Ticket not part of purchase")


def ensure_purchase_session(
    request: Request,
    *,
    required_purchase_id: int | None = None,
    required_ticket_id: int | None = None,
) -> PurchaseSessionContext:
    """Validate cookies and return the current purchase session context."""

    cookies = list(_iter_purchase_cookies(request))
    if not cookies:
        raise HTTPException(status_code=401, detail="Missing purchase session")

    cookie_purchase_ids = {purchase_id for purchase_id, _name, _value in cookies}
    selected = None
    if required_purchase_id is not None:
        if required_purchase_id not in cookie_purchase_ids:
            # Pick deterministic cookie so we can provide a helpful error message.
            selected = cookies[0]
        else:
            for purchase_id, name, value in cookies:
                if purchase_id == required_purchase_id:
                    selected = (purchase_id, name, value)
                    break
    if selected is None:
        if len(cookies) > 1 and required_purchase_id is None:
            raise HTTPException(status_code=400, detail="Ambiguous purchase session")
        selected = cookies[0]

    purchase_id_hint, cookie_name, cookie_value = selected

    session = link_sessions.get_session(
        cookie_value,
        scope="view",
        require_redeemed=True,
    )
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    now = datetime.now(timezone.utc)
    if session.exp <= now:
        raise HTTPException(status_code=401, detail="Session expired")

    conn = get_connection()
    try:
        resolved_purchase_id = _resolve_purchase_id(session, conn=conn)
        if required_purchase_id is not None and resolved_purchase_id != required_purchase_id:
            raise HTTPException(status_code=403, detail="Session does not match purchase")
        if required_ticket_id is not None and required_ticket_id != session.ticket_id:
            _ensure_ticket_belongs(required_ticket_id, resolved_purchase_id, conn=conn)

        if purchase_id_hint != resolved_purchase_id:
            # Cookie name is derived from purchase id; ensure we use the canonical id.
            cookie_name = f"{_PURCHASE_COOKIE_PREFIX}{resolved_purchase_id}"

        link_sessions.touch_session_usage(session.jti, scope="view", conn=conn)
    finally:
        conn.close()

    return PurchaseSessionContext(
        session=session,
        ticket_id=session.ticket_id,
        purchase_id=resolved_purchase_id,
        cookie_name=cookie_name,
        cookie_value=cookie_value,
    )


def get_request_session(request: Request) -> PurchaseSessionContext:
    context = getattr(request.state, "purchase_session", None)
    if not isinstance(context, PurchaseSessionContext):
        raise HTTPException(status_code=401, detail="Missing purchase session")
    return context


__all__ = [
    "PurchaseSessionContext",
    "ensure_purchase_session",
    "get_request_session",
    "_PURCHASE_COOKIE_PREFIX",
]
