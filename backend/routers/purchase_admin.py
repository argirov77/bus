from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
from ..database import get_connection
from ..auth import require_admin_token
from ..models import Sales

router = APIRouter(
    prefix="/admin/purchases",
    tags=["admin_purchases"],
    dependencies=[Depends(require_admin_token)],
)

class PurchaseRow(BaseModel):
    """Summary information about a purchase.

    Earlier the admin purchase list combined ticket details directly in the SQL
    query which led to multiple rows being returned for a single purchase when
    the order contained tickets for different tours (e.g. a return trip).
    To present the information ergonomically we now return one row per purchase
    and load ticket details separately.
    """

    id: int
    created_at: Optional[str]
    customer_name: str
    customer_email: str
    customer_phone: str
    amount_due: float
    status: str
    deadline: Optional[str]
    payment_method: str

@router.get("/", response_model=List[PurchaseRow])
def list_purchases(
    status: Optional[str] = Query(None, description="Filter by status"),
    email: Optional[str] = Query(None, description="Filter by customer email"),
    order_id: Optional[int] = Query(None, description="Filter by purchase id"),
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        conditions = []
        params = []
        if status:
            conditions.append("pu.status = %s")
            params.append(status)
        if email:
            conditions.append("pu.customer_email = %s")
            params.append(email)
        if order_id:
            conditions.append("pu.id = %s")
            params.append(order_id)
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        cur.execute(
            f"""
            SELECT
              pu.id,
              pu.update_at,
              pu.customer_name,
              pu.customer_email,
              pu.customer_phone,
              pu.amount_due,
              pu.status,
              pu.deadline,
              pu.payment_method
            FROM purchase pu
            {where_clause}
            ORDER BY pu.id DESC
            """,
            tuple(params),
        )
        rows = cur.fetchall()
        purchases = []
        for r in rows:
            purchases.append(
                {
                    "id": r[0],
                    "created_at": r[1].isoformat() if r[1] else None,
                    "customer_name": r[2],
                    "customer_email": r[3],
                    "customer_phone": r[4],
                    "amount_due": float(r[5]) if r[5] is not None else 0.0,
                    "status": r[6],
                    "deadline": r[7].isoformat() if r[7] else None,
                    "payment_method": r[8],
                }
            )
        return purchases
    finally:
        cur.close()
        conn.close()


class TicketInfo(BaseModel):
    id: int
    tour_id: int
    tour_date: Optional[str]
    seat_id: int
    seat_num: int
    passenger_id: int
    passenger_name: str
    departure_stop_id: int
    arrival_stop_id: int
    purchase_id: int
    extra_baggage: int


class PurchaseInfo(BaseModel):
    tickets: List[TicketInfo]
    sales: List[Sales]


@router.get("/{purchase_id}", response_model=PurchaseInfo)
def purchase_info(purchase_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT t.id, t.tour_id, tr.date, t.seat_id, s.seat_num, t.passenger_id, p.name,
                   t.departure_stop_id, t.arrival_stop_id,
                   t.purchase_id, t.extra_baggage
            FROM ticket t
            LEFT JOIN seat s ON s.id = t.seat_id
            LEFT JOIN passenger p ON p.id = t.passenger_id
            LEFT JOIN tour tr ON tr.id = t.tour_id
            WHERE t.purchase_id=%s
            """,
            (purchase_id,),
        )
        t_rows = cur.fetchall()
        tickets = [
            {
                "id": r[0],
                "tour_id": r[1],
                "tour_date": r[2].isoformat() if r[2] else None,
                "seat_id": r[3],
                "seat_num": r[4],
                "passenger_id": r[5],
                "passenger_name": r[6],
                "departure_stop_id": r[7],
                "arrival_stop_id": r[8],
                "purchase_id": r[9],
                "extra_baggage": r[10],
            }
            for r in t_rows
        ]

        cur.execute(
            """
            SELECT id, date, category, amount, purchase_id, comment
            FROM sales WHERE purchase_id=%s ORDER BY date
            """,
            (purchase_id,),
        )
        s_rows = cur.fetchall()
        sales = [
            {
                "id": r[0],
                "date": r[1],
                "category": r[2],
                "amount": float(r[3]),
                "purchase_id": r[4],
                "comment": r[5],
            }
            for r in s_rows
        ]

        return {"tickets": tickets, "sales": sales}
    finally:
        cur.close()
        conn.close()
