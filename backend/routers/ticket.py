from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_connection

router = APIRouter(prefix="/tickets", tags=["tickets"])

class TicketCreate(BaseModel):
    tour_id: int
    seat_num: int
    passenger_name: str
    passenger_phone: str = None
    passenger_email: str = None
    departure_stop_id: int
    arrival_stop_id: int


@router.post("/")
def create_ticket(ticket: TicketCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Создаём пассажира
        #    Предполагаем, что мы всегда создаём новую запись (или можно искать по email).
        cur.execute("""
            INSERT INTO passenger (name, phone, email)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (ticket.passenger_name, ticket.passenger_phone, ticket.passenger_email))
        passenger_id = cur.fetchone()[0]

        # 2. Находим seat_id по tour_id + seat_num
        cur.execute("""
            SELECT id, available
            FROM seat
            WHERE tour_id = %s AND seat_num = %s
        """, (ticket.tour_id, ticket.seat_num))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Место не найдено для этого рейса")
        seat_id, available_str = row

        # 3. Проверяем доступность сегментов
        segments_to_remove = "".join(str(i) for i in range(ticket.departure_stop_id, ticket.arrival_stop_id))
        if segments_to_remove not in available_str:
            raise HTTPException(status_code=400, detail="Место уже занято на выбранном участке")

        # 4. Обновляем поле available в таблице seat
        new_available = available_str.replace(segments_to_remove, "")
        cur.execute("""
            UPDATE seat
            SET available = %s
            WHERE id = %s
        """, (new_available, seat_id))

        # 5. Создаём запись в ticket
        cur.execute("""
            INSERT INTO ticket (tour_id, seat_id, passenger_id, departure_stop_id, arrival_stop_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """, (ticket.tour_id, seat_id, passenger_id, ticket.departure_stop_id, ticket.arrival_stop_id))
        ticket_id = cur.fetchone()[0]

        # 6. Обновляем таблицу available (уменьшаем seats)
        cur.execute("""
            UPDATE available
            SET seats = seats - 1
            WHERE tour_id = %s
              AND departure_stop_id = %s
              AND arrival_stop_id = %s
        """, (ticket.tour_id, ticket.departure_stop_id, ticket.arrival_stop_id))

        conn.commit()
        return {"ticket_id": ticket_id, "passenger_id": passenger_id}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
