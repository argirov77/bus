from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime
from ..database import get_connection

router = APIRouter(prefix="/purchase", tags=["purchase"])
# second router exposing simplified endpoints without the /purchase prefix
actions_router = APIRouter(tags=["purchase"])

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

def _log_sale(cur, purchase_id: int, category: str, amount: float = 0.0) -> None:
    cur.execute(
        "INSERT INTO sales (purchase_id, category, amount) VALUES (%s, %s, %s)",
        (purchase_id, category, amount),
    )


def _create_purchase(cur, data: PurchaseCreate, status: str) -> int:
    """Helper that inserts passenger, purchase and ticket records."""
    # 1) create passenger
    cur.execute(
        "INSERT INTO passenger (name) VALUES (%s) RETURNING id",
        (data.passenger_name,),
    )
    passenger_id = cur.fetchone()[0]

    # 2) create purchase record
    cur.execute(
        """
        INSERT INTO purchase
          (customer_name, customer_email, customer_phone, amount_due, deadline, status, update_at, payment_method)
        VALUES (%s,%s,%s,0,NOW() + interval '1 day',%s,NOW(),'online')
        RETURNING id
        """,
        (data.passenger_name, data.passenger_email, data.passenger_phone, status),
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
            int(data.extra_baggage),
        ),
    )
    cur.fetchone()

    _log_sale(cur, purchase_id, "ticket_sale", 0)
    return purchase_id

@router.post("/", response_model=PurchaseOut)
def create_purchase(data: PurchaseCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        purchase_id = _create_purchase(cur, data, "reserved")
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
            "UPDATE purchase SET status='paid', update_at=NOW() WHERE id=%s",
            (purchase_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Purchase not found")
        _log_sale(cur, purchase_id, "ticket_sale", 0)
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
            "UPDATE purchase SET status='cancelled', update_at=NOW() WHERE id=%s",
            (purchase_id,),
        )
        _log_sale(cur, purchase_id, "refund", 0)
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


# --- Public endpoints without /purchase prefix ---

class PayIn(BaseModel):
    purchase_id: int


@actions_router.post("/book", response_model=PurchaseOut)
def book_seat(data: PurchaseCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        purchase_id = _create_purchase(cur, data, "reserved")
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


@actions_router.post("/purchase", response_model=PurchaseOut)
def purchase_and_pay(data: PurchaseCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        purchase_id = _create_purchase(cur, data, "paid")
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


@actions_router.post("/pay", status_code=204)
def pay_booking(data: PayIn):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE purchase SET status='paid', update_at=NOW() WHERE id=%s",
            (data.purchase_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Purchase not found")
        _log_sale(cur, data.purchase_id, "ticket_sale", 0)
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


@actions_router.post("/cancel/{purchase_id}", status_code=204)
def cancel_booking(purchase_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT status FROM purchase WHERE id=%s", (purchase_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Purchase not found")
        if row[0] != "reserved":
            raise HTTPException(400, "Only reserved bookings can be cancelled")

        cur.execute(
            "SELECT id FROM ticket WHERE purchase_id=%s",
            (purchase_id,),
        )
        t = cur.fetchone()
        if t:
            cur.execute("DELETE FROM ticket WHERE id=%s", (t[0],))

        cur.execute(
            "UPDATE purchase SET status='cancelled', update_at=NOW() WHERE id=%s",
            (purchase_id,),
        )
        _log_sale(cur, purchase_id, "refund", 0)
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


@actions_router.post("/refund/{purchase_id}", status_code=204)
def refund_purchase(purchase_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT status FROM purchase WHERE id=%s", (purchase_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Purchase not found")
        if row[0] != "paid":
            raise HTTPException(400, "Only paid purchases can be refunded")

        cur.execute(
            "SELECT id FROM ticket WHERE purchase_id=%s",
            (purchase_id,),
        )
        t = cur.fetchone()
        if t:
            cur.execute("DELETE FROM ticket WHERE id=%s", (t[0],))

        cur.execute(
            "UPDATE purchase SET status='refunded', update_at=NOW() WHERE id=%s",
            (purchase_id,),
        )
        _log_sale(cur, purchase_id, "refund", 0)
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
