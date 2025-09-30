from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse, Response

from ..database import get_connection
from ..services import link_sessions
from ..services.access_guard import guard_public_request
from ..services.ticket_dto import get_ticket_dto
from ..services.ticket_pdf import render_ticket_pdf
from ._ticket_link_helpers import build_deep_link

session_router = APIRouter(tags=["public"])
router = APIRouter(prefix="/public", tags=["public"])


def _redirect_base_url(ticket_id: int) -> str:
    return f"http://localhost:3001/ticket/{ticket_id}"


def _require_view_session(request: Request, ticket_id: int | None = None) -> link_sessions.LinkSession:
    session_id = request.cookies.get("minicab")
    if not session_id:
        raise HTTPException(status_code=401, detail="Missing ticket session")

    session = link_sessions.get_session(
        session_id,
        scope="view",
        require_redeemed=True,
    )
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    now = datetime.now(timezone.utc)
    if session.exp <= now:
        raise HTTPException(status_code=401, detail="Session expired")

    if ticket_id is not None and session.ticket_id != ticket_id:
        raise HTTPException(status_code=403, detail="Session does not match ticket")

    return session


@session_router.get("/q/{opaque}")
def exchange_qr_session(opaque: str, request: Request) -> RedirectResponse:
    guard_public_request(request, "qr_exchange")
    session = link_sessions.redeem_session(opaque, scope="view")
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(timezone.utc)
    if session.exp <= now:
        raise HTTPException(status_code=410, detail="Session expired")

    guard_public_request(request, "qr_exchange", ticket_id=session.ticket_id)

    remaining = int((session.exp - now).total_seconds())
    if remaining <= 0:
        remaining = 60

    response = RedirectResponse(
        url=_redirect_base_url(session.ticket_id),
        status_code=302,
    )
    response.set_cookie(
        "minicab",
        session.jti,
        max_age=remaining,
        httponly=True,
        samesite="lax",
        path="/",
        domain="localhost",
    )
    return response


@router.get("/tickets/{ticket_id}")
def get_public_ticket(ticket_id: int, request: Request) -> Any:
    session = _require_view_session(request, ticket_id)
    guard_public_request(request, "ticket_view", ticket_id=ticket_id)

    link_sessions.touch_session_usage(session.jti, scope="view")

    conn = get_connection()
    try:
        try:
            dto = get_ticket_dto(ticket_id, "bg", conn)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Ticket not found") from exc
    finally:
        conn.close()

    return jsonable_encoder(dto)


@router.get("/tickets/{ticket_id}/pdf")
def get_public_ticket_pdf(ticket_id: int, request: Request) -> Response:
    session = _require_view_session(request, ticket_id)
    guard_public_request(request, "ticket_pdf", ticket_id=ticket_id)

    link_sessions.touch_session_usage(session.jti, scope="view")

    conn = get_connection()
    try:
        try:
            dto = get_ticket_dto(ticket_id, "bg", conn)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Ticket not found") from exc
    finally:
        conn.close()

    deep_link = build_deep_link(session.jti)
    pdf_bytes = render_ticket_pdf(dto, deep_link)

    headers = {
        "Content-Disposition": f'inline; filename="ticket-{ticket_id}.pdf"',
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


__all__ = ["router", "session_router"]
