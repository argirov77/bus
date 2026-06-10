"""Shared helpers for the refund-request workflow.

Both the public router (where customers create requests) and the admin router
(where staff process them) need consistent rules around:
  * locating the active pending request for a purchase
  * computing the remaining refundable balance
  * scheduling Telegram notifications
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Sequence

from fastapi import BackgroundTasks

from . import telegram

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema bootstrap (mirrors what 025_refund_requests.sql declares — included
# here so the table is present when the migration has not been applied yet
# and so tests using fresh dbs don't need to apply migrations manually).
# ---------------------------------------------------------------------------

def ensure_schema(cur) -> None:
    """Create the refund_request table on demand. Safe to call repeatedly."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS refund_request (
            id                     SERIAL PRIMARY KEY,
            purchase_id            INTEGER NOT NULL REFERENCES purchase(id),
            ticket_ids             INTEGER[] NOT NULL DEFAULT '{}',
            amount_requested       NUMERIC(12,2),
            amount_refunded        NUMERIC(12,2),
            currency               TEXT DEFAULT 'UAH',
            status                 TEXT NOT NULL DEFAULT 'pending',
            requested_at           TIMESTAMP NOT NULL DEFAULT NOW(),
            requested_by           TEXT NOT NULL,
            reason                 TEXT,
            admin_actor            TEXT,
            processed_at           TIMESTAMP,
            liqpay_refund_id       TEXT,
            liqpay_response        JSONB,
            fiscal_receipt_id      TEXT,
            fiscal_receipt_number  TEXT,
            fiscal_status          TEXT,
            failure_reason         TEXT
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_refund_request_status ON refund_request(status)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_refund_request_purchase ON refund_request(purchase_id)"
    )
    cur.execute(
        "ALTER TABLE purchase ADD COLUMN IF NOT EXISTS refund_requested_at TIMESTAMP"
    )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

_REQUEST_COLUMNS = (
    "id, purchase_id, ticket_ids, amount_requested, amount_refunded, currency, "
    "status, requested_at, requested_by, reason, admin_actor, processed_at, "
    "liqpay_refund_id, liqpay_response, fiscal_receipt_id, fiscal_receipt_number, "
    "fiscal_status, failure_reason"
)


def _row_to_request(row: Sequence[Any]) -> dict[str, Any]:
    keys = [
        "id",
        "purchase_id",
        "ticket_ids",
        "amount_requested",
        "amount_refunded",
        "currency",
        "status",
        "requested_at",
        "requested_by",
        "reason",
        "admin_actor",
        "processed_at",
        "liqpay_refund_id",
        "liqpay_response",
        "fiscal_receipt_id",
        "fiscal_receipt_number",
        "fiscal_status",
        "failure_reason",
    ]
    return dict(zip(keys, row))


def find_active_request(cur, purchase_id: int) -> dict[str, Any] | None:
    """Return the most recent pending/processing request for a purchase, if any."""
    cur.execute(
        f"""
        SELECT {_REQUEST_COLUMNS}
          FROM refund_request
         WHERE purchase_id = %s AND status IN ('pending', 'processing')
         ORDER BY requested_at DESC, id DESC
         LIMIT 1
        """,
        (purchase_id,),
    )
    row = cur.fetchone()
    return _row_to_request(row) if row else None


def get_request(cur, request_id: int, *, for_update: bool = False) -> dict[str, Any] | None:
    query = f"SELECT {_REQUEST_COLUMNS} FROM refund_request WHERE id = %s"
    if for_update:
        query += " FOR UPDATE"
    cur.execute(query, (request_id,))
    row = cur.fetchone()
    return _row_to_request(row) if row else None


def list_requests(cur, *, status: str | None = None) -> list[dict[str, Any]]:
    if status:
        cur.execute(
            f"""
            SELECT {_REQUEST_COLUMNS}
              FROM refund_request
             WHERE status = %s
             ORDER BY requested_at DESC, id DESC
            """,
            (status,),
        )
    else:
        cur.execute(
            f"""
            SELECT {_REQUEST_COLUMNS}
              FROM refund_request
             ORDER BY requested_at DESC, id DESC
            """,
        )
    return [_row_to_request(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------

def compute_paid_amount(cur, purchase_id: int) -> float:
    """Total amount the customer has paid for the purchase.

    Derived from the sales log because the purchase row has no dedicated
    ``paid_amount`` column. We sum positive ``paid`` entries.
    """
    cur.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
          FROM sales
         WHERE purchase_id = %s AND category = 'paid'
        """,
        (purchase_id,),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def compute_completed_refunds(cur, purchase_id: int) -> float:
    """Total amount already refunded for the purchase (completed requests)."""
    cur.execute(
        """
        SELECT COALESCE(SUM(amount_refunded), 0)
          FROM refund_request
         WHERE purchase_id = %s AND status = 'completed'
        """,
        (purchase_id,),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def compute_remaining(cur, purchase_id: int) -> float:
    """Amount still refundable: paid − already-refunded."""
    return round(compute_paid_amount(cur, purchase_id) - compute_completed_refunds(cur, purchase_id), 2)


# ---------------------------------------------------------------------------
# Request lifecycle
# ---------------------------------------------------------------------------

def create_request(
    cur,
    *,
    purchase_id: int,
    ticket_ids: Sequence[int],
    amount_requested: float | None,
    currency: str,
    requested_by: str,
    reason: str | None,
    admin_actor: str | None = None,
) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO refund_request (
            purchase_id, ticket_ids, amount_requested, currency,
            requested_by, reason, admin_actor, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
        RETURNING id, requested_at
        """,
        (
            purchase_id,
            list(ticket_ids),
            amount_requested,
            currency,
            requested_by,
            reason,
            admin_actor,
        ),
    )
    row = cur.fetchone()
    request_id = int(row[0]) if row else 0
    requested_at = row[1] if row else None
    cur.execute(
        "UPDATE purchase SET refund_requested_at = NOW(), update_at = NOW() WHERE id = %s",
        (purchase_id,),
    )
    return {
        "id": request_id,
        "purchase_id": purchase_id,
        "ticket_ids": list(ticket_ids),
        "amount_requested": amount_requested,
        "currency": currency,
        "status": "pending",
        "requested_at": requested_at,
        "requested_by": requested_by,
        "reason": reason,
        "admin_actor": admin_actor,
    }


def mark_processing(cur, request_id: int) -> None:
    cur.execute(
        "UPDATE refund_request SET status='processing' WHERE id=%s",
        (request_id,),
    )


def mark_completed(
    cur,
    request_id: int,
    *,
    amount_refunded: float,
    liqpay_refund_id: str | None,
    liqpay_response: Mapping[str, Any] | None,
    fiscal_receipt_id: str | None,
    fiscal_receipt_number: str | None,
    fiscal_status: str | None,
) -> None:
    cur.execute(
        """
        UPDATE refund_request
           SET status = 'completed',
               amount_refunded = %s,
               liqpay_refund_id = %s,
               liqpay_response = %s,
               fiscal_receipt_id = %s,
               fiscal_receipt_number = %s,
               fiscal_status = %s,
               processed_at = NOW(),
               failure_reason = NULL
         WHERE id = %s
        """,
        (
            amount_refunded,
            liqpay_refund_id,
            json.dumps(dict(liqpay_response)) if liqpay_response else None,
            fiscal_receipt_id,
            fiscal_receipt_number,
            fiscal_status,
            request_id,
        ),
    )


def mark_failed(cur, request_id: int, failure_reason: str) -> None:
    cur.execute(
        """
        UPDATE refund_request
           SET status = 'failed',
               failure_reason = %s,
               processed_at = NOW()
         WHERE id = %s
        """,
        (failure_reason[:500], request_id),
    )


def mark_rejected(cur, request_id: int, *, admin_actor: str | None, reason: str | None) -> None:
    cur.execute(
        """
        UPDATE refund_request
           SET status = 'rejected',
               admin_actor = COALESCE(%s, admin_actor),
               failure_reason = %s,
               processed_at = NOW()
         WHERE id = %s
        """,
        (admin_actor, reason, request_id),
    )


def find_by_liqpay_refund_id(cur, liqpay_refund_id: str) -> dict[str, Any] | None:
    cur.execute(
        f"SELECT {_REQUEST_COLUMNS} FROM refund_request WHERE liqpay_refund_id = %s LIMIT 1",
        (liqpay_refund_id,),
    )
    row = cur.fetchone()
    return _row_to_request(row) if row else None


# ---------------------------------------------------------------------------
# Notification scheduling
# ---------------------------------------------------------------------------

def _load_purchase_snapshot(cur, purchase_id: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id, customer_name, customer_email, customer_phone, amount_due, status
          FROM purchase
         WHERE id = %s
        """,
        (purchase_id,),
    )
    row = cur.fetchone()
    if not row:
        return {"id": purchase_id}
    return {
        "id": int(row[0]),
        "customer_name": row[1],
        "customer_email": row[2],
        "customer_phone": row[3],
        "amount_due": float(row[4]) if row[4] is not None else None,
        "status": row[5],
    }


def queue_requested_notification(
    background_tasks: BackgroundTasks | None,
    cur,
    purchase_id: int,
    request: Mapping[str, Any],
    requester: str,
) -> None:
    if not background_tasks or not telegram.is_enabled():
        return
    snapshot = _load_purchase_snapshot(cur, purchase_id)
    request_snapshot = dict(request)
    background_tasks.add_task(
        telegram.notify_refund_requested, snapshot, request_snapshot, requester
    )


def queue_completed_notification(
    background_tasks: BackgroundTasks | None,
    purchase_snapshot: Mapping[str, Any],
    request: Mapping[str, Any],
) -> None:
    if not background_tasks or not telegram.is_enabled():
        return
    background_tasks.add_task(
        telegram.notify_refund_completed, dict(purchase_snapshot), dict(request)
    )


def queue_failed_notification(
    background_tasks: BackgroundTasks | None,
    purchase_snapshot: Mapping[str, Any],
    request: Mapping[str, Any],
    error: str,
) -> None:
    if not background_tasks or not telegram.is_enabled():
        return
    background_tasks.add_task(
        telegram.notify_refund_failed, dict(purchase_snapshot), dict(request), error
    )
