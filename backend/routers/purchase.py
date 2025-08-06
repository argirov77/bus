from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime
from ..database import get_connection
from ..ticket_utils import free_ticket

router = APIRouter(prefix="/purchase", tags=["purchase"])
# second router exposing simplified endpoints without the /purchase prefix
actions_router = APIRouter(tags=["purchase"])

class PurchaseCreate(BaseModel):
    tour_id: int
    seat_nums: list[int]
    passenger_names: list[str]
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


def _create_purchase(
    cur, data: PurchaseCreate, status: str, payment_method: str = "online"
) -> int:
    """Helper that inserts passengers, purchase and ticket records."""

    if len(data.seat_nums) != len(data.passenger_names):
        raise HTTPException(400, "Seat numbers and passenger names count mismatch")

    # 1) create purchase record using first passenger as customer name
    cur.execute(
        f"""
        INSERT INTO purchase
          (customer_name, customer_email, customer_phone, amount_due, deadline, status, update_at, payment_method)
        VALUES (%s,%s,%s,0,NOW() + interval '1 day','{status}',NOW(),%s)
        RETURNING id
        """,
        (
            data.passenger_names[0] if data.passenger_names else "",
            data.passenger_email,
            data.passenger_phone,
            payment_method,
        ),
    )
    purchase_id = cur.fetchone()[0]

    # 2) create passenger and ticket for each seat
    for seat_num, name in zip(data.seat_nums, data.passenger_names):
        cur.execute(
            "INSERT INTO passenger (name) VALUES (%s) RETURNING id",
            (name,),
        )
        passenger_id = cur.fetchone()[0]

        cur.execute(
            "SELECT id FROM seat WHERE tour_id=%s AND seat_num=%s",
            (data.tour_id, seat_num),
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
        cur.execute(
            "SELECT id FROM ticket WHERE purchase_id=%s",
            (purchase_id,),
        )
        tickets = [row[0] for row in cur.fetchall()]
        if not tickets:
            raise HTTPException(404, "Purchase not found")

        for t_id in tickets:
            free_ticket(cur, t_id)

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
        purchase_id = _create_purchase(cur, data, "paid", "offline")
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
        cur.execute(
            "SELECT id FROM ticket WHERE purchase_id=%s",
            (purchase_id,),
        )
        tickets = [row[0] for row in cur.fetchall()]
        if not tickets:
            raise HTTPException(404, "Purchase not found")

        for t_id in tickets:
            free_ticket(cur, t_id)

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
