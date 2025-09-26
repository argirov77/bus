# backend/app/routers/ticket.py

from typing import cast

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

from ..auth import require_scope
from ..database import get_connection
from ._ticket_link_helpers import (
    TicketIssueSpec,
    build_deep_link,
    combine_departure_datetime,
    issue_ticket_links,
)
from ..services.ticket_dto import get_ticket_dto
from ..services.ticket_pdf import render_ticket_pdf
from ..services import ticket_links

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
    context=Depends(require_scope("view")),
):
    conn = get_connection()
    try:
        resolved_lang = lang or getattr(context, "lang", None) or "bg"
        try:
            dto = get_ticket_dto(ticket_id, resolved_lang, conn)
        except ValueError as exc:
            raise HTTPException(404, "Ticket not found") from exc
    finally:
        conn.close()

    token = request.query_params.get("token") or request.headers.get("X-Ticket-Token")
    deep_link = build_deep_link(ticket_id, token) if token else None

    pdf_bytes = render_ticket_pdf(dto, deep_link)
    headers = {
        "Content-Disposition": f'inline; filename="ticket-{ticket_id}.pdf"',
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


class TicketReassign(BaseModel):
    tour_id:   int
    from_seat: int
    to_seat:   int


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
