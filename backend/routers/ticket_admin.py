from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from ..database import get_connection
from ..auth import require_admin_token

router = APIRouter(
    prefix="/admin/tickets",
    tags=["admin_tickets"],
    dependencies=[Depends(require_admin_token)],
)


class TicketInfo(BaseModel):
    ticket_id: int
    seat_num: int
    passenger_id: int
    passenger_name: str
    passenger_phone: str
    passenger_email: EmailStr
    departure_stop_id: int
    arrival_stop_id: int


class TicketUpdate(BaseModel):
    passenger_name: Optional[str]
    passenger_phone: Optional[str]
    passenger_email: Optional[EmailStr]
    departure_stop_id: Optional[int]
    arrival_stop_id: Optional[int]


class TicketReassign(BaseModel):
    ticket_id: int
    to_seat: int


@router.get("/", response_model=List[TicketInfo])
def list_tickets(tour_id: int = Query(..., description="ID рейса")):
    """
    Список проданных билетов для тура.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
              t.id, s.seat_num, t.passenger_id,
              p.name, p.phone, p.email,
              t.departure_stop_id, t.arrival_stop_id
            FROM ticket t
            JOIN seat s      ON s.id = t.seat_id
            JOIN passenger p ON p.id = t.passenger_id
            WHERE t.tour_id = %s
            ORDER BY s.seat_num
        """, (tour_id,))
        rows = cur.fetchall()
        return [
            TicketInfo(
                ticket_id=r[0],
                seat_num=r[1],
                passenger_id=r[2],
                passenger_name=r[3],
                passenger_phone=r[4],
                passenger_email=r[5],
                departure_stop_id=r[6],
                arrival_stop_id=r[7],
            )
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()


@router.put("/{ticket_id}", response_model=TicketInfo)
def update_ticket(ticket_id: int, data: TicketUpdate):
    """
    Частичное обновление данных пассажира и/или остановок в билете.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # passenger data
        cur.execute("SELECT passenger_id FROM ticket WHERE id = %s", (ticket_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        passenger_id = row[0]

        if any([data.passenger_name, data.passenger_phone, data.passenger_email]):
            cur.execute("""
                UPDATE passenger
                   SET name  = COALESCE(%s, name),
                       phone = COALESCE(%s, phone),
                       email = COALESCE(%s, email)
                 WHERE id = %s
            """, (
                data.passenger_name,
                data.passenger_phone,
                data.passenger_email,
                passenger_id
            ))

        # stops in ticket
        if data.departure_stop_id is not None or data.arrival_stop_id is not None:
            cur.execute("""
                UPDATE ticket
                   SET departure_stop_id = COALESCE(%s, departure_stop_id),
                       arrival_stop_id   = COALESCE(%s, arrival_stop_id)
                 WHERE id = %s
            """, (
                data.departure_stop_id,
                data.arrival_stop_id,
                ticket_id
            ))

        conn.commit()

        # return updated
        cur.execute("""
            SELECT
              t.id, s.seat_num, t.passenger_id,
              p.name, p.phone, p.email,
              t.departure_stop_id, t.arrival_stop_id
            FROM ticket t
            JOIN seat s      ON s.id = t.seat_id
            JOIN passenger p ON p.id = t.passenger_id
            WHERE t.id = %s
        """, (ticket_id,))
        updated = cur.fetchone()
        if not updated:
            raise HTTPException(404, "Ticket not found after update")

        return TicketInfo(
            ticket_id=updated[0],
            seat_num=updated[1],
            passenger_id=updated[2],
            passenger_name=updated[3],
            passenger_phone=updated[4],
            passenger_email=updated[5],
            departure_stop_id=updated[6],
            arrival_stop_id=updated[7],
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


@router.post("/reassign", status_code=204)
def reassign_ticket_admin(data: TicketReassign):
    """
    Пересадка пассажира на другое место в том же туре:
      1) меняем места в таблице seat: просто обмениваем их доступности (available) и номера
      2) обновляем seat_id в ticket
      3) не трогаем таблицу available
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) получаем старый seat_id и его available
        cur.execute("""
            SELECT seat_id
            FROM ticket
            WHERE id = %s
        """, (data.ticket_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        old_seat_id = row[0]

        # 2) находим новый seat_id и его available
        cur.execute("""
            SELECT id, available
            FROM seat
            WHERE tour_id = (
                SELECT tour_id FROM ticket WHERE id = %s
            ) AND seat_num = %s
        """, (data.ticket_id, data.to_seat))
        new = cur.fetchone()
        if not new:
            raise HTTPException(404, f"Seat {data.to_seat} not found")
        new_seat_id, new_avail = new

        # 3) получаем available старого места
        cur.execute("SELECT available FROM seat WHERE id = %s", (old_seat_id,))
        old_avail = cur.fetchone()[0] or ""

        # 4) меняем available между двумя seats
        cur.execute("""
            UPDATE seat
               SET available = CASE 
                 WHEN id = %s THEN %s
                 WHEN id = %s THEN %s
               END
             WHERE id IN (%s, %s)
        """, (old_seat_id, new_avail, new_seat_id, old_avail, old_seat_id, new_seat_id))

        # 5) обновляем ticket
        cur.execute("""
            UPDATE ticket
               SET seat_id = %s
             WHERE id = %s
        """, (new_seat_id, data.ticket_id))

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


@router.delete("/{ticket_id}", status_code=204)
def delete_ticket_admin(ticket_id: int):
    """
    Удаляем билет (паспорт остаётся) и возвращаем места:
      1) восстанавливаем seat.available по сегментам
      2) увеличиваем seats в таблице available только по сегментам
      3) удаляем запись ticket
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # детали билета
        cur.execute("""
            SELECT tour_id, seat_id, departure_stop_id, arrival_stop_id
            FROM ticket
            WHERE id = %s
        """, (ticket_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        tour_id, seat_id, dep, arr = row

        # маршрут и остановки
        cur.execute("SELECT route_id FROM tour WHERE id = %s", (tour_id,))
        route_id = cur.fetchone()[0]
        cur.execute("""
            SELECT stop_id FROM routestop
            WHERE route_id = %s ORDER BY "order"
        """, (route_id,))
        stops = [r[0] for r in cur.fetchall()]

        idx_from = stops.index(dep)
        idx_to   = stops.index(arr)
        if idx_from >= idx_to:
            raise HTTPException(400, "Invalid ticket stops")

        segments = [str(i+1) for i in range(idx_from, idx_to)]

        # вернуть seat.available
        cur.execute("SELECT available FROM seat WHERE id = %s", (seat_id,))
        old_avail = cur.fetchone()[0] or ""
        merged = sorted(set(old_avail + "".join(segments)), key=int)
        new_avail = "".join(merged) if merged else "0"
        cur.execute(
            "UPDATE seat SET available = %s WHERE id = %s",
            (new_avail, seat_id)
        )

        # увеличить available.seats по сегментам
        for i in range(idx_from, idx_to):
            d, a = stops[i], stops[i+1]
            cur.execute("""
                UPDATE available
                   SET seats = seats + 1
                 WHERE tour_id = %s
                   AND departure_stop_id = %s
                   AND arrival_stop_id   = %s
            """, (tour_id, d, a))

        # удалить билет
        cur.execute("DELETE FROM ticket WHERE id = %s", (ticket_id,))

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
