# backend/app/routers/ticket.py

from typing import Any, Dict, List, Optional, Tuple, cast

from datetime import datetime
import os

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field

from ..auth import optional_scope, require_scope
from ..database import get_connection
from ._ticket_link_helpers import (
    TicketIssueSpec,
    build_deep_link,
    combine_departure_datetime,
    issue_ticket_links,
)
from ..services.ticket_dto import get_ticket_dto
from ..services.ticket_pdf import render_ticket_pdf
from ..services.link_sessions import get_or_create_view_session
from ..services import ticket_links
from ..services.access_guard import guard_public_request
from ..ticket_utils import recalc_available

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketCreate(BaseModel):
    tour_id: int
    seat_num: int
    purchase_id: int | None = None
    passenger_name: str
    passenger_phone: str
    passenger_email: EmailStr
    departure_stop_id: int
    arrival_stop_id: int
    extra_baggage: bool = False
    lang: str | None = None


class TicketOut(BaseModel):
    ticket_id: int
    deep_link: str


@router.get("/{ticket_id}/pdf")
def get_ticket_pdf(
    ticket_id: int,
    request: Request,
    lang: str | None = None,
    context=Depends(optional_scope("view")),
):
    guard_public_request(
        request,
        "view",
        ticket_id=ticket_id,
        context=context,
    )

    conn = get_connection()
    try:
        context_lang = getattr(context, "lang", None) if context else None
        resolved_lang = lang or context_lang or "bg"
        try:
            dto = get_ticket_dto(ticket_id, resolved_lang, conn)
        except ValueError as exc:
            raise HTTPException(404, "Ticket not found") from exc
    finally:
        conn.close()

    purchase = dto.get("purchase") or {}
    segment = dto.get("segment") or {}
    departure_ctx = segment.get("departure") or {}

    departure_dt: datetime | None = None
    tour = dto.get("tour") or {}
    tour_date = tour.get("date")
    departure_time = departure_ctx.get("time")
    if tour_date:
        try:
            departure_dt = combine_departure_datetime(tour_date, departure_time)
        except ValueError:
            departure_dt = None

    try:
        scope_values = set(getattr(context, "scopes", []) or []) if context else {"view"}
        if not scope_values:
            scope_values = {"view"}
        opaque, _expires_at = get_or_create_view_session(
            ticket_id,
            purchase_id=purchase.get("id"),
            lang=resolved_lang,
            departure_dt=departure_dt,
            scopes=scope_values,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to resolve ticket link session for %s", ticket_id)
        raise HTTPException(500, "Failed to prepare ticket link") from exc

    base_url = os.getenv("TICKET_LINK_BASE_URL") or os.getenv("APP_PUBLIC_URL", "https://t.example.com")
    deep_link = build_deep_link(opaque, base_url=base_url)

    pdf_bytes = render_ticket_pdf(dto, deep_link)
    headers = {
        "Content-Disposition": f'inline; filename="ticket-{ticket_id}.pdf"',
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


class TicketReassign(BaseModel):
    tour_id: int
    from_seat: int
    to_seat: int


class TicketUpdate(BaseModel):
    passenger_name: Optional[str] = Field(None, description="Updated passenger name")
    extra_baggage: Optional[bool] = Field(None, description="Extra baggage flag")
    departure_stop_id: Optional[int] = Field(
        None, description="Updated departure stop identifier"
    )
    arrival_stop_id: Optional[int] = Field(
        None, description="Updated arrival stop identifier"
    )


class TicketSeatChange(BaseModel):
    seat_num: int = Field(..., description="Target seat number on the tour")


class TicketReschedule(BaseModel):
    tour_id: int = Field(..., description="Target tour identifier")
    seat_num: int = Field(..., description="Desired seat number on the new tour")
    departure_stop_id: int = Field(..., description="Departure stop for the new segment")
    arrival_stop_id: int = Field(..., description="Arrival stop for the new segment")


def _resolve_actor(request: Request) -> tuple[str, str | None]:
    token = request.headers.get("X-Ticket-Token") or request.query_params.get("token")
    is_admin = getattr(request.state, "is_admin", False)
    jti = getattr(request.state, "jti", None)

    if token and not is_admin:
        try:
            payload = ticket_links.verify(token)
        except ticket_links.TicketLinkError as exc:
            raise HTTPException(401, "Invalid or missing ticket token") from exc
        jti = payload.get("jti") or jti

    actor = jti or ("admin" if is_admin else "system")
    return actor, jti


def _fetch_route_stops(cur, route_id: int) -> List[int]:
    cur.execute(
        'SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY "order"',
        (route_id,),
    )
    rows = cur.fetchall()
    if not rows:
        raise HTTPException(400, "Route has no stops configured")
    return [int(row[0]) for row in rows]


def _segments_between(
    stops: List[int], departure_stop_id: int, arrival_stop_id: int
) -> Tuple[List[str], List[Tuple[int, int]]]:
    if departure_stop_id not in stops or arrival_stop_id not in stops:
        raise HTTPException(400, "Invalid stops for this route")
    idx_from = stops.index(departure_stop_id)
    idx_to = stops.index(arrival_stop_id)
    if idx_from >= idx_to:
        raise HTTPException(400, "Arrival must come after departure")
    segment_tokens = [str(i + 1) for i in range(idx_from, idx_to)]
    segment_pairs = [(stops[i], stops[i + 1]) for i in range(idx_from, idx_to)]
    return segment_tokens, segment_pairs


def _merge_available(avail: Optional[str], segments: List[str]) -> str:
    base = "" if not avail or avail == "0" else avail
    merged = sorted(set(base + "".join(segments)), key=int)
    return "".join(merged) if merged else "0"


def _remove_segments(avail: Optional[str], segments: List[str]) -> str:
    base = "" if not avail or avail == "0" else avail
    updated = "".join(ch for ch in base if ch not in segments)
    return updated or "0"


def _ensure_segments_available(avail: Optional[str], segments: List[str]) -> None:
    base = "" if not avail or avail == "0" else avail
    for seg in segments:
        if seg not in base:
            raise HTTPException(409, "Seat is already occupied on the selected segment")


def _determine_scopes(context) -> set[str]:
    if getattr(context, "is_admin", False):
        return {"view", "download", "pay", "cancel", "edit", "seat", "reschedule"}
    return set(getattr(context, "scopes", []) or [])


def _build_allowed_actions(dto: Dict[str, Any], context) -> Dict[str, bool]:
    scopes = _determine_scopes(context)
    purchase = dto.get("purchase") or {}
    flags = purchase.get("flags") or dto.get("payment_status") or {}
    is_reserved = bool(flags.get("is_reserved"))
    is_active = bool(flags.get("is_active"))
    is_cancelled = bool(flags.get("is_cancelled"))

    return {
        "download_pdf": "download" in scopes,
        "pay": "pay" in scopes and is_reserved and not is_cancelled,
        "cancel": "cancel" in scopes and is_active,
        "update_passenger": "edit" in scopes,
        "change_seat": "seat" in scopes,
        "reschedule": "reschedule" in scopes,
    }


def _resolve_lang(request: Request, context) -> str:
    return (
        request.query_params.get("lang")
        or getattr(context, "lang", None)
        or "bg"
    )


def _load_ticket_details(
    ticket_id: int,
    request: Request,
    context,
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        lang = _resolve_lang(request, context)
        try:
            dto = get_ticket_dto(ticket_id, lang, conn)
        except ValueError as exc:
            raise HTTPException(404, "Ticket not found") from exc
    finally:
        conn.close()

    token = request.headers.get("X-Ticket-Token") or request.query_params.get("token")
    pdf_url: Optional[str] = None
    if token:
        pdf_url = f"/tickets/{ticket_id}/pdf?token={token}&lang={lang}"
    elif getattr(context, "is_admin", False):
        pdf_url = f"/tickets/{ticket_id}/pdf?lang={lang}"

    payload: Dict[str, Any] = {
        "data": dto,
        "lang": lang,
        "pdf_url": pdf_url,
        "allowed_actions": _build_allowed_actions(dto, context),
    }

    if getattr(context, "is_admin", False):
        payload["scopes"] = sorted(_determine_scopes(context))
    else:
        payload["scopes"] = sorted(set(getattr(context, "scopes", []) or []))
        link = getattr(context, "link", None) or {}
        payload["token"] = {
            "jti": getattr(context, "jti", None),
            "expires_at": link.get("exp"),
        }

    return payload


@router.get("/{ticket_id}")
def get_ticket_details(
    ticket_id: int,
    request: Request,
    context=Depends(require_scope("view")),
):
    guard_public_request(
        request,
        "view",
        ticket_id=ticket_id,
        context=context,
    )
    return _load_ticket_details(ticket_id, request, context)


@router.patch("/{ticket_id}")
def update_ticket_details(
    ticket_id: int,
    data: TicketUpdate,
    request: Request,
    context=Depends(require_scope("edit")),
):
    if not any(
        [
            data.passenger_name is not None,
            data.extra_baggage is not None,
            data.departure_stop_id is not None,
            data.arrival_stop_id is not None,
        ]
    ):
        raise HTTPException(400, "No fields provided for update")

    conn = get_connection()
    cur = conn.cursor()
    try:
        actor, jti = _resolve_actor(request)
        guard_public_request(
            request,
            "edit",
            ticket_id=ticket_id,
            context=context,
        )

        cur.execute(
            """
            SELECT passenger_id, seat_id, tour_id, departure_stop_id, arrival_stop_id
              FROM ticket
             WHERE id = %s
             FOR UPDATE
            """,
            (ticket_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        passenger_id, seat_id, tour_id, current_dep, current_arr = row

        cur.execute("SELECT route_id FROM tour WHERE id = %s", (tour_id,))
        route_row = cur.fetchone()
        if not route_row:
            raise HTTPException(404, "Tour not found")
        route_id = int(route_row[0])
        stops = _fetch_route_stops(cur, route_id)

        new_dep = data.departure_stop_id or current_dep
        new_arr = data.arrival_stop_id or current_arr

        segments_changed = new_dep != current_dep or new_arr != current_arr
        if segments_changed:
            old_segments, _ = _segments_between(stops, current_dep, current_arr)
            new_segments, _ = _segments_between(stops, new_dep, new_arr)

            cur.execute(
                "SELECT available FROM seat WHERE id = %s FOR UPDATE",
                (seat_id,),
            )
            seat_row = cur.fetchone()
            if not seat_row:
                raise HTTPException(404, "Seat not found")
            avail_str = seat_row[0]
            interim = _merge_available(avail_str, old_segments)
            _ensure_segments_available(interim, new_segments)
            final_avail = _remove_segments(interim, new_segments)
            cur.execute(
                "UPDATE seat SET available = %s WHERE id = %s",
                (final_avail, seat_id),
            )

        if data.passenger_name is not None:
            cur.execute(
                "UPDATE passenger SET name = %s WHERE id = %s",
                (data.passenger_name, passenger_id),
            )

        ticket_updates: List[str] = []
        params: List[Any] = []
        if data.extra_baggage is not None:
            ticket_updates.append("extra_baggage = %s")
            params.append(int(data.extra_baggage))
        if segments_changed:
            ticket_updates.append("departure_stop_id = %s")
            ticket_updates.append("arrival_stop_id = %s")
            params.extend([new_dep, new_arr])

        if ticket_updates:
            params.append(ticket_id)
            cur.execute(
                f"UPDATE ticket SET {', '.join(ticket_updates)} WHERE id = %s",
                params,
            )

        if segments_changed:
            recalc_available(cur, tour_id)

        conn.commit()
        if jti:
            logger.info("Ticket %s updated with token jti=%s by %s", ticket_id, jti, actor)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()

    return _load_ticket_details(ticket_id, request, context)


@router.post("/{ticket_id}/seat")
def change_ticket_seat(
    ticket_id: int,
    data: TicketSeatChange,
    request: Request,
    context=Depends(require_scope("seat")),
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        actor, jti = _resolve_actor(request)
        guard_public_request(
            request,
            "seat",
            ticket_id=ticket_id,
            context=context,
        )

        cur.execute(
            """
            SELECT seat_id, tour_id, departure_stop_id, arrival_stop_id
              FROM ticket
             WHERE id = %s
             FOR UPDATE
            """,
            (ticket_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        current_seat_id, tour_id, dep_id, arr_id = row

        cur.execute("SELECT route_id FROM tour WHERE id = %s", (tour_id,))
        route_row = cur.fetchone()
        if not route_row:
            raise HTTPException(404, "Tour not found")
        stops = _fetch_route_stops(cur, int(route_row[0]))
        segments, _ = _segments_between(stops, dep_id, arr_id)

        cur.execute(
            "SELECT available FROM seat WHERE id = %s FOR UPDATE",
            (current_seat_id,),
        )
        current_seat_row = cur.fetchone()
        if not current_seat_row:
            raise HTTPException(404, "Seat not found")
        current_avail = current_seat_row[0]

        cur.execute(
            "SELECT id, available FROM seat WHERE tour_id = %s AND seat_num = %s FOR UPDATE",
            (tour_id, data.seat_num),
        )
        new_seat_row = cur.fetchone()
        if not new_seat_row:
            raise HTTPException(404, "Seat not found")
        new_seat_id, new_avail = new_seat_row

        if new_seat_id == current_seat_id:
            conn.rollback()
            return _load_ticket_details(ticket_id, request, context)

        if new_avail == "0":
            raise HTTPException(400, "Seat is blocked")
        _ensure_segments_available(new_avail, segments)

        released_avail = _merge_available(current_avail, segments)
        updated_new_avail = _remove_segments(new_avail, segments)

        cur.execute(
            "UPDATE seat SET available = %s WHERE id = %s",
            (released_avail, current_seat_id),
        )
        cur.execute(
            "UPDATE seat SET available = %s WHERE id = %s",
            (updated_new_avail, new_seat_id),
        )
        cur.execute(
            "UPDATE ticket SET seat_id = %s WHERE id = %s",
            (new_seat_id, ticket_id),
        )

        recalc_available(cur, tour_id)
        conn.commit()
        if jti:
            logger.info(
                "Ticket %s seat changed to %s with token jti=%s by %s",
                ticket_id,
                data.seat_num,
                jti,
                actor,
            )
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()

    return _load_ticket_details(ticket_id, request, context)


@router.post("/{ticket_id}/reschedule")
def reschedule_ticket(
    ticket_id: int,
    data: TicketReschedule,
    request: Request,
    context=Depends(require_scope("reschedule")),
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        actor, jti = _resolve_actor(request)
        guard_public_request(
            request,
            "reschedule",
            ticket_id=ticket_id,
            context=context,
        )

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
            raise HTTPException(404, "Ticket not found")
        current_seat_id, current_tour_id, current_dep, current_arr = ticket_row

        cur.execute("SELECT route_id FROM tour WHERE id = %s", (current_tour_id,))
        current_route_row = cur.fetchone()
        if not current_route_row:
            raise HTTPException(404, "Tour not found")
        current_stops = _fetch_route_stops(cur, int(current_route_row[0]))
        current_segments, _ = _segments_between(
            current_stops, current_dep, current_arr
        )

        cur.execute(
            "SELECT available FROM seat WHERE id = %s FOR UPDATE",
            (current_seat_id,),
        )
        current_seat_row = cur.fetchone()
        if not current_seat_row:
            raise HTTPException(404, "Seat not found")
        current_avail = current_seat_row[0]

        cur.execute("SELECT route_id FROM tour WHERE id = %s", (data.tour_id,))
        target_route_row = cur.fetchone()
        if not target_route_row:
            raise HTTPException(404, "Target tour not found")
        target_stops = _fetch_route_stops(cur, int(target_route_row[0]))
        target_segments, _ = _segments_between(
            target_stops, data.departure_stop_id, data.arrival_stop_id
        )

        cur.execute(
            "SELECT id, available FROM seat WHERE tour_id = %s AND seat_num = %s FOR UPDATE",
            (data.tour_id, data.seat_num),
        )
        target_seat_row = cur.fetchone()
        if not target_seat_row:
            raise HTTPException(404, "Seat not found on target tour")
        target_seat_id, target_avail = target_seat_row
        if target_avail == "0":
            raise HTTPException(400, "Seat is blocked on target tour")

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
                   seat_id = %s,
                   departure_stop_id = %s,
                   arrival_stop_id = %s
             WHERE id = %s
            """,
            (
                data.tour_id,
                target_seat_id,
                data.departure_stop_id,
                data.arrival_stop_id,
                ticket_id,
            ),
        )

        recalc_available(cur, current_tour_id)
        if data.tour_id != current_tour_id:
            recalc_available(cur, data.tour_id)

        conn.commit()
        if jti:
            logger.info(
                "Ticket %s rescheduled to tour %s seat %s with token jti=%s by %s",
                ticket_id,
                data.tour_id,
                data.seat_num,
                jti,
                actor,
            )
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()

    return _load_ticket_details(ticket_id, request, context)


@router.get("/{ticket_id}/seat-map")
def get_ticket_seat_map(
    ticket_id: int,
    request: Request,
    departure_stop_id: Optional[int] = Query(None),
    arrival_stop_id: Optional[int] = Query(None),
    context=Depends(require_scope("view")),
):
    guard_public_request(
        request,
        "seat-map",
        ticket_id=ticket_id,
        context=context,
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT tour_id, seat_id, departure_stop_id, arrival_stop_id FROM ticket WHERE id = %s",
            (ticket_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        tour_id, seat_id, ticket_dep, ticket_arr = row

        dep_id = departure_stop_id or ticket_dep
        arr_id = arrival_stop_id or ticket_arr

        cur.execute("SELECT route_id FROM tour WHERE id = %s", (tour_id,))
        route_row = cur.fetchone()
        if not route_row:
            raise HTTPException(404, "Tour not found")
        stops = _fetch_route_stops(cur, int(route_row[0]))
        segments, segment_pairs = _segments_between(stops, dep_id, arr_id)

        cur.execute(
            "SELECT id, seat_num, available FROM seat WHERE tour_id = %s ORDER BY seat_num",
            (tour_id,),
        )
        seats = cur.fetchall()

        seat_list: List[Dict[str, Any]] = []
        for s_id, seat_num, avail_str in seats:
            available_segments = "" if not avail_str or avail_str == "0" else avail_str
            is_available = all(seg in available_segments for seg in segments)
            if s_id == seat_id:
                status = "selected"
            elif is_available:
                status = "available"
            else:
                status = "blocked"
            seat_list.append(
                {
                    "seat_id": s_id,
                    "seat_num": seat_num,
                    "status": status,
                }
            )

        return {
            "tour_id": tour_id,
            "segment": {
                "departure_stop_id": dep_id,
                "arrival_stop_id": arr_id,
                "pairs": segment_pairs,
            },
            "seats": seat_list,
        }
    finally:
        cur.close()
        conn.close()

@router.post("/", response_model=TicketOut)
def create_ticket(data: TicketCreate):
    conn = get_connection()
    cur = conn.cursor()
    ticket_spec: TicketIssueSpec | None = None
    try:
        # --- 1) Проверяем рейс и получаем route_id ---
        cur.execute("SELECT route_id, date FROM tour WHERE id = %s", (data.tour_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Tour not found")
        route_id, tour_date = row

        # --- 2) Ищем место и получаем строку available (строку-сегменты) ---
        cur.execute(
            "SELECT id, available FROM seat WHERE tour_id = %s AND seat_num = %s",
            (data.tour_id, data.seat_num),
        )
        seat_row = cur.fetchone()
        if not seat_row:
            raise HTTPException(404, "Seat not found")
        seat_id, avail_str = seat_row
        if avail_str == "0":
            raise HTTPException(400, "Seat is blocked")

        # --- 3) Получаем список остановок по порядку для маршрута ---
        cur.execute(
            "SELECT stop_id, departure_time FROM routestop WHERE route_id = %s ORDER BY \"order\"",
            (route_id,),
        )
        stop_rows = cur.fetchall()
        stops = [r[0] for r in stop_rows]
        stop_departures = {r[0]: r[1] for r in stop_rows}
        if data.departure_stop_id not in stops or data.arrival_stop_id not in stops:
            raise HTTPException(400, "Invalid stops for this route")
        idx_from = stops.index(data.departure_stop_id)
        idx_to   = stops.index(data.arrival_stop_id)
        if idx_from >= idx_to:
            raise HTTPException(400, "Arrival must come after departure")

        # --- 4) Проверяем, что все нужные сегменты свободны в seat.available ---
        segments = [str(i + 1) for i in range(idx_from, idx_to)]
        for seg in segments:
            if seg not in avail_str:
                raise HTTPException(400, "Seat is already occupied on this segment")

        # --- 5) Создаём запись в passenger ---
        cur.execute(
            "INSERT INTO passenger (name) VALUES (%s) RETURNING id",
            (data.passenger_name,),
        )
        passenger_id = cur.fetchone()[0]

        # --- 6) Создаём билет ---
        cur.execute(
            """
            INSERT INTO ticket
              (tour_id, seat_id, passenger_id, departure_stop_id, arrival_stop_id, purchase_id, extra_baggage)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data.tour_id,
                seat_id,
                passenger_id,
                data.departure_stop_id,
                data.arrival_stop_id,
                data.purchase_id,
                int(data.extra_baggage),
            ),
        )
        ticket_id = cur.fetchone()[0]
        departure_dt = combine_departure_datetime(
            tour_date, stop_departures.get(data.departure_stop_id)
        )
        ticket_spec = cast(
            TicketIssueSpec,
            {
                "ticket_id": ticket_id,
                "purchase_id": data.purchase_id,
                "departure_dt": departure_dt,
            },
        )

        # --- 7) Обновляем seat.available, убирая из строки занятые сегменты ---
        new_avail = "".join(ch for ch in avail_str if ch not in segments)
        if not new_avail:
            new_avail = "0"
        cur.execute(
            "UPDATE seat SET available = %s WHERE id = %s",
            (new_avail, seat_id),
        )

        # --- 8) Единым UPDATE уменьшаем seats в таблице available
        #     для всех комбинированных поездок, чьи от–до остановки
        #     пересекаются с купленным отрезком ---
        cur.execute(
            """
            UPDATE available
               SET seats = seats - 1
             WHERE tour_id = %s
               -- позиция начала available < позиция конца билета
               AND (
                 (SELECT "order" FROM routestop
                  WHERE route_id=%s AND stop_id=departure_stop_id)
                 <
                 (SELECT "order" FROM routestop
                  WHERE route_id=%s AND stop_id=%s)
               )
               -- позиция конца available > позиция начала билета
               AND (
                 (SELECT "order" FROM routestop
                  WHERE route_id=%s AND stop_id=arrival_stop_id)
                 >
                 (SELECT "order" FROM routestop
                  WHERE route_id=%s AND stop_id=%s)
               );
            """,
            (
                data.tour_id,
                route_id, route_id, data.arrival_stop_id,
                route_id, route_id, data.departure_stop_id,
            ),
        )

        conn.commit()

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()

    if ticket_spec is None:
        raise HTTPException(500, "Failed to create ticket")

    tickets = issue_ticket_links([ticket_spec], data.lang)
    if not tickets:
        raise HTTPException(500, "Failed to issue ticket link")

    return {
        "ticket_id": ticket_spec["ticket_id"],
        "deep_link": tickets[0]["deep_link"],
    }


@router.post("/reassign", status_code=204)
def reassign_ticket(
    data: TicketReassign,
    request: Request,
    context=Depends(require_scope("edit")),
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        _actor, jti = _resolve_actor(request)
        # 1) Ищем ticket_id и from_seat_id
        cur.execute(
            """
            SELECT t.id, s.id
            FROM ticket t
            JOIN seat s ON s.id = t.seat_id
            WHERE t.tour_id = %s AND s.seat_num = %s
            """,
            (data.tour_id, data.from_seat),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"No ticket on seat {data.from_seat}")
        from_ticket_id, from_seat_id = row

        # 2) Ищем to_seat_id
        cur.execute(
            "SELECT id FROM seat WHERE tour_id = %s AND seat_num = %s",
            (data.tour_id, data.to_seat),
        )
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, f"Seat {data.to_seat} not found")
        to_seat_id = r[0]

        # 3) Если на to_seat уже есть билет — свапаем места
        cur.execute(
            "SELECT id FROM ticket WHERE tour_id = %s AND seat_id = %s",
            (data.tour_id, to_seat_id),
        )
        swap = cur.fetchone()
        if swap:
            swap_ticket_id = swap[0]
            cur.execute(
                "UPDATE ticket SET seat_id = %s WHERE id = %s",
                (from_seat_id, swap_ticket_id),
            )

        # 4) Перемещаем исходный билет на to_seat
        cur.execute(
            "UPDATE ticket SET seat_id = %s WHERE id = %s",
            (to_seat_id, from_ticket_id),
        )

        conn.commit()
        if jti:
            logger.info(
                "Ticket reassigned on tour %s using token jti=%s", data.tour_id, jti
            )
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) Забираем информацию о билете
        cur.execute(
            """
            SELECT tour_id, seat_id, passenger_id, departure_stop_id, arrival_stop_id
            FROM ticket
            WHERE id = %s
            """,
            (ticket_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        tour_id, seat_id, passenger_id, dep_stop, arr_stop = row

        # 2) Получаем route_id
        cur.execute("SELECT route_id FROM tour WHERE id = %s", (tour_id,))
        rr = cur.fetchone()
        if not rr:
            raise HTTPException(500, "Tour not found")
        route_id = rr[0]

        # 3) Восстанавливаем строку seat.available
        cur.execute("SELECT available FROM seat WHERE id = %s", (seat_id,))
        avail_str = cur.fetchone()[0] or ""
        # находим порядок сегментов, которые нужно вернуть
        cur.execute(
            "SELECT \"order\" FROM routestop WHERE route_id=%s AND stop_id=%s",
            (route_id, dep_stop),
        )
        idx_from = cur.fetchone()[0] - 1  # -1, потому что segments считаем от 1
        cur.execute(
            "SELECT \"order\" FROM routestop WHERE route_id=%s AND stop_id=%s",
            (route_id, arr_stop),
        )
        idx_to = cur.fetchone()[0] - 1
        segments = [str(i + 1) for i in range(idx_from, idx_to)]

        merged = sorted(set(list(avail_str) + segments), key=lambda x: int(x))
        new_avail = "".join(merged) if merged else "0"
        cur.execute(
            "UPDATE seat SET available = %s WHERE id = %s",
            (new_avail, seat_id),
        )

        # 4) Единым UPDATE возвращаем seats для всех overlapping available
        cur.execute(
            """
            UPDATE available
               SET seats = seats + 1
             WHERE tour_id = %s
               AND (
                 (SELECT "order" FROM routestop
                  WHERE route_id=%s AND stop_id=departure_stop_id)
                 <
                 (SELECT "order" FROM routestop
                  WHERE route_id=%s AND stop_id=%s)
               )
               AND (
                 (SELECT "order" FROM routestop
                  WHERE route_id=%s AND stop_id=arrival_stop_id)
                 >
                 (SELECT "order" FROM routestop
                  WHERE route_id=%s AND stop_id=%s)
               );
            """,
            (
                tour_id,
                route_id, route_id, arr_stop,
                route_id, route_id, dep_stop,
            ),
        )

        # 5) Удаляем запись о билете и пассажира
        cur.execute("DELETE FROM ticket WHERE id = %s", (ticket_id,))
        cur.execute("DELETE FROM passenger WHERE id = %s", (passenger_id,))

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()
