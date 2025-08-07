from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
from ..database import get_connection
from ..auth import require_admin_token
from ..models import Ticket, Sales

router = APIRouter(
    prefix="/admin/purchases",
    tags=["admin_purchases"],
    dependencies=[Depends(require_admin_token)],
)

class PurchaseRow(BaseModel):
    id: int
    created_at: Optional[str]
    customer_name: str
    customer_email: str
    customer_phone: str
    tour_date: Optional[str]
    route_name: Optional[str]
    departure_stop: Optional[str]
    arrival_stop: Optional[str]
    seats: List[int]
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
              tr.date,
              r.name,
              ds.stop_name,
              as_.stop_name,
              ARRAY_AGG(s.seat_num) AS seats,
              pu.amount_due,
              pu.status,
              pu.deadline,
              pu.payment_method
            FROM purchase pu
            LEFT JOIN ticket t ON t.purchase_id = pu.id
            LEFT JOIN seat s ON s.id = t.seat_id
            LEFT JOIN tour tr ON tr.id = t.tour_id
            LEFT JOIN route r ON r.id = tr.route_id
            LEFT JOIN stop ds ON ds.id = t.departure_stop_id
            LEFT JOIN stop as_ ON as_.id = t.arrival_stop_id
            {where_clause}
            GROUP BY pu.id, pu.update_at, pu.customer_name, pu.customer_email, pu.customer_phone,
                     tr.date, r.name, ds.stop_name, as_.stop_name,
                     pu.amount_due, pu.status, pu.deadline, pu.payment_method
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
                    "tour_date": r[5].isoformat() if r[5] else None,
                    "route_name": r[6],
                    "departure_stop": r[7],
                    "arrival_stop": r[8],
                    "seats": r[9] if r[9] is not None else [],
                    "amount_due": float(r[10]) if r[10] is not None else 0.0,
                    "status": r[11],
                    "deadline": r[12].isoformat() if r[12] else None,
                    "payment_method": r[13],
                }
            )
        return purchases
    finally:
        cur.close()
        conn.close()


class PurchaseInfo(BaseModel):
    tickets: List[Ticket]
    sales: List[Sales]


@router.get("/{purchase_id}", response_model=PurchaseInfo)
def purchase_info(purchase_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, tour_id, seat_id, passenger_id,
                   departure_stop_id, arrival_stop_id,
                   purchase_id, extra_baggage
            FROM ticket WHERE purchase_id=%s
            """,
            (purchase_id,),
        )
        t_rows = cur.fetchall()
        tickets = [
            {
                "id": r[0],
                "tour_id": r[1],
                "seat_id": r[2],
                "passenger_id": r[3],
                "departure_stop_id": r[4],
                "arrival_stop_id": r[5],
                "purchase_id": r[6],
                "extra_baggage": r[7],
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
