from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from ..database import get_connection

router = APIRouter(prefix="/purchase", tags=["purchase"])

class PurchaseCreate(BaseModel):
    tour_id: int
    seat_num: int
    passenger_name: str
    passenger_phone: str
    passenger_email: EmailStr
    departure_stop_id: int
    arrival_stop_id: int
    extra_baggage: bool = False

class PurchaseOut(BaseModel):
    purchase_id: int


def _log_status(cur, purchase_id: int, status: str) -> None:
    cur.execute(
        "INSERT INTO sales (purchase_id, status) VALUES (%s, %s)",
        (purchase_id, status),
    )


@router.post("/", response_model=PurchaseOut)
def create_purchase(data: PurchaseCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) create passenger
        cur.execute(
            "INSERT INTO passenger (name, phone, email) VALUES (%s,%s,%s) RETURNING id",
            (data.passenger_name, data.passenger_phone, data.passenger_email),
        )
        passenger_id = cur.fetchone()[0]

        # 2) create purchase record
        cur.execute(
            "INSERT INTO purchase (status) VALUES ('reserved') RETURNING id",
        )
        purchase_id = cur.fetchone()[0]

        # 3) delegate to ticket creation logic
        cur.execute(
            "SELECT id FROM seat WHERE tour_id=%s AND seat_num=%s",
            (data.tour_id, data.seat_num),
        )
        seat_row = cur.fetchone()
        if not seat_row:
            raise HTTPException(404, "Seat not found")
        seat_id = seat_row[0]

        cur.execute(
            """
            INSERT INTO ticket
              (tour_id, seat_id, passenger_id, departure_stop_id, arrival_stop_id, purchase_id, extra_baggage)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                data.tour_id,
                seat_id,
                passenger_id,
                data.departure_stop_id,
                data.arrival_stop_id,
                purchase_id,
                data.extra_baggage,
            ),
        )
        cur.fetchone()

        _log_status(cur, purchase_id, "reserved")
        conn.commit()
        return {"purchase_id": purchase_id}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()


@router.post("/{purchase_id}/pay", status_code=204)
def pay_purchase(purchase_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE purchase SET status='paid', updated_at=NOW() WHERE id=%s",
            (purchase_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Purchase not found")
        _log_status(cur, purchase_id, "paid")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()


@router.post("/{purchase_id}/cancel", status_code=204)
def cancel_purchase(purchase_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # find ticket
        cur.execute(
            "SELECT id, seat_id FROM ticket WHERE purchase_id=%s",
            (purchase_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Purchase not found")
        ticket_id, seat_id = row

        cur.execute("DELETE FROM ticket WHERE id=%s", (ticket_id,))
        cur.execute(
            "UPDATE purchase SET status='cancelled', updated_at=NOW() WHERE id=%s",
            (purchase_id,),
        )
        _log_status(cur, purchase_id, "cancelled")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()
