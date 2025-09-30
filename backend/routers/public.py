from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import zipfile
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
from ..services.public_session import (
    PurchaseSessionContext,
    get_request_session,
    _PURCHASE_COOKIE_PREFIX,
)

session_router = APIRouter(tags=["public"])
router = APIRouter(prefix="/public", tags=["public"])

_DEFAULT_LANG = "bg"


class OTPStartRequest(BaseModel):
    purchase_id: int = Field(..., gt=0)
    action: str = Field(..., pattern=r"^(pay|reschedule|cancel|baggage)$")


class OTPStartResponse(BaseModel):
    challenge_id: str
    ttl_sec: int


class OTPVerifyRequest(BaseModel):
    challenge_id: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)


class OTPVerifyResponse(BaseModel):
    op_token: str
    ttl_sec: int


class OperationTokenIn(BaseModel):
    op_token: str = Field(..., min_length=1)


class RescheduleOptionsRequest(BaseModel):
    ticket_ids: list[int] | None = Field(default=None)
    date: datetime | None = None


class CancelPreviewRequest(BaseModel):
    ticket_ids: list[int] | None = Field(default=None)


class BaggageQuoteRequest(BaseModel):
    baggage: Any


class RescheduleRequest(OperationTokenIn):
    ticket_ids: list[int] | None = Field(default=None)
    new_tour_id: int = Field(..., gt=0)


class CancelRequest(OperationTokenIn):
    ticket_ids: list[int] | None = Field(default=None)
    reason: str | None = None


class BaggageRequest(OperationTokenIn):
    baggage: Any


def _redirect_base_url(purchase_id: int) -> str:
    return f"http://localhost:3001/purchase/{purchase_id}"


def _purchase_cookie_name(purchase_id: int) -> str:
    return f"{_PURCHASE_COOKIE_PREFIX}{purchase_id}"


def _resolve_purchase_id(session: link_sessions.LinkSession) -> int:
    if session.purchase_id:
        return int(session.purchase_id)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT purchase_id FROM ticket WHERE id = %s", (session.ticket_id,))
            row = cur.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="Purchase not found for ticket")
        return int(row[0])
    finally:
        conn.close()


def _get_purchase_session(request: Request) -> PurchaseSessionContext:
    return get_request_session(request)


def _assert_ticket_in_purchase(ticket_id: int, purchase_id: int) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM ticket WHERE id = %s AND purchase_id = %s",
                (ticket_id, purchase_id),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=403, detail="Ticket not part of purchase")
    finally:
        conn.close()


def _load_ticket_dto(ticket_id: int, lang: str = _DEFAULT_LANG) -> Mapping[str, Any]:
    conn = get_connection()
    try:
        try:
            return get_ticket_dto(ticket_id, lang, conn)
        except ValueError as exc:  # pragma: no cover - defensive logging
            raise HTTPException(status_code=404, detail="Ticket not found") from exc
    finally:
        conn.close()


def _load_purchase_view(purchase_id: int, lang: str = _DEFAULT_LANG) -> Mapping[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, amount_due, customer_name, customer_email,
                       customer_phone, update_at
                  FROM purchase
                 WHERE id = %s
                """,
                (purchase_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Purchase not found")

        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id FROM ticket WHERE purchase_id = %s ORDER BY id",
                (purchase_id,),
            )
            ticket_ids = [int(r[0]) for r in cur.fetchall()]
        finally:
            cur.close()

        tickets = [get_ticket_dto(tid, lang, conn) for tid in ticket_ids]
        timestamp = row[6]
        return {
            "id": purchase_id,
            "status": row[1],
            "amount_due": float(row[2]) if row[2] is not None else None,
            "customer": {
                "name": row[3],
                "email": row[4],
                "phone": row[5],
            },
            "created_at": timestamp.isoformat() if timestamp else None,
            "updated_at": timestamp.isoformat() if timestamp else None,
            "tickets": tickets,
        }
    finally:
        conn.close()


def _build_liqpay_payload(
    purchase_id: int,
    amount: float,
    *,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    public_key = os.getenv("LIQPAY_PUBLIC_KEY", "sandbox")
    private_key = os.getenv("LIQPAY_PRIVATE_KEY", "sandbox")
    currency = os.getenv("LIQPAY_CURRENCY", "UAH")

    description = ""
    if ticket_id is not None:
        description = f"Ticket #{ticket_id}"
    else:
        description = f"Purchase #{purchase_id}"

    payload = {
        "version": "3",
        "public_key": public_key,
        "action": "pay",
        "amount": round(max(amount, 0.0), 2),
        "currency": currency,
        "description": description,
        "order_id": f"purchase-{purchase_id}" if ticket_id is None else f"ticket-{ticket_id}-{purchase_id}",
        "result_url": _redirect_base_url(purchase_id),
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

    purchase_id = _resolve_purchase_id(session)

    guard_public_request(
        request,
        "qr_exchange",
        ticket_id=session.ticket_id,
        purchase_id=purchase_id,
    )

    remaining = int((session.exp - now).total_seconds())
    if remaining <= 0:
        remaining = 60

    response = RedirectResponse(
        url=_redirect_base_url(purchase_id),
        status_code=302,
    )
    response.set_cookie(
        _purchase_cookie_name(purchase_id),
        session.jti,
        max_age=remaining,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/tickets/{ticket_id}")
def get_public_ticket(ticket_id: int, request: Request) -> Any:
    context = _get_purchase_session(request)
    if ticket_id != context.ticket_id:
        _assert_ticket_in_purchase(ticket_id, context.purchase_id)

    guard_public_request(
        request,
        "ticket_view",
        ticket_id=ticket_id,
        purchase_id=context.purchase_id,
    )

    dto = _load_ticket_dto(ticket_id, _DEFAULT_LANG)
    payload: dict[str, Any] = {"ticket": dto}
    if isinstance(dto, Mapping):
        payload.update(dto)
    return jsonable_encoder(payload)


@router.get("/purchase/{purchase_id}")
def get_public_purchase(purchase_id: int, request: Request) -> Any:
    context = _get_purchase_session(request)
    if purchase_id != context.purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")

    guard_public_request(
        request,
        "purchase_view",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    dto = _load_purchase_view(context.purchase_id, _DEFAULT_LANG)
    payload: dict[str, Any] = {"purchase": dto}
    if isinstance(dto, Mapping):
        payload.update(dto)
    return jsonable_encoder(payload)


@router.post("/purchase/{purchase_id}/reschedule-options")
def get_reschedule_options(
    purchase_id: int, data: RescheduleOptionsRequest, request: Request
) -> Mapping[str, Any]:
    context = _get_purchase_session(request)
    if purchase_id != context.purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")
    if data.ticket_ids and context.ticket_id not in data.ticket_ids:
        raise HTTPException(status_code=403, detail="Ticket not part of request")

    guard_public_request(
        request,
        "reschedule_options",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    return {"options": []}


@router.post("/purchase/{purchase_id}/cancel/preview")
def preview_cancel(
    purchase_id: int, data: CancelPreviewRequest, request: Request
) -> Mapping[str, Any]:
    context = _get_purchase_session(request)
    if purchase_id != context.purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")
    if data.ticket_ids and context.ticket_id not in data.ticket_ids:
        raise HTTPException(status_code=403, detail="Ticket not part of request")

    guard_public_request(
        request,
        "cancel_preview",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    return {"total_refund": 0.0, "currency": "BGN"}


@router.post("/purchase/{purchase_id}/baggage/quote")
def quote_baggage(
    purchase_id: int, data: BaggageQuoteRequest, request: Request
) -> Mapping[str, Any]:
    context = _get_purchase_session(request)
    if purchase_id != context.purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")

    guard_public_request(
        request,
        "baggage_quote",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    return {"total": 0.0, "currency": "BGN"}


@session_router.get("/tickets/{ticket_id}/pdf")
def get_public_ticket_pdf(ticket_id: int, request: Request) -> Response:
    context = _get_purchase_session(request)
    if ticket_id != context.ticket_id:
        _assert_ticket_in_purchase(ticket_id, context.purchase_id)

    guard_public_request(
        request,
        "ticket_pdf",
        ticket_id=ticket_id,
        purchase_id=context.purchase_id,
    )

    dto = _load_ticket_dto(ticket_id, _DEFAULT_LANG)
    deep_link = build_deep_link(context.session.jti)
    pdf_bytes = render_ticket_pdf(dto, deep_link)

    headers = {
        "Content-Disposition": f'inline; filename="ticket-{ticket_id}.pdf"',
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@session_router.get("/purchase/{purchase_id}/pdf")
def get_public_purchase_pdf(purchase_id: int, request: Request) -> Response:
    context = _get_purchase_session(request)
    if purchase_id != context.purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")

    guard_public_request(
        request,
        "purchase_pdf",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    purchase = _load_purchase_view(context.purchase_id, _DEFAULT_LANG)
    tickets = purchase.get("tickets", []) if isinstance(purchase, Mapping) else []
    deep_link = build_deep_link(context.session.jti)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for ticket in tickets:
            ticket_info = ticket if isinstance(ticket, Mapping) else {}
            ticket_obj = ticket_info.get("ticket") if isinstance(ticket_info.get("ticket"), Mapping) else None
            ticket_id_value = None
            if isinstance(ticket_obj, Mapping):
                ticket_id_value = ticket_obj.get("id")
            if ticket_id_value is None:
                ticket_id_value = ticket_info.get("id")
            if ticket_id_value is None:
                continue
            pdf_bytes = render_ticket_pdf(ticket_info, deep_link)
            archive.writestr(f"ticket-{ticket_id_value}.pdf", pdf_bytes)

    buffer.seek(0)
    headers = {
        "Content-Disposition": f'attachment; filename="purchase-{context.purchase_id}.zip"',
    }
    return Response(content=buffer.getvalue(), media_type="application/zip", headers=headers)


@router.post("/otp/start", response_model=OTPStartResponse)
def start_otp_flow(data: OTPStartRequest, request: Request) -> OTPStartResponse:
    context = _get_purchase_session(request)

    guard_public_request(
        request,
        "otp_start",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM ticket WHERE id = %s AND purchase_id = %s",
            (context.ticket_id, context.purchase_id),
        )
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=403, detail="Ticket not part of purchase")

        dto = get_ticket_dto(context.ticket_id, _DEFAULT_LANG, conn)
        purchase_info = dto.get("purchase") if isinstance(dto, Mapping) else None
        customer = purchase_info.get("customer") if isinstance(purchase_info, Mapping) else None
        email = customer.get("email") if isinstance(customer, Mapping) else None
        if not email:
            raise HTTPException(status_code=400, detail="Ticket has no contact email")

        challenge = otp.create_challenge(
            context.ticket_id,
            context.purchase_id,
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
    context = _get_purchase_session(request)
    guard_public_request(
        request,
        "otp_verify",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    token = otp.verify_challenge(
        data.challenge_id,
        data.code,
        ticket_id=context.ticket_id,
    )
    if not token:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    if token.purchase_id and context.purchase_id and int(token.purchase_id) != context.purchase_id:
        raise HTTPException(status_code=400, detail="Operation token mismatch")

    ttl_seconds = max(int((token.exp - datetime.now(timezone.utc)).total_seconds()), 1)

    return OTPVerifyResponse(op_token=token.token, ttl_sec=ttl_seconds)


@router.post("/purchase/{purchase_id}/pay")
def public_pay(purchase_id: int, data: OperationTokenIn, request: Request) -> Mapping[str, Any]:
    context = _get_purchase_session(request)
    if purchase_id != context.purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")

    guard_public_request(
        request,
        "pay",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        if not otp.consume_op_token(data.op_token, "pay", context.ticket_id, conn=conn):
            raise HTTPException(status_code=400, detail="Invalid operation token")

        cur.execute(
            "SELECT amount_due FROM purchase WHERE id = %s",
            (context.purchase_id,),
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

    return _build_liqpay_payload(context.purchase_id, amount_due, ticket_id=context.ticket_id)


@router.post("/purchase/{purchase_id}/reschedule")
def public_reschedule(purchase_id: int, data: RescheduleRequest, request: Request) -> Mapping[str, Any]:
    context = _get_purchase_session(request)
    if purchase_id != context.purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")
    if data.ticket_ids and context.ticket_id not in data.ticket_ids:
        raise HTTPException(status_code=403, detail="Ticket not part of request")

    guard_public_request(
        request,
        "reschedule",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        if not otp.validate_op_token(data.op_token, "reschedule", context.ticket_id, conn=conn):
            raise HTTPException(status_code=400, detail="Invalid operation token")

        cur.execute(
            """
            SELECT seat_id, tour_id, departure_stop_id, arrival_stop_id
              FROM ticket
             WHERE id = %s
             FOR UPDATE
            """,
            (context.ticket_id,),
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
            if not otp.consume_op_token(data.op_token, "reschedule", context.ticket_id, conn=conn):
                raise HTTPException(status_code=400, detail="Operation token expired")
            conn.commit()
            return {
                "need_payment": False,
                "difference": 0.0,
                "ticket_id": context.ticket_id,
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
            ticket_id=context.ticket_id,
            current_seat_id=seat_id,
            target_tour_id=data.new_tour_id,
            seat_num=seat_num,
            departure_stop_id=departure_stop_id,
            arrival_stop_id=arrival_stop_id,
        )

        if not otp.consume_op_token(data.op_token, "reschedule", context.ticket_id, conn=conn):
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
        "ticket_id": context.ticket_id,
        "new_tour_id": data.new_tour_id,
    }


@router.post("/purchase/{purchase_id}/cancel")
def public_cancel(purchase_id: int, data: CancelRequest, request: Request) -> JSONResponse:
    context = _get_purchase_session(request)
    if purchase_id != context.purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")
    if data.ticket_ids and context.ticket_id not in data.ticket_ids:
        raise HTTPException(status_code=403, detail="Ticket not part of request")

    guard_public_request(
        request,
        "cancel",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        if not otp.consume_op_token(data.op_token, "cancel", context.ticket_id, conn=conn):
            raise HTTPException(status_code=400, detail="Invalid operation token")

        free_ticket(cur, context.ticket_id)
        if context.purchase_id:
            cur.execute(
                "UPDATE purchase SET status='cancelled', update_at=NOW() WHERE id = %s",
                (context.purchase_id,),
            )
        link_sessions.revoke_ticket_sessions(context.ticket_id, conn=conn)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    response = JSONResponse({"status": "cancelled", "ticket_id": context.ticket_id})
    response.set_cookie(
        context.cookie_name,
        "",
        max_age=0,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/purchase/{purchase_id}/baggage")
def public_baggage(purchase_id: int, data: BaggageRequest, request: Request) -> Mapping[str, Any]:
    context = _get_purchase_session(request)
    if purchase_id != context.purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")

    guard_public_request(
        request,
        "baggage",
        ticket_id=context.ticket_id,
        purchase_id=context.purchase_id,
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        if not otp.consume_op_token(data.op_token, "baggage", context.ticket_id, conn=conn):
            raise HTTPException(status_code=400, detail="Invalid operation token")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return {"need_payment": False, "done": True}


__all__ = ["router", "session_router"]
