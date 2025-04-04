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
        cur.execute("""
            INSERT INTO passenger (name, phone, email)
            VALUES (%s, %s, %s) RETURNING id;
        """, (ticket.passenger_name, ticket.passenger_phone, ticket.passenger_email))
        passenger_id = cur.fetchone()[0]

        cur.execute("SELECT id, available FROM seat WHERE tour_id=%s AND seat_num=%s;",
                    (ticket.tour_id, ticket.seat_num))
        seat_data = cur.fetchone()
        if not seat_data:
            raise HTTPException(status_code=404, detail="Seat not found")

        seat_id, available = seat_data
        segments_to_book = set(range(ticket.departure_stop_id, ticket.arrival_stop_id))

        if not all(str(seg) in available for seg in segments_to_book):
            raise HTTPException(status_code=400, detail="Seat already booked for selected segments")

        for segment in segments_to_book:
            available = available.replace(str(segment), "")
        cur.execute("UPDATE seat SET available=%s WHERE id=%s;", (available, seat_id))

        cur.execute("""
            INSERT INTO ticket (tour_id, seat_id, passenger_id, departure_stop_id, arrival_stop_id)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """, (ticket.tour_id, seat_id, passenger_id, ticket.departure_stop_id, ticket.arrival_stop_id))

        cur.execute("""
            UPDATE available SET seats = seats - 1
            WHERE tour_id=%s AND departure_stop_id <= %s AND arrival_stop_id >= %s;
        """, (ticket.tour_id, ticket.departure_stop_id, ticket.arrival_stop_id))

        conn.commit()
        return {"ticket_id": cur.fetchone()[0], "passenger_id": passenger_id}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
