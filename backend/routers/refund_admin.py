"""Admin endpoints for the refund-request workflow.

The public side only creates refund requests. All processing — calling LiqPay,
issuing the CheckBox refund receipt, freeing seats and writing sales log
entries — runs through here under admin auth.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Optional, Sequence

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..auth import require_admin_token
from ..database import get_connection
from ..services import liqpay, refund as refund_service, telegram
from ..services import checkbox as checkbox_service
from ..services import link_sessions
from ..ticket_utils import free_ticket

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/refund-requests",
    tags=["admin_refund_requests"],
    dependencies=[Depends(require_admin_token)],
)

purchase_router = APIRouter(
    prefix="/admin/purchases",
    tags=["admin_refund_requests"],
    dependencies=[Depends(require_admin_token)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RefundRequestRow(BaseModel):
    id: int
    purchase_id: int
    ticket_ids: list[int]
    amount_requested: Optional[float]
    amount_refunded: Optional[float]
    currency: str
    status: str
    requested_at: Optional[str]
    requested_by: str
    reason: Optional[str]
    admin_actor: Optional[str]
    processed_at: Optional[str]
    failure_reason: Optional[str]
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None


class RefundRequestDetail(BaseModel):
    request: RefundRequestRow
    tickets: list[dict[str, Any]]
    remaining: float
    paid_amount: float
    payment_method: Optional[str]
    liqpay_order_id: Optional[str]


class ProcessRequest(BaseModel):
    ticket_ids: list[int] = Field(default_factory=list)
    refund_amount: float = Field(..., gt=0)
    void_fiscal: bool = True
    comment: Optional[str] = Field(default=None, max_length=500)


class RejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class PartialRefundRequest(BaseModel):
    ticket_ids: list[int] = Field(..., min_length=1)
    refund_amount: float = Field(..., gt=0)
    void_fiscal: bool = True
    reason: Optional[str] = Field(default=None, max_length=500)
    comment: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_request(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "purchase_id": row.get("purchase_id"),
        "ticket_ids": list(row.get("ticket_ids") or []),
        "amount_requested": (
            float(row["amount_requested"]) if row.get("amount_requested") is not None else None
        ),
        "amount_refunded": (
            float(row["amount_refunded"]) if row.get("amount_refunded") is not None else None
        ),
        "currency": row.get("currency") or "UAH",
        "status": row.get("status"),
        "requested_at": (
            row["requested_at"].isoformat() if row.get("requested_at") else None
        ),
        "requested_by": row.get("requested_by"),
        "reason": row.get("reason"),
        "admin_actor": row.get("admin_actor"),
        "processed_at": (
            row["processed_at"].isoformat() if row.get("processed_at") else None
        ),
        "failure_reason": row.get("failure_reason"),
    }


def _resolve_admin_actor(request: Request) -> str:
    """Best-effort actor label for audit fields."""
    actor = getattr(request.state, "actor", None) or getattr(request.state, "jti", None)
    return str(actor) if actor else "admin"


def _load_purchase_for_refund(cur, purchase_id: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id, status, customer_name, customer_email, payment_method,
               liqpay_order_id
          FROM purchase
         WHERE id = %s
         FOR UPDATE
        """,
        (purchase_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return {
        "id": int(row[0]),
        "status": row[1],
        "customer_name": row[2],
        "customer_email": row[3],
        "payment_method": row[4],
        "liqpay_order_id": row[5],
    }


def _active_ticket_ids(cur, purchase_id: int) -> list[int]:
    cur.execute(
        "SELECT id FROM ticket WHERE purchase_id = %s ORDER BY id",
        (purchase_id,),
    )
    return [int(r[0]) for r in cur.fetchall()]


def _describe_liqpay_order(order_id: str | None) -> str:
    """Best-effort snapshot of what LiqPay itself knows about the order.

    A refusal like ``status=error code=payment_not_found`` only makes sense
    next to the payment's real state (wrong order id, not captured yet, amount
    smaller than the requested refund), so ask LiqPay for it before giving up.
    Never raises: this runs on the failure path and must not mask the refusal.
    """
    if not order_id:
        return ""
    try:
        body = liqpay.verify_order(order_id)
    except Exception:
        logger.exception("LiqPay status lookup failed for order_id=%s", order_id)
        return ""

    err_code, err_description = liqpay.extract_error(body)
    parts = [f"status={body.get('status') or 'unknown'}"]
    if body.get("amount") is not None:
        parts.append(f"amount={body.get('amount')}")
    if body.get("currency"):
        parts.append(f"currency={body.get('currency')}")
    if body.get("sender_commission") is not None:
        parts.append(f"sender_commission={body.get('sender_commission')}")
    if err_code:
        parts.append(f"code={err_code}")
    if err_description:
        parts.append(f"description={err_description}")
    return f" (order {order_id}: {', '.join(parts)})"


def _log_sale(
    cur,
    purchase_id: int,
    category: str,
    amount: float,
    *,
    actor: str | None,
    method: str | None,
) -> None:
    cur.execute(
        "INSERT INTO sales (purchase_id, category, amount, actor, method) VALUES (%s,%s,%s,%s,%s)",
        (purchase_id, category, amount, actor or "admin", method),
    )


# ---------------------------------------------------------------------------
# List & detail
# ---------------------------------------------------------------------------


@router.get("", response_model=list[RefundRequestRow])
@router.get("/", response_model=list[RefundRequestRow])
def list_refund_requests(status: Optional[str] = Query(None)):
    conn = get_connection()
    cur = conn.cursor()
    try:
        refund_service.ensure_schema(cur)
        rows = refund_service.list_requests(cur, status=status)
        out: list[dict[str, Any]] = []
        for row in rows:
            entry = _serialize_request(row)
            # Attach customer info to make the list usable without a per-row join.
            cur.execute(
                "SELECT customer_name, customer_email FROM purchase WHERE id = %s",
                (row.get("purchase_id"),),
            )
            cust_row = cur.fetchone()
            if cust_row:
                entry["customer_name"] = cust_row[0]
                entry["customer_email"] = cust_row[1]
            out.append(entry)
        return out
    finally:
        cur.close()
        conn.close()


@router.get("/{request_id}", response_model=RefundRequestDetail)
def get_refund_request(request_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        refund_service.ensure_schema(cur)
        row = refund_service.get_request(cur, request_id)
        if not row:
            raise HTTPException(status_code=404, detail="Refund request not found")

        purchase_id = int(row["purchase_id"])
        cur.execute(
            """
            SELECT id, status, customer_name, customer_email, payment_method,
                   liqpay_order_id
              FROM purchase
             WHERE id = %s
            """,
            (purchase_id,),
        )
        purchase_row = cur.fetchone()
        payment_method = purchase_row[4] if purchase_row else None
        liqpay_order_id = purchase_row[5] if purchase_row else None

        cur.execute(
            """
            SELECT t.id, s.seat_num, p.name, t.extra_baggage,
                   COALESCE(dep.stop_ua, dep.stop_name),
                   COALESCE(arr.stop_ua, arr.stop_name),
                   tr.date
              FROM ticket t
              LEFT JOIN seat s ON s.id = t.seat_id
              LEFT JOIN passenger p ON p.id = t.passenger_id
              LEFT JOIN tour tr ON tr.id = t.tour_id
              LEFT JOIN stop dep ON dep.id = t.departure_stop_id
              LEFT JOIN stop arr ON arr.id = t.arrival_stop_id
             WHERE t.purchase_id = %s
             ORDER BY t.id
            """,
            (purchase_id,),
        )
        tickets = [
            {
                "id": int(t[0]),
                "seat_num": t[1],
                "passenger_name": t[2],
                "extra_baggage": int(t[3] or 0),
                "from_stop_name": t[4],
                "to_stop_name": t[5],
                "tour_date": t[6].isoformat() if t[6] else None,
            }
            for t in cur.fetchall()
        ]

        paid_amount = refund_service.compute_paid_amount(cur, purchase_id)
        remaining = round(
            paid_amount - refund_service.compute_completed_refunds(cur, purchase_id), 2
        )

        entry = _serialize_request(row)
        if purchase_row:
            entry["customer_name"] = purchase_row[2]
            entry["customer_email"] = purchase_row[3]

        return {
            "request": entry,
            "tickets": tickets,
            "remaining": remaining,
            "paid_amount": round(paid_amount, 2),
            "payment_method": payment_method,
            "liqpay_order_id": liqpay_order_id,
        }
    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# Core refund processing
# ---------------------------------------------------------------------------


def _execute_refund(
    request_id: int,
    *,
    actor: str,
    ticket_ids: Sequence[int],
    refund_amount: float,
    void_fiscal: bool,
    comment: str | None,
    background_tasks: BackgroundTasks | None,
) -> dict[str, Any]:
    """Execute the full refund flow for an existing pending request.

    Steps (in order):
      1. mark request as processing
      2. call LiqPay refund_payment (online refund)
      3. optionally create CheckBox refund receipt
      4. release seats, void open returns, write sales log
      5. close purchase status if fully refunded
      6. mark request completed; schedule Telegram completion notification
    """
    conn = get_connection()
    cur = conn.cursor()
    purchase_snapshot: dict[str, Any] = {}
    completed_request: dict[str, Any] = {}
    try:
        refund_service.ensure_schema(cur)
        request_row = refund_service.get_request(cur, request_id, for_update=True)
        if not request_row:
            raise HTTPException(status_code=404, detail="Refund request not found")

        if request_row.get("status") not in {"pending", "failed"}:
            raise HTTPException(
                status_code=409,
                detail=f"Refund request cannot be processed (status={request_row.get('status')})",
            )

        purchase = _load_purchase_for_refund(cur, int(request_row["purchase_id"]))
        if purchase["status"] not in {"paid"}:
            raise HTTPException(
                status_code=409,
                detail=f"Purchase is not paid (status={purchase['status']})",
            )

        if not purchase.get("liqpay_order_id"):
            raise HTTPException(
                status_code=409,
                detail="Purchase has no LiqPay order id; offline payments must use the manual refund flow",
            )

        active_tickets = set(_active_ticket_ids(cur, purchase["id"]))
        ticket_ids_list = list(ticket_ids)
        invalid = [t for t in ticket_ids_list if t not in active_tickets]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Tickets {invalid} are not active on this purchase",
            )

        remaining = refund_service.compute_remaining(cur, purchase["id"])
        if refund_amount - remaining > 0.005:
            raise HTTPException(
                status_code=400,
                detail=f"Refund amount {refund_amount} exceeds remaining {remaining}",
            )

        refund_service.mark_processing(cur, request_id)
        # Commit the processing flip immediately so the row is visibly locked
        # even if the external API hangs.
        conn.commit()

        purchase_snapshot = {
            "id": purchase["id"],
            "customer_name": purchase["customer_name"],
            "customer_email": purchase["customer_email"],
        }

        # Idempotency guards: a previous attempt may have completed some
        # steps before failing (e.g. LiqPay refunded but CheckBox errored).
        # A money-moving step with a persisted id must never run twice.
        existing_liqpay_refund_id = request_row.get("liqpay_refund_id")
        existing_fiscal_receipt_id = request_row.get("fiscal_receipt_id")

        # ---- LiqPay refund call (outside any DB transaction) ----
        if existing_liqpay_refund_id:
            logger.info(
                "LiqPay refund %s already done for request=%s, skipping",
                existing_liqpay_refund_id,
                request_id,
            )
            liqpay_result = {
                "status": "success",
                "payment_id": existing_liqpay_refund_id,
                "raw": request_row.get("liqpay_response"),
            }
        else:
            try:
                liqpay_result = liqpay.refund_payment(
                    purchase["liqpay_order_id"],
                    refund_amount,
                    comment or f"Refund for purchase #{purchase['id']}",
                )
            except Exception as exc:
                error = f"LiqPay refund failed: {exc}"
                logger.exception("LiqPay refund failed for request=%s", request_id)
                _record_failure(request_id, error)
                refund_service.queue_failed_notification(
                    background_tasks, purchase_snapshot, request_row, error
                )
                raise HTTPException(status_code=502, detail=error) from exc

            if not liqpay.is_refund_success(liqpay_result.get("status")):
                error = (
                    "LiqPay refund rejected: "
                    f"{liqpay.describe_refund_result(liqpay_result)}"
                    f"{_describe_liqpay_order(purchase.get('liqpay_order_id'))}"
                )
                logger.error(
                    "LiqPay refund rejected for request=%s purchase=%s order_id=%s amount=%s: %s",
                    request_id,
                    purchase["id"],
                    purchase.get("liqpay_order_id"),
                    refund_amount,
                    error,
                )
                _record_failure(request_id, error, liqpay_response=liqpay_result.get("raw"))
                refund_service.queue_failed_notification(
                    background_tasks, purchase_snapshot, request_row, error
                )
                raise HTTPException(status_code=502, detail=error)

            # Persist the refund id immediately, before touching CheckBox, so
            # a fiscal failure below cannot lead to a second LiqPay refund on
            # retry.
            cur.execute(
                """
                UPDATE refund_request
                   SET liqpay_refund_id = %s,
                       liqpay_response = %s
                 WHERE id = %s
                """,
                (
                    liqpay_result.get("payment_id"),
                    json.dumps(dict(liqpay_result["raw"]))
                    if liqpay_result.get("raw")
                    else None,
                    request_id,
                ),
            )
            conn.commit()

        # ---- Fiscal refund receipt (optional) ----
        fiscal_receipt_id: str | None = None
        fiscal_receipt_number: str | None = None
        fiscal_status: str | None = None
        if existing_fiscal_receipt_id:
            logger.info(
                "CheckBox refund receipt %s already created for request=%s, skipping",
                existing_fiscal_receipt_id,
                request_id,
            )
            fiscal_receipt_id = existing_fiscal_receipt_id
            fiscal_receipt_number = request_row.get("fiscal_receipt_number")
            fiscal_status = request_row.get("fiscal_status")
        elif void_fiscal and checkbox_service.is_enabled():
            try:
                fiscal = checkbox_service.create_refund_receipt(
                    purchase["id"], ticket_ids_list or None, refund_amount
                )
                fiscal_receipt_id = fiscal.get("receipt_id")
                fiscal_receipt_number = fiscal.get("fiscal_number")
                fiscal_status = fiscal.get("status") or "done"
            except Exception as exc:
                error = f"CheckBox refund failed: {exc}"
                logger.exception("CheckBox refund failed for request=%s", request_id)
                _record_failure(
                    request_id,
                    error,
                    liqpay_refund_id=liqpay_result.get("payment_id"),
                    liqpay_response=liqpay_result.get("raw"),
                )
                refund_service.queue_failed_notification(
                    background_tasks, purchase_snapshot, request_row, error
                )
                raise HTTPException(status_code=502, detail=error) from exc

            # Persist the fiscal id immediately so a downstream failure in the
            # seat/inventory transaction cannot roll it back. Without this the
            # CheckBox receipt exists but our DB forgets it and a retry would
            # issue a second receipt.
            if fiscal_receipt_id or fiscal_status:
                cur.execute(
                    """
                    UPDATE refund_request
                       SET fiscal_receipt_id = %s,
                           fiscal_receipt_number = %s,
                           fiscal_status = %s
                     WHERE id = %s
                    """,
                    (
                        fiscal_receipt_id,
                        fiscal_receipt_number,
                        fiscal_status,
                        request_id,
                    ),
                )
                conn.commit()

        # ---- Apply seat & purchase changes inside a fresh DB transaction ----
        cur2 = conn.cursor()
        try:
            for ticket_id in ticket_ids_list:
                free_ticket(cur2, ticket_id)
                link_sessions.revoke_ticket_sessions(ticket_id, conn=conn)

            # Did we wipe out all remaining tickets?
            cur2.execute(
                "SELECT COUNT(*) FROM ticket WHERE purchase_id = %s",
                (purchase["id"],),
            )
            count_row = cur2.fetchone()
            remaining_tickets = int(count_row[0]) if count_row else 0

            new_total_refunded = round(
                refund_service.compute_completed_refunds(cur2, purchase["id"])
                + refund_amount,
                2,
            )
            paid_total = round(refund_service.compute_paid_amount(cur2, purchase["id"]), 2)
            is_full_refund = (
                remaining_tickets == 0
                and abs(new_total_refunded - paid_total) <= 0.005
            )

            sale_category = "refunded" if is_full_refund else "part_refund"
            _log_sale(
                cur2,
                purchase["id"],
                sale_category,
                -refund_amount,
                actor=actor,
                method="liqpay",
            )

            if is_full_refund:
                cur2.execute(
                    "UPDATE purchase SET status='refunded', update_at=NOW() WHERE id=%s",
                    (purchase["id"],),
                )
                cur2.execute(
                    "UPDATE open_ticket SET status='cancelled' "
                    "WHERE purchase_id=%s AND status='open'",
                    (purchase["id"],),
                )

            refund_service.mark_completed(
                cur2,
                request_id,
                amount_refunded=refund_amount,
                liqpay_refund_id=liqpay_result.get("payment_id"),
                liqpay_response=liqpay_result.get("raw"),
                fiscal_receipt_id=fiscal_receipt_id,
                fiscal_receipt_number=fiscal_receipt_number,
                fiscal_status=fiscal_status,
            )
            conn.commit()
        finally:
            cur2.close()

        completed_request = refund_service.get_request(cur, request_id) or {}
        refund_service.queue_completed_notification(
            background_tasks, purchase_snapshot, completed_request
        )

        return _serialize_request(completed_request)
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("Unhandled error processing refund request=%s", request_id)
        # Don't leave the row stuck in 'processing' — flip it to 'failed' so
        # an admin can retry once they've fixed the underlying cause.
        try:
            _record_failure(request_id, f"Unhandled error: {exc}")
        except Exception:
            logger.exception("Failed to record failure for request=%s", request_id)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        cur.close()
        conn.close()


def _record_failure(
    request_id: int,
    error: str,
    *,
    liqpay_refund_id: str | None = None,
    liqpay_response: Mapping[str, Any] | None = None,
) -> None:
    """Persist a failure on a dedicated connection so it survives rollbacks."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        if liqpay_refund_id or liqpay_response is not None:
            import json

            cur.execute(
                """
                UPDATE refund_request
                   SET liqpay_refund_id = COALESCE(%s, liqpay_refund_id),
                       liqpay_response  = COALESCE(%s::jsonb, liqpay_response)
                 WHERE id = %s
                """,
                (
                    liqpay_refund_id,
                    json.dumps(dict(liqpay_response)) if liqpay_response else None,
                    request_id,
                ),
            )
        refund_service.mark_failed(cur, request_id, error)
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to persist refund failure for request=%s", request_id)
    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{request_id}/process")
def process_refund_request(
    request_id: int,
    data: ProcessRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    actor = _resolve_admin_actor(request)
    return _execute_refund(
        request_id,
        actor=actor,
        ticket_ids=data.ticket_ids,
        refund_amount=round(float(data.refund_amount), 2),
        void_fiscal=data.void_fiscal,
        comment=data.comment,
        background_tasks=background_tasks,
    )


@router.post("/{request_id}/reject")
def reject_refund_request(
    request_id: int,
    data: RejectRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    actor = _resolve_admin_actor(request)
    conn = get_connection()
    cur = conn.cursor()
    try:
        refund_service.ensure_schema(cur)
        row = refund_service.get_request(cur, request_id, for_update=True)
        if not row:
            raise HTTPException(status_code=404, detail="Refund request not found")
        if row.get("status") != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot reject a {row.get('status')} request",
            )
        refund_service.mark_rejected(
            cur, request_id, admin_actor=actor, reason=data.reason
        )
        conn.commit()
        rejected = refund_service.get_request(cur, request_id) or {}
        return _serialize_request(rejected)
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@purchase_router.post("/{purchase_id}/partial-refund")
def admin_initiated_partial_refund(
    purchase_id: int,
    data: PartialRefundRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Admin shortcut: create a refund request and immediately process it.

    Used when the customer didn't open a request themselves — e.g. when a call
    centre operator initiates the refund manually.
    """
    actor = _resolve_admin_actor(request)
    conn = get_connection()
    cur = conn.cursor()
    request_id: int | None = None
    try:
        refund_service.ensure_schema(cur)
        cur.execute(
            "SELECT status FROM purchase WHERE id = %s FOR UPDATE",
            (purchase_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Purchase not found")
        if str(row[0] or "") != "paid":
            raise HTTPException(
                status_code=409,
                detail=f"Only paid purchases can be refunded (status={row[0]})",
            )

        existing = refund_service.find_active_request(cur, purchase_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Active refund request already exists (id={existing['id']})",
            )

        created = refund_service.create_request(
            cur,
            purchase_id=purchase_id,
            ticket_ids=data.ticket_ids,
            amount_requested=round(float(data.refund_amount), 2),
            currency="UAH",
            requested_by="admin",
            reason=data.reason,
            admin_actor=actor,
        )
        request_id = int(created["id"])
        _log_sale(cur, purchase_id, "refund_requested", 0, actor=actor, method=None)

        refund_service.queue_requested_notification(
            background_tasks, cur, purchase_id, created, "admin"
        )
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    if request_id is None:  # pragma: no cover - safeguarded above
        raise HTTPException(status_code=500, detail="Failed to create refund request")

    return _execute_refund(
        request_id,
        actor=actor,
        ticket_ids=data.ticket_ids,
        refund_amount=round(float(data.refund_amount), 2),
        void_fiscal=data.void_fiscal,
        comment=data.comment,
        background_tasks=background_tasks,
    )


__all__ = ["router", "purchase_router"]
