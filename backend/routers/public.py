from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from ..database import get_connection
from ..services import link_sessions, otp
from ..services.access_guard import guard_public_request
from ..services.email import send_otp_email
from ..services.ticket_dto import get_ticket_dto
from ..services.ticket_pdf import render_ticket_pdf
from ..ticket_utils import free_ticket, recalc_available
from ._ticket_link_helpers import build_deep_link

session_router = APIRouter(tags=["public"])
router = APIRouter(prefix="/public", tags=["public"])

_COOKIE_PREFIX = "minicab_"
_DEFAULT_LANG = "bg"


class OTPStartRequest(BaseModel):
    action: str = Field(..., pattern=r"^(pay|reschedule|cancel)$")
    ticket_id: int = Field(..., gt=0)


class OTPStartResponse(BaseModel):
    challenge_id: str
    ttl_sec: int


class OTPVerifyRequest(BaseModel):
    challenge_id: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)


class OTPVerifyResponse(BaseModel):
    ok: bool
    op_token: str


class OperationTokenIn(BaseModel):
    op_token: str = Field(..., min_length=1)


class RescheduleRequest(OperationTokenIn):
    new_tour_id: int = Field(..., gt=0)


def _redirect_base_url(ticket_id: int) -> str:
    return f"http://localhost:3001/ticket/{ticket_id}"


def _cookie_name(ticket_id: int) -> str:
    return f"{_COOKIE_PREFIX}{ticket_id}"


def _extract_session_cookie(request: Request, ticket_id: int | None = None) -> tuple[int, str, str]:
    cookies = request.cookies or {}
    if ticket_id is not None:
        name = _cookie_name(ticket_id)
        value = cookies.get(name)
        if not value:
            raise HTTPException(status_code=401, detail="Missing ticket session")
        return ticket_id, name, value

    matches: list[tuple[int, str, str]] = []
    for key, value in cookies.items():
        if not key.startswith(_COOKIE_PREFIX) or not value:
            continue
        suffix = key[len(_COOKIE_PREFIX) :]
        if not suffix.isdigit():
            continue
        matches.append((int(suffix), key, value))

    if not matches:
        raise HTTPException(status_code=401, detail="Missing ticket session")
    if len(matches) > 1:
        raise HTTPException(status_code=400, detail="Ambiguous ticket session")
    return matches[0]


def _require_view_session(
    request: Request, ticket_id: int | None = None
) -> tuple[link_sessions.LinkSession, int, str]:
    resolved_ticket_id, cookie_name, session_id = _extract_session_cookie(request, ticket_id)

    session = link_sessions.get_session(
        session_id,
        scope="view",
        require_redeemed=True,
    )
    if not session or session.ticket_id != resolved_ticket_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    now = datetime.now(timezone.utc)
    if session.exp <= now:
        raise HTTPException(status_code=401, detail="Session expired")

    return session, resolved_ticket_id, cookie_name


def _load_ticket_dto(ticket_id: int, lang: str = _DEFAULT_LANG) -> Mapping[str, Any]:
    conn = get_connection()
    try:
        try:
            return get_ticket_dto(ticket_id, lang, conn)
        except ValueError as exc:  # pragma: no cover - defensive logging
            raise HTTPException(status_code=404, detail="Ticket not found") from exc
    finally:
        conn.close()


def _build_liqpay_payload(ticket_id: int, purchase_id: int, amount: float) -> dict[str, Any]:
    public_key = os.getenv("LIQPAY_PUBLIC_KEY", "sandbox")
    private_key = os.getenv("LIQPAY_PRIVATE_KEY", "sandbox")
    currency = os.getenv("LIQPAY_CURRENCY", "UAH")

    payload = {
        "version": "3",
        "public_key": public_key,
        "action": "pay",
        "amount": round(max(amount, 0.0), 2),
        "currency": currency,
        "description": f"Ticket #{ticket_id}",
        "order_id": f"ticket-{ticket_id}-{purchase_id}",
        "result_url": _redirect_base_url(ticket_id),
    }

    payload_json = json.dumps(payload, separators=(",", ":"))
    data = base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")
    signature_raw = f"{private_key}{data}{private_key}".encode("utf-8")
    signature = base64.b64encode(hashlib.sha1(signature_raw).digest()).decode("utf-8")

    return {
        "provider": "liqpay",
        "data": data,
        "signature": signature,
        "payload": payload,
    }


def _fetch_route_stops(cur, route_id: int) -> list[int]:
    cur.execute(
        'SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY "order"',
        (route_id,),
    )
    rows = cur.fetchall()
    if not rows:
        raise HTTPException(status_code=400, detail="Route has no stops configured")
    return [int(row[0]) for row in rows]


def _segments_between(
    stops: Iterable[int], departure_stop_id: int, arrival_stop_id: int
) -> tuple[list[str], list[tuple[int, int]]]:
    stops_list = list(stops)
    if departure_stop_id not in stops_list or arrival_stop_id not in stops_list:
        raise HTTPException(status_code=400, detail="Invalid stops for this route")
    idx_from = stops_list.index(departure_stop_id)
    idx_to = stops_list.index(arrival_stop_id)
    if idx_from >= idx_to:
        raise HTTPException(status_code=400, detail="Arrival must come after departure")
    tokens = [str(i + 1) for i in range(idx_from, idx_to)]
    pairs = [(stops_list[i], stops_list[i + 1]) for i in range(idx_from, idx_to)]
    return tokens, pairs


def _normalize_availability(avail: str | None) -> str:
    if not avail or avail == "0":
        return ""
    return avail


def _ensure_segments_available(avail: str | None, segments: Iterable[str]) -> None:
    base = _normalize_availability(avail)
    for segment in segments:
        if segment not in base:
            raise HTTPException(status_code=409, detail="Seat not available for the selected tour")


def _merge_available(avail: str | None, segments: Iterable[str]) -> str:
    base = _normalize_availability(avail)
    merged = sorted(set(base + "".join(segments)), key=int)
    return "".join(merged) if merged else "0"


def _remove_segments(avail: str | None, segments: Iterable[str]) -> str:
    base = _normalize_availability(avail)
    updated = "".join(ch for ch in base if ch not in set(segments))
    return updated or "0"


def _resolve_ticket_price(cur, tour_id: int, departure_stop_id: int, arrival_stop_id: int):
    cur.execute("SELECT pricelist_id FROM tour WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    if not row:
        return None
    pricelist_id = row[0]
    cur.execute(
        """
        SELECT price
          FROM prices
         WHERE pricelist_id = %s
           AND departure_stop_id = %s
           AND arrival_stop_id = %s
        """,
        (pricelist_id, departure_stop_id, arrival_stop_id),
    )
    price_row = cur.fetchone()
    return price_row[0] if price_row else None


def _perform_reschedule(
    cur,
    *,
    ticket_id: int,
    current_seat_id: int,
    target_tour_id: int,
    seat_num: int,
    departure_stop_id: int,
    arrival_stop_id: int,
) -> None:
    cur.execute("SELECT tour_id FROM seat WHERE id = %s", (current_seat_id,))
    seat_tour_row = cur.fetchone()
    if not seat_tour_row:
        raise HTTPException(status_code=404, detail="Seat not found")
    current_tour_id = int(seat_tour_row[0])

    cur.execute("SELECT route_id FROM tour WHERE id = %s", (current_tour_id,))
    current_route_row = cur.fetchone()
    if not current_route_row:
        raise HTTPException(status_code=404, detail="Tour not found")
    current_stops = _fetch_route_stops(cur, int(current_route_row[0]))
    current_segments, _ = _segments_between(current_stops, departure_stop_id, arrival_stop_id)

    cur.execute("SELECT available FROM seat WHERE id = %s FOR UPDATE", (current_seat_id,))
    current_avail_row = cur.fetchone()
    if not current_avail_row:
        raise HTTPException(status_code=404, detail="Seat not found")
    current_avail = current_avail_row[0]

    cur.execute("SELECT route_id FROM tour WHERE id = %s", (target_tour_id,))
    target_route_row = cur.fetchone()
    if not target_route_row:
        raise HTTPException(status_code=404, detail="Target tour not found")
    target_stops = _fetch_route_stops(cur, int(target_route_row[0]))
    target_segments, _ = _segments_between(target_stops, departure_stop_id, arrival_stop_id)

    cur.execute(
        "SELECT id, available FROM seat WHERE tour_id = %s AND seat_num = %s FOR UPDATE",
        (target_tour_id, seat_num),
    )
    target_seat_row = cur.fetchone()
    if not target_seat_row:
        raise HTTPException(status_code=404, detail="Seat not found on target tour")
    target_seat_id, target_avail = target_seat_row
    if target_avail == "0":
        raise HTTPException(status_code=409, detail="Seat is blocked on the selected tour")
    _ensure_segments_available(target_avail, target_segments)

    released_current_avail = _merge_available(current_avail, current_segments)
    updated_target_avail = _remove_segments(target_avail, target_segments)

    cur.execute(
        "UPDATE seat SET available = %s WHERE id = %s",
        (released_current_avail, current_seat_id),
    )
    cur.execute(
        "UPDATE seat SET available = %s WHERE id = %s",
        (updated_target_avail, target_seat_id),
    )
    cur.execute(
        """
        UPDATE ticket
           SET tour_id = %s,
               seat_id = %s
         WHERE id = %s
        """,
        (target_tour_id, target_seat_id, ticket_id),
    )

    recalc_available(cur, current_tour_id)
    if current_tour_id != target_tour_id:
        recalc_available(cur, target_tour_id)


@session_router.get("/q/{opaque}")
def exchange_qr_session(opaque: str, request: Request) -> RedirectResponse:
    guard_public_request(request, "qr_exchange")
    session = link_sessions.redeem_session(opaque, scope="view")
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(timezone.utc)
    if session.exp <= now:
        raise HTTPException(status_code=410, detail="Session expired")

    guard_public_request(
        request,
        "qr_exchange",
        ticket_id=session.ticket_id,
        purchase_id=session.purchase_id,
    )

    remaining = int((session.exp - now).total_seconds())
    if remaining <= 0:
        remaining = 60

    response = RedirectResponse(
        url=_redirect_base_url(session.ticket_id),
        status_code=302,
    )
    response.set_cookie(
        _cookie_name(session.ticket_id),
        session.jti,
        max_age=remaining,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/tickets/{ticket_id}")
def get_public_ticket(ticket_id: int, request: Request) -> Any:
    session, resolved_ticket_id, _cookie = _require_view_session(request, ticket_id)
    guard_public_request(
        request,
        "ticket_view",
        ticket_id=resolved_ticket_id,
        purchase_id=session.purchase_id,
    )

    link_sessions.touch_session_usage(session.jti, scope="view")

    dto = _load_ticket_dto(resolved_ticket_id, _DEFAULT_LANG)
    return jsonable_encoder(dto)


@router.get("/tickets/{ticket_id}/pdf")
def get_public_ticket_pdf(ticket_id: int, request: Request) -> Response:
    session, resolved_ticket_id, _cookie = _require_view_session(request, ticket_id)
    guard_public_request(
        request,
        "ticket_pdf",
        ticket_id=resolved_ticket_id,
        purchase_id=session.purchase_id,
    )

    link_sessions.touch_session_usage(session.jti, scope="view")

    dto = _load_ticket_dto(resolved_ticket_id, _DEFAULT_LANG)
    deep_link = build_deep_link(session.jti)
    pdf_bytes = render_ticket_pdf(dto, deep_link)

    headers = {
        "Content-Disposition": f'inline; filename="ticket-{resolved_ticket_id}.pdf"',
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.post("/otp/start", response_model=OTPStartResponse)
def start_otp_flow(data: OTPStartRequest, request: Request) -> OTPStartResponse:
    session, ticket_id, _cookie = _require_view_session(request, data.ticket_id)
    if data.ticket_id != ticket_id:
        raise HTTPException(status_code=403, detail="Session does not match ticket")

    guard_public_request(
        request,
        "otp_start",
        ticket_id=ticket_id,
        purchase_id=session.purchase_id,
    )
    link_sessions.touch_session_usage(session.jti, scope="view")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT purchase_id FROM ticket WHERE id = %s",
            (ticket_id,),
        )
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        purchase_id = ticket_row[0]

        dto = get_ticket_dto(ticket_id, _DEFAULT_LANG, conn)
        purchase_info = dto.get("purchase") if isinstance(dto, Mapping) else None
        customer = purchase_info.get("customer") if isinstance(purchase_info, Mapping) else None
        email = customer.get("email") if isinstance(customer, Mapping) else None
        if not email:
            raise HTTPException(status_code=400, detail="Ticket has no contact email")

        challenge = otp.create_challenge(
            ticket_id,
            purchase_id,
            data.action,
            conn=conn,
        )
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    ttl_seconds = max(int((challenge.exp - datetime.now(timezone.utc)).total_seconds()), 1)
    send_otp_email(email, challenge.code, lang=_DEFAULT_LANG)

    return OTPStartResponse(challenge_id=challenge.id, ttl_sec=ttl_seconds)


@router.post("/otp/verify", response_model=OTPVerifyResponse)
def verify_otp_code(data: OTPVerifyRequest, request: Request) -> OTPVerifyResponse:
    session, ticket_id, _cookie = _require_view_session(request)
    guard_public_request(
        request,
        "otp_verify",
        ticket_id=ticket_id,
        purchase_id=session.purchase_id,
    )
    link_sessions.touch_session_usage(session.jti, scope="view")

    token = otp.verify_challenge(
        data.challenge_id,
        data.code,
        ticket_id=ticket_id,
    )
    if not token:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    return OTPVerifyResponse(ok=True, op_token=token.token)


@router.post("/pay")
def public_pay(data: OperationTokenIn, request: Request) -> Mapping[str, Any]:
    session, ticket_id, _cookie = _require_view_session(request)
    guard_public_request(
        request,
        "pay",
        ticket_id=ticket_id,
        purchase_id=session.purchase_id,
    )
    link_sessions.touch_session_usage(session.jti, scope="view")

    conn = get_connection()
    cur = conn.cursor()
    try:
        if not otp.consume_op_token(data.op_token, "pay", ticket_id, conn=conn):
            raise HTTPException(status_code=400, detail="Invalid operation token")

        purchase_id = session.purchase_id
        if not purchase_id:
            cur.execute(
                "SELECT purchase_id FROM ticket WHERE id = %s",
                (ticket_id,),
            )
            row = cur.fetchone()
            purchase_id = row[0] if row else None
        if not purchase_id:
            raise HTTPException(status_code=400, detail="Ticket has no purchase")

        cur.execute(
            "SELECT amount_due FROM purchase WHERE id = %s",
            (purchase_id,),
        )
        purchase_row = cur.fetchone()
        if not purchase_row:
            raise HTTPException(status_code=404, detail="Purchase not found")
        amount_due = float(purchase_row[0] or 0)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return _build_liqpay_payload(ticket_id, int(purchase_id), amount_due)


@router.post("/reschedule")
def public_reschedule(data: RescheduleRequest, request: Request) -> Mapping[str, Any]:
    session, ticket_id, _cookie = _require_view_session(request)
    guard_public_request(
        request,
        "reschedule",
        ticket_id=ticket_id,
        purchase_id=session.purchase_id,
    )
    link_sessions.touch_session_usage(session.jti, scope="view")

    conn = get_connection()
    cur = conn.cursor()
    try:
        if not otp.validate_op_token(data.op_token, "reschedule", ticket_id, conn=conn):
            raise HTTPException(status_code=400, detail="Invalid operation token")

        cur.execute(
            """
            SELECT seat_id, tour_id, departure_stop_id, arrival_stop_id
              FROM ticket
             WHERE id = %s
             FOR UPDATE
            """,
            (ticket_id,),
        )
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        seat_id, current_tour_id, departure_stop_id, arrival_stop_id = ticket_row

        cur.execute("SELECT seat_num FROM seat WHERE id = %s", (seat_id,))
        seat_row = cur.fetchone()
        if not seat_row:
            raise HTTPException(status_code=404, detail="Seat not found")
        seat_num = int(seat_row[0])

        if current_tour_id == data.new_tour_id:
            if not otp.consume_op_token(data.op_token, "reschedule", ticket_id, conn=conn):
                raise HTTPException(status_code=400, detail="Operation token expired")
            conn.commit()
            return {
                "need_payment": False,
                "difference": 0.0,
                "ticket_id": ticket_id,
                "new_tour_id": current_tour_id,
            }

        current_price = _resolve_ticket_price(cur, current_tour_id, departure_stop_id, arrival_stop_id)
        target_price = _resolve_ticket_price(cur, data.new_tour_id, departure_stop_id, arrival_stop_id)
        if current_price is None or target_price is None:
            raise HTTPException(status_code=400, detail="Unable to calculate fare difference")

        difference_value = float(target_price - current_price)
        if difference_value > 0:
            conn.rollback()
            return {
                "need_payment": True,
                "difference": difference_value,
            }

        _perform_reschedule(
            cur,
            ticket_id=ticket_id,
            current_seat_id=seat_id,
            target_tour_id=data.new_tour_id,
            seat_num=seat_num,
            departure_stop_id=departure_stop_id,
            arrival_stop_id=arrival_stop_id,
        )

        if not otp.consume_op_token(data.op_token, "reschedule", ticket_id, conn=conn):
            raise HTTPException(status_code=400, detail="Operation token expired")

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return {
        "need_payment": False,
        "difference": difference_value,
        "ticket_id": ticket_id,
        "new_tour_id": data.new_tour_id,
    }


@router.post("/cancel")
def public_cancel(data: OperationTokenIn, request: Request) -> JSONResponse:
    session, ticket_id, cookie_name = _require_view_session(request)
    guard_public_request(
        request,
        "cancel",
        ticket_id=ticket_id,
        purchase_id=session.purchase_id,
    )
    link_sessions.touch_session_usage(session.jti, scope="view")

    conn = get_connection()
    cur = conn.cursor()
    try:
        if not otp.consume_op_token(data.op_token, "cancel", ticket_id, conn=conn):
            raise HTTPException(status_code=400, detail="Invalid operation token")

        free_ticket(cur, ticket_id)
        if session.purchase_id:
            cur.execute(
                "UPDATE purchase SET status='cancelled', update_at=NOW() WHERE id = %s",
                (session.purchase_id,),
            )
        link_sessions.revoke_ticket_sessions(ticket_id, conn=conn)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    response = JSONResponse({"status": "cancelled", "ticket_id": ticket_id})
    response.set_cookie(cookie_name, "", max_age=0, httponly=True, samesite="lax", path="/")
    return response


__all__ = ["router", "session_router"]
