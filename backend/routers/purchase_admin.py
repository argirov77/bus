from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from ..database import get_connection
from ..auth import require_admin_token
from ..models import PurchaseLog

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
    payment_status: Optional[str] = None
    liqpay_order_id: Optional[str] = None
    liqpay_payment_id: Optional[str] = None
    liqpay_status: Optional[str] = None
    fiscal_status: Optional[str] = None
    fiscal_last_error: Optional[str] = None
    checkbox_receipt_id: Optional[str] = None
    fiscal_receipt_url: Optional[str] = None

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
              pu.payment_method,
              pu.status AS payment_status,
              pu.liqpay_order_id,
              pu.liqpay_payment_id,
              pu.liqpay_status,
              pu.fiscal_status,
              pu.fiscal_last_error,
              pu.checkbox_receipt_id,
              pu.fiscal_receipt_url
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
                    "payment_status": r[9],
                    "liqpay_order_id": r[10],
                    "liqpay_payment_id": r[11],
                    "liqpay_status": r[12],
                    "fiscal_status": r[13],
                    "fiscal_last_error": r[14],
                    "checkbox_receipt_id": r[15],
                    "fiscal_receipt_url": r[16],
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
    from_stop_name: Optional[str]
    arrival_stop_id: int
    to_stop_name: Optional[str]
    purchase_id: int
    extra_baggage: int


class PurchaseInfo(BaseModel):
    tickets: List[TicketInfo]
    logs: List[PurchaseLog]
    payment_status: Optional[str] = None
    liqpay_order_id: Optional[str] = None
    liqpay_payment_id: Optional[str] = None
    liqpay_status: Optional[str] = None
    fiscal_status: Optional[str] = None
    fiscal_last_error: Optional[str] = None
    checkbox_receipt_id: Optional[str] = None
    fiscal_receipt_url: Optional[str] = None
    fiscal_payload: Optional[dict] = None


@router.get("/{purchase_id}", response_model=PurchaseInfo)
def purchase_info(purchase_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT t.id, t.tour_id, tr.date, t.seat_id, s.seat_num, t.passenger_id, p.name,
                   t.departure_stop_id, ds.stop_name, t.arrival_stop_id, ar.stop_name,
                   t.purchase_id, t.extra_baggage
            FROM ticket t
            LEFT JOIN seat s ON s.id = t.seat_id
            LEFT JOIN passenger p ON p.id = t.passenger_id
            LEFT JOIN tour tr ON tr.id = t.tour_id
            LEFT JOIN stop ds ON ds.id = t.departure_stop_id
            LEFT JOIN stop ar ON ar.id = t.arrival_stop_id
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
                "from_stop_name": r[8],
                "arrival_stop_id": r[9],
                "to_stop_name": r[10],
                "purchase_id": r[11],
                "extra_baggage": r[12],
            }
            for r in t_rows
        ]

        cur.execute(
            """
            SELECT id, date, category, amount, purchase_id, actor, method
            FROM sales WHERE purchase_id=%s ORDER BY date
            """,
            (purchase_id,),
        )
        s_rows = cur.fetchall()
        logs = [
            {
                "id": r[0],
                "at": r[1],
                "action": r[2],
                "amount": float(r[3]),
                "purchase_id": r[4],
                "by": r[5],
                "method": r[6],
            }
            for r in s_rows
        ]

        cur.execute(
            """
            SELECT status, liqpay_order_id, liqpay_payment_id, liqpay_status,
                   fiscal_status, fiscal_last_error, checkbox_receipt_id, fiscal_receipt_url, fiscal_payload
            FROM purchase
            WHERE id=%s
            """,
            (purchase_id,),
        )
        p_row = cur.fetchone()

        return {
            "tickets": tickets,
            "logs": logs,
            "payment_status": p_row[0] if p_row else None,
            "liqpay_order_id": p_row[1] if p_row else None,
            "liqpay_payment_id": p_row[2] if p_row else None,
            "liqpay_status": p_row[3] if p_row else None,
            "fiscal_status": p_row[4] if p_row else None,
            "fiscal_last_error": p_row[5] if p_row else None,
            "checkbox_receipt_id": p_row[6] if p_row else None,
            "fiscal_receipt_url": p_row[7] if p_row else None,
            "fiscal_payload": p_row[8] if p_row else None,
        }
    finally:
        cur.close()
        conn.close()


@router.post("/{purchase_id}/retry-fiscalization")
def retry_fiscalization(purchase_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, status, fiscal_status, checkbox_receipt_id
            FROM purchase
            WHERE id = %s
            """,
            (purchase_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Purchase not found")
        _, status, fiscal_status, receipt_id = row
        if status != "paid":
            raise HTTPException(status_code=409, detail=f"Purchase must be paid (current status: {status})")
        if receipt_id:
            raise HTTPException(status_code=409, detail=f"Purchase already has receipt id: {receipt_id}")
        if fiscal_status not in ("pending", "failed"):
            raise HTTPException(status_code=409, detail=f"Fiscal status does not allow retry: {fiscal_status}")
    finally:
        cur.close()
        conn.close()

    from ..services.checkbox import fiscalize_purchase

    fiscalize_purchase(purchase_id)

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT status, fiscal_status, checkbox_receipt_id, fiscal_receipt_url, fiscal_last_error
            FROM purchase
            WHERE id = %s
            """,
            (purchase_id,),
        )
        status, fiscal_status, receipt_id, receipt_url, fiscal_last_error = cur.fetchone()
        return {
            "purchase_id": purchase_id,
            "payment_status": status,
            "fiscal_status": fiscal_status,
            "checkbox_receipt_id": receipt_id,
            "fiscal_receipt_url": receipt_url,
            "fiscal_last_error": fiscal_last_error,
        }
    finally:
        cur.close()
        conn.close()
