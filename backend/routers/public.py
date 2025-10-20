from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import secrets
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, EmailStr, Field

from ..database import get_connection
from ..services import link_sessions
from ..services.access_guard import guard_public_request
from ..services.ticket_dto import get_ticket_dto
from ..services.ticket_pdf import render_ticket_pdf
from ..ticket_utils import free_ticket, recalc_available
from ._ticket_link_helpers import build_deep_link, combine_departure_datetime
from ..services.link_sessions import get_or_create_view_session

session_router = APIRouter(tags=["public"])
router = APIRouter(prefix="/public", tags=["public"])

_COOKIE_PREFIX = "minicab_"
_PURCHASE_COOKIE_PREFIX = "minicab_purchase_"
_CSRF_COOKIE_NAME = "mc_csrf"
_DEFAULT_LANG = "bg"


class TicketPdfRequest(BaseModel):
    purchase_id: int = Field(..., gt=0)
    purchaser_email: EmailStr = Field(...)
    lang: str | None = Field(None, description="Preferred language for the PDF")


class RescheduleTicketSpec(BaseModel):
    ticket_id: int = Field(..., gt=0)
    new_tour_id: int = Field(..., gt=0)
    seat_num: int = Field(..., gt=0)


class RescheduleRequest(BaseModel):
    tickets: list[RescheduleTicketSpec] = Field(..., min_length=1)


class BaggageTicketSpec(BaseModel):
    ticket_id: int = Field(..., gt=0)
    extra_baggage: int = Field(..., ge=0)


class BaggageRequest(BaseModel):
    tickets: list[BaggageTicketSpec] = Field(..., min_length=1)


class CancelRequest(BaseModel):
    ticket_ids: list[int] = Field(..., min_length=1)


def _generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _require_csrf(request: Request) -> str:
    cookie_value = request.cookies.get(_CSRF_COOKIE_NAME)
    header_value = request.headers.get("X-CSRF")
    if not cookie_value or not header_value:
        raise HTTPException(status_code=403, detail="Missing CSRF token")
    if not secrets.compare_digest(cookie_value, header_value):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return cookie_value


def _log_sale(cur, purchase_id: int, category: str, amount: float, *, actor: str | None = None) -> None:
    cur.execute(
        "INSERT INTO sales (purchase_id, category, amount, actor, method) VALUES (%s,%s,%s,%s,%s)",
        (purchase_id, category, amount, actor or "public", None),
    )


def _round_currency(value: float | None) -> float:
    return round(float(value or 0.0), 2)


def _redirect_base_url(purchase_id: int) -> str:
    return f"http://localhost:3001/purchase/{purchase_id}"


def _cookie_name(ticket_id: int) -> str:
    return f"{_COOKIE_PREFIX}{ticket_id}"


def _purchase_cookie_name(purchase_id: int) -> str:
    return f"{_PURCHASE_COOKIE_PREFIX}{purchase_id}"


def _iter_purchase_cookies(cookies: Mapping[str, str]) -> Iterable[tuple[int, str, str]]:
    for key, value in cookies.items():
        if not key.startswith(_PURCHASE_COOKIE_PREFIX) or not value:
            continue
        suffix = key[len(_PURCHASE_COOKIE_PREFIX) :]
        if suffix.isdigit():
            yield int(suffix), key, value


def _iter_ticket_cookies(cookies: Mapping[str, str]) -> Iterable[tuple[int, str, str]]:
    for key, value in cookies.items():
        if not key.startswith(_COOKIE_PREFIX) or not value:
            continue
        suffix = key[len(_COOKIE_PREFIX) :]
        if suffix.isdigit():
            yield int(suffix), key, value


def _pick_cookie(
    matches: Sequence[tuple[int, str, str]] | Iterable[tuple[int, str, str]],
    *,
    missing_detail: str,
    ambiguous_detail: str,
) -> tuple[int, str, str]:
    collected = matches if isinstance(matches, list) else list(matches)
    if not collected:
        raise HTTPException(status_code=401, detail=missing_detail)
    if len(collected) > 1:
        raise HTTPException(status_code=400, detail=ambiguous_detail)
    return collected[0]


def _extract_session_cookie(
    request: Request, ticket_id: int | None = None, purchase_id: int | None = None
) -> tuple[int, str, str]:
    cookies = request.cookies or {}
    if purchase_id is not None:
        name = _purchase_cookie_name(purchase_id)
        value = cookies.get(name)
        if not value:
            raise HTTPException(status_code=401, detail="Missing purchase session")
        return purchase_id, name, value

    if ticket_id is not None:
        name = _cookie_name(ticket_id)
        value = cookies.get(name)
        if value:
            return ticket_id, name, value
        return _pick_cookie(
            _iter_purchase_cookies(cookies),
            missing_detail="Missing purchase session",
            ambiguous_detail="Ambiguous purchase session",
        )

    purchase_match = list(_iter_purchase_cookies(cookies))
    if purchase_match:
        return _pick_cookie(
            purchase_match,
            missing_detail="Missing purchase session",
            ambiguous_detail="Ambiguous purchase session",
        )

    return _pick_cookie(
        _iter_ticket_cookies(cookies),
        missing_detail="Missing ticket session",
        ambiguous_detail="Ambiguous ticket session",
    )


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


def _require_view_session(
    request: Request,
    ticket_id: int | None = None,
    purchase_id: int | None = None,
) -> tuple[link_sessions.LinkSession, int, int, str]:
    target_id, cookie_name, session_id = _extract_session_cookie(
        request, ticket_id=ticket_id, purchase_id=purchase_id
    )

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

    resolved_purchase_id = _resolve_purchase_id(session)
    if purchase_id is not None and resolved_purchase_id != purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")

    if ticket_id is not None and session.ticket_id != ticket_id:
        raise HTTPException(status_code=403, detail="Session does not match ticket")

    if purchase_id is None and target_id != resolved_purchase_id:
        # Cookie may have been issued for a specific ticket; keep compatibility by
        # ensuring it matches the associated purchase.
        if target_id != session.ticket_id:
            raise HTTPException(status_code=403, detail="Session mismatch")

    return session, session.ticket_id, resolved_purchase_id, cookie_name


def _require_purchase_context(
    request: Request,
    purchase_id: int,
    scope: str,
) -> tuple[link_sessions.LinkSession, int, int, str]:
    session, ticket_id, resolved_purchase_id, cookie_name = _require_view_session(
        request, purchase_id=purchase_id
    )
    guard_public_request(
        request,
        scope,
        ticket_id=ticket_id,
        purchase_id=resolved_purchase_id,
    )
    _require_csrf(request)
    link_sessions.touch_session_usage(session.jti, scope="view")
    return session, ticket_id, resolved_purchase_id, cookie_name


def _load_purchase_state(
    cur,
    purchase_id: int,
    *,
    for_update: bool = False,
) -> tuple[float, str]:
    query = "SELECT amount_due, status FROM purchase WHERE id = %s"
    if for_update:
        query += " FOR UPDATE"
    cur.execute(query, (purchase_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Purchase not found")
    amount_due = _round_currency(row[0])
    status = str(row[1]) if row[1] is not None else "reserved"
    return amount_due, status


def _ensure_purchase_active(status: str) -> None:
    if status in {"cancelled", "refunded"}:
        raise HTTPException(status_code=409, detail="Purchase is not active")


def _status_for_balance(current_status: str, new_amount_due: float, *, has_tickets: bool = True) -> str:
    if not has_tickets:
        return "cancelled"
    if new_amount_due <= 0:
        return "paid" if current_status != "refunded" else current_status
    return "reserved"


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


def _plan_reschedule(
    cur,
    purchase_id: int,
    specs: Sequence[RescheduleTicketSpec],
    *,
    lock_tickets: bool = False,
    lock_seats: bool = False,
) -> tuple[list[dict[str, Any]], float]:
    if not specs:
        raise HTTPException(status_code=400, detail="No tickets provided")

    seen: set[int] = set()
    seat_state: dict[int, str] = {}
    tour_route_cache: dict[int, int] = {}
    route_stop_cache: dict[int, list[int]] = {}
    plans: list[dict[str, Any]] = []
    total_difference = 0.0

    for spec in specs:
        if spec.ticket_id in seen:
            raise HTTPException(status_code=400, detail="Duplicate ticket in request")
        seen.add(spec.ticket_id)

        ticket_query = (
            "SELECT seat_id, tour_id, departure_stop_id, arrival_stop_id, purchase_id FROM ticket WHERE id = %s"
        )
        if lock_tickets:
            ticket_query += " FOR UPDATE"
        cur.execute(ticket_query, (spec.ticket_id,))
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        current_seat_id, current_tour_id, dep_id, arr_id, purchase_ref = ticket_row
        if purchase_ref != purchase_id:
            raise HTTPException(status_code=403, detail="Ticket does not belong to this purchase")

        seat_query = "SELECT seat_num, available FROM seat WHERE id = %s"
        if lock_seats:
            seat_query += " FOR UPDATE"
        cur.execute(seat_query, (current_seat_id,))
        seat_row = cur.fetchone()
        if not seat_row:
            raise HTTPException(status_code=404, detail="Seat not found")
        current_seat_num = int(seat_row[0])
        current_avail = seat_row[1]

        current_state = seat_state.get(current_seat_id)
        if current_state is None:
            current_state = _normalize_availability(current_avail)

        current_route_id = tour_route_cache.get(current_tour_id)
        if current_route_id is None:
            cur.execute("SELECT route_id FROM tour WHERE id = %s", (current_tour_id,))
            route_row = cur.fetchone()
            if not route_row:
                raise HTTPException(status_code=404, detail="Tour not found")
            current_route_id = int(route_row[0])
            tour_route_cache[current_tour_id] = current_route_id

        current_stops = route_stop_cache.get(current_route_id)
        if current_stops is None:
            current_stops = _fetch_route_stops(cur, current_route_id)
            route_stop_cache[current_route_id] = current_stops
        current_segments, _ = _segments_between(current_stops, dep_id, arr_id)
        released_state = _merge_available(current_state, current_segments)
        seat_state[current_seat_id] = released_state

        current_price = _resolve_ticket_price(cur, current_tour_id, dep_id, arr_id)
        if current_price is None:
            raise HTTPException(status_code=400, detail="Unable to calculate fare difference")

        target_route_id = tour_route_cache.get(spec.new_tour_id)
        if target_route_id is None:
            cur.execute("SELECT route_id FROM tour WHERE id = %s", (spec.new_tour_id,))
            route_row = cur.fetchone()
            if not route_row:
                raise HTTPException(status_code=404, detail="Target tour not found")
            target_route_id = int(route_row[0])
            tour_route_cache[spec.new_tour_id] = target_route_id

        target_stops = route_stop_cache.get(target_route_id)
        if target_stops is None:
            target_stops = _fetch_route_stops(cur, target_route_id)
            route_stop_cache[target_route_id] = target_stops
        target_segments, _ = _segments_between(target_stops, dep_id, arr_id)

        target_query = "SELECT id, available FROM seat WHERE tour_id = %s AND seat_num = %s"
        if lock_seats:
            target_query += " FOR UPDATE"
        cur.execute(target_query, (spec.new_tour_id, spec.seat_num))
        target_row = cur.fetchone()
        if not target_row:
            raise HTTPException(status_code=404, detail="Seat not found on target tour")
        target_seat_id, target_avail = target_row
        if target_avail == "0" and target_seat_id != current_seat_id:
            raise HTTPException(status_code=409, detail="Seat is blocked on the selected tour")

        target_state = seat_state.get(target_seat_id)
        if target_state is None:
            target_state = _normalize_availability(target_avail)
        _ensure_segments_available(target_state, target_segments)
        seat_state[target_seat_id] = _remove_segments(target_state, target_segments)

        target_price = _resolve_ticket_price(cur, spec.new_tour_id, dep_id, arr_id)
        if target_price is None:
            raise HTTPException(status_code=400, detail="Unable to calculate fare difference")

        difference = float(target_price - current_price)
        total_difference += difference

        plans.append(
            {
                "ticket_id": int(spec.ticket_id),
                "current_tour_id": int(current_tour_id),
                "target_tour_id": int(spec.new_tour_id),
                "seat_num": int(spec.seat_num),
                "current_seat_num": current_seat_num,
                "current_price": float(current_price),
                "target_price": float(target_price),
                "difference": difference,
                "current_seat_id": int(current_seat_id),
                "target_seat_id": int(target_seat_id),
                "departure_stop_id": int(dep_id),
                "arrival_stop_id": int(arr_id),
                "no_change": current_tour_id == spec.new_tour_id
                and current_seat_id == target_seat_id,
            }
        )

    return plans, total_difference


def _plan_baggage(
    cur,
    purchase_id: int,
    specs: Sequence[BaggageTicketSpec],
    purchase_status: str,
    *,
    lock_tickets: bool = False,
) -> tuple[list[dict[str, Any]], float]:
    if not specs:
        raise HTTPException(status_code=400, detail="No tickets provided")

    seen: set[int] = set()
    plans: list[dict[str, Any]] = []
    total_delta = 0.0

    for spec in specs:
        if spec.ticket_id in seen:
            raise HTTPException(status_code=400, detail="Duplicate ticket in request")
        seen.add(spec.ticket_id)

        ticket_query = (
            "SELECT tour_id, departure_stop_id, arrival_stop_id, extra_baggage, purchase_id FROM ticket WHERE id = %s"
        )
        if lock_tickets:
            ticket_query += " FOR UPDATE"
        cur.execute(ticket_query, (spec.ticket_id,))
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        tour_id, dep_id, arr_id, current_extra, purchase_ref = ticket_row
        if purchase_ref != purchase_id:
            raise HTTPException(status_code=403, detail="Ticket does not belong to this purchase")

        current_extra_count = int(current_extra or 0)
        new_extra_count = int(spec.extra_baggage)
        if new_extra_count < current_extra_count and purchase_status == "paid":
            raise HTTPException(status_code=409, detail="Cannot remove paid baggage")

        base_price = _resolve_ticket_price(cur, tour_id, dep_id, arr_id)
        if base_price is None:
            raise HTTPException(status_code=400, detail="Unable to calculate baggage price")

        delta_count = new_extra_count - current_extra_count
        delta = float(base_price) * 0.1 * delta_count
        delta = round(delta, 2)
        total_delta += delta

        plans.append(
            {
                "ticket_id": int(spec.ticket_id),
                "tour_id": int(tour_id),
                "departure_stop_id": int(dep_id),
                "arrival_stop_id": int(arr_id),
                "current_extra_baggage": current_extra_count,
                "new_extra_baggage": new_extra_count,
                "delta": delta,
            }
        )

    return plans, total_delta


def _plan_cancel(
    cur,
    purchase_id: int,
    ticket_ids: Sequence[int],
    *,
    lock_tickets: bool = False,
) -> tuple[list[dict[str, Any]], float]:
    if not ticket_ids:
        raise HTTPException(status_code=400, detail="No tickets provided")

    seen: set[int] = set()
    plans: list[dict[str, Any]] = []
    total_delta = 0.0

    for ticket_id in ticket_ids:
        if ticket_id in seen:
            raise HTTPException(status_code=400, detail="Duplicate ticket in request")
        seen.add(ticket_id)

        ticket_query = (
            "SELECT tour_id, departure_stop_id, arrival_stop_id, extra_baggage, purchase_id FROM ticket WHERE id = %s"
        )
        if lock_tickets:
            ticket_query += " FOR UPDATE"
        cur.execute(ticket_query, (ticket_id,))
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        tour_id, dep_id, arr_id, extra_baggage, purchase_ref = ticket_row
        if purchase_ref != purchase_id:
            raise HTTPException(status_code=403, detail="Ticket does not belong to this purchase")

        base_price = _resolve_ticket_price(cur, tour_id, dep_id, arr_id)
        if base_price is None:
            raise HTTPException(status_code=400, detail="Unable to calculate ticket price")

        baggage_price = float(base_price) * 0.1 * int(extra_baggage or 0)
        ticket_value = float(base_price) + baggage_price
        ticket_value = round(ticket_value, 2)
        total_delta -= ticket_value

        plans.append(
            {
                "ticket_id": int(ticket_id),
                "tour_id": int(tour_id),
                "value": ticket_value,
                "extra_baggage": int(extra_baggage or 0),
            }
        )

    return plans, total_delta


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
    csrf_token = _generate_csrf_token()
    response.set_cookie(
        _purchase_cookie_name(purchase_id),
        session.jti,
        max_age=remaining,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        _CSRF_COOKIE_NAME,
        csrf_token,
        max_age=remaining,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/tickets/{ticket_id}")
def get_public_ticket(ticket_id: int, request: Request) -> Any:
    session, resolved_ticket_id, resolved_purchase_id, _cookie = _require_view_session(
        request, ticket_id=ticket_id
    )
    guard_public_request(
        request,
        "ticket_view",
        ticket_id=resolved_ticket_id,
        purchase_id=resolved_purchase_id,
    )

    link_sessions.touch_session_usage(session.jti, scope="view")

    dto = _load_ticket_dto(resolved_ticket_id, _DEFAULT_LANG)
    payload: dict[str, Any] = {"ticket": dto}
    if isinstance(dto, Mapping):
        payload.update(dto)
    return jsonable_encoder(payload)


@router.get("/purchase/{purchase_id}")
def get_public_purchase(purchase_id: int, request: Request) -> Any:
    session, resolved_ticket_id, resolved_purchase_id, _cookie = _require_view_session(
        request, purchase_id=purchase_id
    )
    guard_public_request(
        request,
        "purchase_view",
        ticket_id=resolved_ticket_id,
        purchase_id=resolved_purchase_id,
    )

    link_sessions.touch_session_usage(session.jti, scope="view")

    dto = _load_purchase_view(resolved_purchase_id, _DEFAULT_LANG)
    payload: dict[str, Any] = {"purchase": dto}
    if isinstance(dto, Mapping):
        payload.update(dto)
    return jsonable_encoder(payload)


@router.post("/tickets/{ticket_id}/pdf")
def get_public_ticket_pdf(ticket_id: int, request: Request, data: TicketPdfRequest) -> Response:
    guard_public_request(
        request,
        "ticket_pdf",
        ticket_id=ticket_id,
        purchase_id=data.purchase_id,
    )

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.purchase_id, p.customer_email, p.lang
                  FROM ticket AS t
                  JOIN purchase AS p ON p.id = t.purchase_id
                 WHERE t.id = %s
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")

    resolved_purchase_id = int(row[0])
    if resolved_purchase_id != data.purchase_id:
        raise HTTPException(status_code=404, detail="Ticket not found")

    stored_email = (row[1] or "").strip()
    if not stored_email or stored_email.casefold() != data.purchaser_email.casefold():
        raise HTTPException(status_code=403, detail="Invalid purchaser email")

    purchase_lang = str(row[2]) if row[2] is not None else None
    resolved_lang = (data.lang or purchase_lang or _DEFAULT_LANG).lower()

    dto = _load_ticket_dto(ticket_id, resolved_lang)

    segment = dto.get("segment") if isinstance(dto, Mapping) else {}
    segment = segment or {}
    departure_ctx = segment.get("departure") if isinstance(segment, Mapping) else {}
    departure_ctx = departure_ctx or {}
    tour = dto.get("tour") if isinstance(dto, Mapping) else {}
    tour = tour or {}

    tour_date = tour.get("date") if isinstance(tour, Mapping) else None
    departure_time = (
        departure_ctx.get("time") if isinstance(departure_ctx, Mapping) else None
    )

    departure_dt = None
    if tour_date:
        try:
            departure_dt = combine_departure_datetime(tour_date, departure_time)
        except ValueError:
            departure_dt = None

    try:
        opaque, _expires_at = get_or_create_view_session(
            ticket_id,
            purchase_id=resolved_purchase_id,
            lang=resolved_lang,
            departure_dt=departure_dt,
            scopes={"view"},
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Failed to prepare ticket link") from exc

    deep_link = build_deep_link(opaque)
    pdf_bytes = render_ticket_pdf(dto, deep_link)

    headers = {
        "Content-Disposition": f'inline; filename="ticket-{ticket_id}.pdf"',
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.get("/purchase/{purchase_id}/pdf")
def get_public_purchase_pdf(purchase_id: int, request: Request) -> Response:
    session, resolved_ticket_id, resolved_purchase_id, _cookie = _require_view_session(
        request, purchase_id=purchase_id
    )
    guard_public_request(
        request,
        "purchase_pdf",
        ticket_id=resolved_ticket_id,
        purchase_id=resolved_purchase_id,
    )

    link_sessions.touch_session_usage(session.jti, scope="view")

    purchase = _load_purchase_view(resolved_purchase_id, _DEFAULT_LANG)
    tickets = purchase.get("tickets", []) if isinstance(purchase, Mapping) else []
    deep_link = build_deep_link(session.jti)

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
        "Content-Disposition": f'attachment; filename="purchase-{resolved_purchase_id}.zip"',
    }
    return Response(content=buffer.getvalue(), media_type="application/zip", headers=headers)


@router.post("/purchase/{purchase_id}/pay")
def public_pay(purchase_id: int, request: Request) -> Mapping[str, Any]:
    _session, ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "pay"
    )

    amount_due = 0.0
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            amount_due, status = _load_purchase_state(cur, resolved_purchase_id)
            _ensure_purchase_active(status)
    finally:
        conn.close()

    if amount_due <= 0:
        raise HTTPException(status_code=400, detail="Purchase has no outstanding balance")

    return _build_liqpay_payload(resolved_purchase_id, amount_due, ticket_id=ticket_id)


@router.post("/purchase/{purchase_id}/reschedule/quote")
def public_reschedule_quote(
    purchase_id: int, data: RescheduleRequest, request: Request
) -> Mapping[str, Any]:
    _session, _ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "reschedule_quote"
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        amount_due, status = _load_purchase_state(cur, resolved_purchase_id)
        _ensure_purchase_active(status)
        plans, difference = _plan_reschedule(cur, resolved_purchase_id, data.tickets)
    finally:
        cur.close()
        conn.close()

    total_difference = round(difference, 2)
    new_amount_due = _round_currency(amount_due + difference)

    response = {
        "tickets": [
            {
                "ticket_id": plan["ticket_id"],
                "current_tour_id": plan["current_tour_id"],
                "new_tour_id": plan["target_tour_id"],
                "seat_num": plan["seat_num"],
                "current_price": round(plan["current_price"], 2),
                "new_price": round(plan["target_price"], 2),
                "difference": round(plan["difference"], 2),
                "no_change": bool(plan["no_change"]),
            }
            for plan in plans
        ],
        "total_difference": total_difference,
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "need_payment": new_amount_due > 0,
    }
    return jsonable_encoder(response)


@router.post("/purchase/{purchase_id}/reschedule")
def public_reschedule(
    purchase_id: int, data: RescheduleRequest, request: Request
) -> Mapping[str, Any]:
    session, _ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "reschedule"
    )

    conn = get_connection()
    cur = conn.cursor()
    plans: list[dict[str, Any]] = []
    amount_due = 0.0
    difference = 0.0
    new_amount_due = 0.0
    status = "reserved"
    try:
        amount_due, status = _load_purchase_state(
            cur, resolved_purchase_id, for_update=True
        )
        _ensure_purchase_active(status)
        plans, difference = _plan_reschedule(
            cur,
            resolved_purchase_id,
            data.tickets,
            lock_tickets=True,
            lock_seats=True,
        )

        for plan in plans:
            if plan["no_change"]:
                continue
            _perform_reschedule(
                cur,
                ticket_id=plan["ticket_id"],
                current_seat_id=plan["current_seat_id"],
                target_tour_id=plan["target_tour_id"],
                seat_num=plan["seat_num"],
                departure_stop_id=plan["departure_stop_id"],
                arrival_stop_id=plan["arrival_stop_id"],
            )

        new_amount_due = _round_currency(amount_due + difference)
        status_update = _status_for_balance(status, new_amount_due, has_tickets=True)
        cur.execute(
            "UPDATE purchase SET amount_due=%s, status=%s, update_at=NOW() WHERE id=%s",
            (new_amount_due, status_update, resolved_purchase_id),
        )

        total_difference = round(difference, 2)
        if total_difference != 0:
            _log_sale(
                cur,
                resolved_purchase_id,
                "reschedule",
                total_difference,
                actor=session.jti,
            )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    response = {
        "tickets": [
            {
                "ticket_id": plan["ticket_id"],
                "current_tour_id": plan["current_tour_id"],
                "new_tour_id": plan["target_tour_id"],
                "seat_num": plan["seat_num"],
                "current_price": round(plan["current_price"], 2),
                "new_price": round(plan["target_price"], 2),
                "difference": round(plan["difference"], 2),
                "no_change": bool(plan["no_change"]),
            }
            for plan in plans
        ],
        "total_difference": round(difference, 2),
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "need_payment": new_amount_due > 0,
    }
    return jsonable_encoder(response)


@router.post("/purchase/{purchase_id}/baggage/quote")
def public_baggage_quote(
    purchase_id: int, data: BaggageRequest, request: Request
) -> Mapping[str, Any]:
    _session, _ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "baggage_quote"
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        amount_due, status = _load_purchase_state(cur, resolved_purchase_id)
        _ensure_purchase_active(status)
        plans, delta = _plan_baggage(cur, resolved_purchase_id, data.tickets, status)
    finally:
        cur.close()
        conn.close()

    total_delta = round(delta, 2)
    new_amount_due = _round_currency(amount_due + delta)

    response = {
        "tickets": [
            {
                "ticket_id": plan["ticket_id"],
                "current_extra_baggage": plan["current_extra_baggage"],
                "new_extra_baggage": plan["new_extra_baggage"],
                "delta": plan["delta"],
            }
            for plan in plans
        ],
        "total_delta": total_delta,
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "need_payment": new_amount_due > 0,
    }
    return jsonable_encoder(response)


@router.post("/purchase/{purchase_id}/baggage")
def public_baggage(
    purchase_id: int, data: BaggageRequest, request: Request
) -> Mapping[str, Any]:
    session, _ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "baggage"
    )

    conn = get_connection()
    cur = conn.cursor()
    plans: list[dict[str, Any]] = []
    amount_due = 0.0
    delta = 0.0
    new_amount_due = 0.0
    status = "reserved"
    try:
        amount_due, status = _load_purchase_state(
            cur, resolved_purchase_id, for_update=True
        )
        _ensure_purchase_active(status)
        plans, delta = _plan_baggage(
            cur,
            resolved_purchase_id,
            data.tickets,
            status,
            lock_tickets=True,
        )

        for plan in plans:
            if plan["current_extra_baggage"] == plan["new_extra_baggage"]:
                continue
            cur.execute(
                "UPDATE ticket SET extra_baggage=%s WHERE id=%s",
                (plan["new_extra_baggage"], plan["ticket_id"]),
            )

        new_amount_due = _round_currency(amount_due + delta)
        status_update = _status_for_balance(status, new_amount_due, has_tickets=True)
        cur.execute(
            "UPDATE purchase SET amount_due=%s, status=%s, update_at=NOW() WHERE id=%s",
            (new_amount_due, status_update, resolved_purchase_id),
        )

        total_delta = round(delta, 2)
        if total_delta != 0:
            _log_sale(
                cur,
                resolved_purchase_id,
                "baggage",
                total_delta,
                actor=session.jti,
            )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    response = {
        "tickets": [
            {
                "ticket_id": plan["ticket_id"],
                "current_extra_baggage": plan["current_extra_baggage"],
                "new_extra_baggage": plan["new_extra_baggage"],
                "delta": plan["delta"],
            }
            for plan in plans
        ],
        "total_delta": round(delta, 2),
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "need_payment": new_amount_due > 0,
    }
    return jsonable_encoder(response)


@router.post("/purchase/{purchase_id}/cancel")
def public_cancel(
    purchase_id: int, data: CancelRequest, request: Request
) -> JSONResponse:
    session, _ticket_id, resolved_purchase_id, cookie_name = _require_purchase_context(
        request, purchase_id, "cancel"
    )

    conn = get_connection()
    cur = conn.cursor()
    plans: list[dict[str, Any]] = []
    amount_due = 0.0
    delta = 0.0
    new_amount_due = 0.0
    status = "reserved"
    remaining_tickets = 0
    try:
        amount_due, status = _load_purchase_state(
            cur, resolved_purchase_id, for_update=True
        )
        _ensure_purchase_active(status)
        plans, delta = _plan_cancel(
            cur,
            resolved_purchase_id,
            data.ticket_ids,
            lock_tickets=True,
        )

        for plan in plans:
            free_ticket(cur, plan["ticket_id"])
            link_sessions.revoke_ticket_sessions(plan["ticket_id"], conn=conn)

        cur.execute(
            "SELECT COUNT(*) FROM ticket WHERE purchase_id = %s",
            (resolved_purchase_id,),
        )
        count_row = cur.fetchone()
        remaining_tickets = int(count_row[0]) if count_row else 0
        has_tickets = remaining_tickets > 0

        new_amount_due = _round_currency(amount_due + delta)
        status_update = _status_for_balance(
            status, new_amount_due, has_tickets=has_tickets
        )
        cur.execute(
            "UPDATE purchase SET amount_due=%s, status=%s, update_at=NOW() WHERE id=%s",
            (new_amount_due, status_update, resolved_purchase_id),
        )

        total_delta = round(delta, 2)
        if total_delta != 0:
            _log_sale(
                cur,
                resolved_purchase_id,
                "cancelled",
                total_delta,
                actor=session.jti,
            )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    payload = {
        "cancelled_ticket_ids": [plan["ticket_id"] for plan in plans],
        "amount_delta": round(delta, 2),
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "remaining_tickets": remaining_tickets,
    }
    response = JSONResponse(jsonable_encoder(payload))
    if remaining_tickets == 0:
        response.set_cookie(
            _purchase_cookie_name(resolved_purchase_id),
            "",
            max_age=0,
            httponly=True,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            _CSRF_COOKIE_NAME,
            "",
            max_age=0,
            httponly=False,
            samesite="lax",
            path="/",
        )
    return response


__all__ = ["router", "session_router"]
