# backend/app/routers/ticket_admin.py

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from database import get_connection

router = APIRouter(prefix="/admin/tickets", tags=["admin_tickets"])


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


@router.get("/", response_model=List[TicketInfo])
def list_tickets(tour_id: int = Query(..., description="ID рейса")):
    """
    Возвращает список проданных билетов для данного тура.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
              t.id,
              s.seat_num,
              t.passenger_id,
              p.name,
              p.phone,
              p.email,
              t.departure_stop_id,
              t.arrival_stop_id
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
    Частичное обновление информации о пассажире и/или остановок в билете.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) Убедимся, что билет существует, и получим passenger_id
        cur.execute("SELECT passenger_id FROM ticket WHERE id = %s", (ticket_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        passenger_id = row[0]

        # 2) Обновляем данные пассажира
        if any([data.passenger_name, data.passenger_phone, data.passenger_email]):
            cur.execute(
                """
                UPDATE passenger
                SET
                  name  = COALESCE(%s, name),
                  phone = COALESCE(%s, phone),
                  email = COALESCE(%s, email)
                WHERE id = %s
                """,
                (data.passenger_name, data.passenger_phone, data.passenger_email, passenger_id)
            )

        # 3) Обновляем остановки в билете
        if data.departure_stop_id is not None or data.arrival_stop_id is not None:
            cur.execute(
                """
                UPDATE ticket
                SET
                  departure_stop_id = COALESCE(%s, departure_stop_id),
                  arrival_stop_id   = COALESCE(%s, arrival_stop_id)
                WHERE id = %s
                """,
                (data.departure_stop_id, data.arrival_stop_id, ticket_id)
            )

        conn.commit()

        # 4) Вернём обновлённую запись
        cur.execute("""
            SELECT 
              t.id,
              s.seat_num,
              t.passenger_id,
              p.name,
              p.phone,
              p.email,
              t.departure_stop_id,
              t.arrival_stop_id
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


@router.delete("/{ticket_id}", status_code=204)
def delete_ticket_admin(ticket_id: int):
    """
    Удаляем только билет (passenger остаётся), и «освобождаем» занятые сегменты:
    1) возвращаем их в строку seat.available
    2) увеличиваем seats в таблице available для каждого сегмента
    3) удаляем саму запись в ticket
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) Получаем детали по билету
        cur.execute("""
            SELECT tour_id, seat_id, departure_stop_id, arrival_stop_id
            FROM ticket
            WHERE id = %s
        """, (ticket_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        tour_id, seat_id, dep_stop, arr_stop = row

        # 2) Узнаём маршрут и все остановки по порядку
        cur.execute("SELECT route_id FROM tour WHERE id = %s", (tour_id,))
        route = cur.fetchone()
        if not route:
            raise HTTPException(500, "Tour not found")
        route_id = route[0]

        cur.execute(
            "SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY \"order\"",
            (route_id,),
        )
        stops = [r[0] for r in cur.fetchall()]

        idx_from = stops.index(dep_stop)
        idx_to   = stops.index(arr_stop)
        if idx_from >= idx_to:
            raise HTTPException(500, "Invalid ticket stops")

        # 3) Восстанавливаем сегменты
        segments = [str(i + 1) for i in range(idx_from, idx_to)]

        # 3a) Получаем текущую строку available
        cur.execute("SELECT available FROM seat WHERE id = %s", (seat_id,))
        avail_str = cur.fetchone()[0] or ""

        # 3b) Объединяем и сортируем
        merged = sorted(
            set(list(avail_str) + segments),
            key=lambda x: int(x)
        )
        new_avail = "".join(merged) if merged else "0"

        cur.execute(
            "UPDATE seat SET available = %s WHERE id = %s",
            (new_avail, seat_id),
        )

        # 4) Увеличиваем счётчики в таблице available
        for i in range(idx_from, idx_to):
            dep = stops[i]
            arr = stops[i + 1]
            cur.execute(
                """
                UPDATE available
                SET seats = seats + 1
                WHERE tour_id = %s
                  AND departure_stop_id = %s
                  AND arrival_stop_id   = %s
                """,
                (tour_id, dep, arr),
            )

        # 5) Наконец, удаляем сам билет
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
