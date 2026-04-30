from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from ..auth import require_admin_token
from ..database import get_connection

router = APIRouter(
    prefix="/admin/ops",
    tags=["admin_ops"],
    dependencies=[Depends(require_admin_token)],
)


@router.get("/health")
def ops_health() -> dict[str, Any]:
    """Aggregated integrations and error queue health for ops dashboards."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # LiqPay status snapshot from latest integration events.
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE provider = 'liqpay') AS total,
              COUNT(*) FILTER (WHERE provider = 'liqpay' AND status IN ('success', 'ok', 'paid')) AS success,
              COUNT(*) FILTER (WHERE provider = 'liqpay' AND status IN ('failed', 'error')) AS failed,
              MAX(created_at) FILTER (WHERE provider = 'liqpay') AS last_event_at
            FROM integration_events
            """
        )
        liqpay_row = cur.fetchone()

        # CheckBox status snapshot from latest integration events.
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE provider = 'checkbox') AS total,
              COUNT(*) FILTER (WHERE provider = 'checkbox' AND status IN ('success', 'done', 'ok')) AS success,
              COUNT(*) FILTER (WHERE provider = 'checkbox' AND status IN ('failed', 'error')) AS failed,
              MAX(created_at) FILTER (WHERE provider = 'checkbox') AS last_event_at
            FROM integration_events
            """
        )
        checkbox_row = cur.fetchone()

        # Error queues / operational backlog.
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE fiscal_status = 'failed') AS fiscal_failed,
              COUNT(*) FILTER (WHERE status = 'paid' AND (checkbox_receipt_id IS NULL OR checkbox_receipt_id = '')) AS paid_without_receipt,
              COUNT(*) FILTER (WHERE fiscal_status IN ('pending', 'processing')) AS fiscal_queue
            FROM purchase
            """
        )
        queue_row = cur.fetchone()

        return {
            "providers": {
                "liqpay": {
                    "total_events": int(liqpay_row[0] or 0),
                    "success_events": int(liqpay_row[1] or 0),
                    "failed_events": int(liqpay_row[2] or 0),
                    "last_event_at": liqpay_row[3].isoformat() if liqpay_row[3] else None,
                },
                "checkbox": {
                    "total_events": int(checkbox_row[0] or 0),
                    "success_events": int(checkbox_row[1] or 0),
                    "failed_events": int(checkbox_row[2] or 0),
                    "last_event_at": checkbox_row[3].isoformat() if checkbox_row[3] else None,
                },
            },
            "queues": {
                "fiscal_failed": int(queue_row[0] or 0),
                "paid_without_receipt": int(queue_row[1] or 0),
                "fiscal_processing_or_pending": int(queue_row[2] or 0),
            },
        }
    finally:
        cur.close()
        conn.close()


@router.get("/events")
def list_events(
    provider: Optional[str] = Query(None, description="Filter by integration provider (liqpay/checkbox/email/...)"),
    status: Optional[str] = Query(None, description="Filter by event status"),
    purchase_id: Optional[int] = Query(None, description="Filter by purchase id"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=500, description="Max events to return"),
) -> dict[str, Any]:
    """Latest integration events for ops troubleshooting."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        conditions = []
        params: list[Any] = []

        if provider:
            conditions.append("provider = %s")
            params.append(provider)
        if status:
            conditions.append("status = %s")
            params.append(status)
        if purchase_id is not None:
            conditions.append("purchase_id = %s")
            params.append(purchase_id)
        if event_type:
            conditions.append("event_type = %s")
            params.append(event_type)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cur.execute(
            f"""
            SELECT id, provider, event_type, purchase_id, ticket_id, external_id,
                   status, payload_json, error_message, created_at
            FROM integration_events
            {where_clause}
            ORDER BY id DESC
            LIMIT %s
            """,
            tuple([*params, limit]),
        )
        rows = cur.fetchall()

        events = [
            {
                "id": r[0],
                "provider": r[1],
                "event_type": r[2],
                "purchase_id": r[3],
                "ticket_id": r[4],
                "external_id": r[5],
                "status": r[6],
                "payload_json": r[7],
                "error_message": r[8],
                "created_at": r[9].isoformat() if r[9] else None,
            }
            for r in rows
        ]

        return {
            "items": events,
            "count": len(events),
            "filters": {
                "provider": provider,
                "status": status,
                "purchase_id": purchase_id,
                "event_type": event_type,
                "limit": limit,
            },
        }
    finally:
        cur.close()
        conn.close()


@router.get("/fiscal-errors")
def fiscal_errors(
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """Purchases failed on fiscalization with latest error context."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, update_at, customer_name, customer_email, amount_due,
                   fiscal_status, fiscal_last_error, checkbox_receipt_id, fiscal_attempts
            FROM purchase
            WHERE fiscal_status = 'failed'
            ORDER BY update_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        items = [
            {
                "purchase_id": r[0],
                "updated_at": r[1].isoformat() if r[1] else None,
                "customer_name": r[2],
                "customer_email": r[3],
                "amount_due": float(r[4]) if r[4] is not None else None,
                "fiscal_status": r[5],
                "fiscal_last_error": r[6],
                "checkbox_receipt_id": r[7],
                "fiscal_attempts": r[8],
            }
            for r in rows
        ]
        return {"items": items, "count": len(items), "limit": limit}
    finally:
        cur.close()
        conn.close()


@router.get("/paid-without-receipt")
def paid_without_receipt(
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """Paid purchases which still do not have an issued CheckBox receipt."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, update_at, customer_name, customer_email, amount_due,
                   status, fiscal_status, checkbox_receipt_id, checkbox_fiscal_code
            FROM purchase
            WHERE status = 'paid'
              AND (checkbox_receipt_id IS NULL OR checkbox_receipt_id = '')
            ORDER BY update_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        items = [
            {
                "purchase_id": r[0],
                "updated_at": r[1].isoformat() if r[1] else None,
                "customer_name": r[2],
                "customer_email": r[3],
                "amount_due": float(r[4]) if r[4] is not None else None,
                "status": r[5],
                "fiscal_status": r[6],
                "checkbox_receipt_id": r[7],
                "checkbox_fiscal_code": r[8],
            }
            for r in rows
        ]
        return {"items": items, "count": len(items), "limit": limit}
    finally:
        cur.close()
        conn.close()
