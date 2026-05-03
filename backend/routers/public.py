from __future__ import annotations

import io
import json
import logging
import secrets
import zipfile
from urllib.parse import parse_qs
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Literal, Sequence

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
import psycopg2

from ..database import get_connection
from ..services import link_sessions
from ..services.link_sessions import get_or_create_view_session
from ..services.access_guard import guard_public_request
from ..services import liqpay
from ..services.ticket_dto import get_ticket_dto
from ..services.ticket_pdf import render_ticket_pdf
from ..ticket_utils import free_ticket, recalc_available
from ._ticket_link_helpers import (
    DEFAULT_TICKET_SCOPES,
    build_deep_link,
    combine_departure_datetime,
)
from ..utils.client_app import get_client_app_base

session_router = APIRouter(tags=["public"])
router = APIRouter(prefix="/public", tags=["public"])

_COOKIE_PREFIX = "minicab_"
_PURCHASE_COOKIE_PREFIX = "minicab_purchase_"
_CSRF_COOKIE_NAME = "mc_csrf"
_DEFAULT_LANG = "bg"

logger = logging.getLogger(__name__)


class RescheduleTicketSpec(BaseModel):
    ticket_id: int = Field(..., gt=0)
    new_tour_id: int = Field(..., gt=0)
    seat_num: int = Field(..., gt=0)


class RescheduleRequest(BaseModel):
    tickets: list[RescheduleTicketSpec] = Field(..., min_length=1)


class TicketRescheduleRequest(BaseModel):
    tour_id: int = Field(..., gt=0)
    seat_num: int = Field(..., gt=0)


class BaggageTicketSpec(BaseModel):
    ticket_id: int = Field(..., gt=0)
    extra_baggage: int = Field(..., ge=0)


class BaggageRequest(BaseModel):
    tickets: list[BaggageTicketSpec] = Field(..., min_length=1)


class CancelRequest(BaseModel):
    ticket_ids: list[int] = Field(..., min_length=1)


class PaymentResolveTicket(BaseModel):
    ticket_id: int
    seat_number: int | None = None
    route_label: str | None = None
    trip_date: str | None = None
    departure_name: str | None = None
    arrival_name: str | None = None


class PaymentResolvePurchase(BaseModel):
    id: int
    status: str
    amount_due: float
    customer_email: str | None = None
    customer_name: str | None = None
    tickets: list[PaymentResolveTicket] = []


class PaymentResolveOut(BaseModel):
    status: Literal["paid", "pending", "failed"]
    purchaseId: int
    amount_due: float
    tickets: list[PaymentResolveTicket] = []
    fiscal_status: Literal["pending", "processing", "done", "failed"] | None = None
    fiscal_receipt_url: str | None = None
    checkbox_fiscal_code: str | None = None
    purchase: PaymentResolvePurchase | None = None


def _generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _require_csrf(request: Request) -> str:
    cookie_value = request.cookies.get(_CSRF_COOKIE_NAME)
    header_value = request.headers.get("X-CSRF")
    if not cookie_value or not header_value:
        raise HTTPException(status_code=403, detail="Missing CSRF token")
    if not secrets.compare_digest(cookie_value, header_value):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return cookie_value


def _log_sale(cur, purchase_id: int, category: str, amount: float, *, actor: str | None = None) -> None:
    cur.execute(
        "INSERT INTO sales (purchase_id, category, amount, actor, method) VALUES (%s,%s,%s,%s,%s)",
        (purchase_id, category, amount, actor or "public", None),
    )


def _round_currency(value: float | None) -> float:
    return round(float(value or 0.0), 2)


def _purchase_has_column(cur, column_name: str) -> bool:
    cur.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'purchase'
           AND column_name = %s
         LIMIT 1
        """,
        (column_name,),
    )
    return cur.fetchone() is not None


def _missing_purchase_columns(cur, column_names: Sequence[str]) -> list[str]:
    missing: list[str] = []
    for column_name in column_names:
        if not _purchase_has_column(cur, column_name):
            missing.append(column_name)
    return missing


def _redirect_base_url(purchase_id: int) -> str:
    try:
        base_url = get_client_app_base()
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc
    return f"{base_url}/purchase/{purchase_id}"


def _cookie_name(ticket_id: int) -> str:
    return f"{_COOKIE_PREFIX}{ticket_id}"


def _purchase_cookie_name(purchase_id: int) -> str:
    return f"{_PURCHASE_COOKIE_PREFIX}{purchase_id}"


def _iter_purchase_cookies(cookies: Mapping[str, str]) -> Iterable[tuple[int, str, str]]:
    for key, value in cookies.items():
        if not key.startswith(_PURCHASE_COOKIE_PREFIX) or not value:
            continue
        suffix = key[len(_PURCHASE_COOKIE_PREFIX) :]
        if suffix.isdigit():
            yield int(suffix), key, value


def _iter_ticket_cookies(cookies: Mapping[str, str]) -> Iterable[tuple[int, str, str]]:
    for key, value in cookies.items():
        if not key.startswith(_COOKIE_PREFIX) or not value:
            continue
        suffix = key[len(_COOKIE_PREFIX) :]
        if suffix.isdigit():
            yield int(suffix), key, value


def _pick_cookie(
    matches: Sequence[tuple[int, str, str]] | Iterable[tuple[int, str, str]],
    *,
    missing_detail: str,
    ambiguous_detail: str,
) -> tuple[int, str, str]:
    collected = matches if isinstance(matches, list) else list(matches)
    if not collected:
        raise HTTPException(status_code=401, detail=missing_detail)
    if len(collected) > 1:
        raise HTTPException(status_code=400, detail=ambiguous_detail)
    return collected[0]




def _describe_purchase_session_mismatch(cookies: Mapping[str, str], purchase_id: int) -> str:
    available = sorted({pid for pid, _name, _value in _iter_purchase_cookies(cookies)})
    if not available:
        return "Purchase session is not initialized; open /q/{opaque} first to set cookies and CSRF."
    available_text = ", ".join(str(pid) for pid in available)
    return (
        "Purchase session is not initialized for this purchase; "
        f"requested purchase_id={purchase_id}, available purchase sessions: [{available_text}]. "
        "Open /q/{opaque} for the requested purchase to set the correct cookies and CSRF."
    )


def _extract_session_cookie(
    request: Request, ticket_id: int | None = None, purchase_id: int | None = None
) -> tuple[int, str, str]:
    cookies = request.cookies or {}
    if purchase_id is not None:
        name = _purchase_cookie_name(purchase_id)
        value = cookies.get(name)
        if not value:
            detail = _describe_purchase_session_mismatch(cookies, purchase_id)
            raise HTTPException(status_code=401, detail=detail)
        return purchase_id, name, value

    if ticket_id is not None:
        name = _cookie_name(ticket_id)
        value = cookies.get(name)
        if value:
            return ticket_id, name, value
        return _pick_cookie(
            _iter_purchase_cookies(cookies),
            missing_detail="Purchase session is not initialized; open /q/{opaque} first to set cookies and CSRF.",
            ambiguous_detail="Ambiguous purchase session",
        )

    purchase_match = list(_iter_purchase_cookies(cookies))
    if purchase_match:
        return _pick_cookie(
            purchase_match,
            missing_detail="Purchase session is not initialized; open /q/{opaque} first to set cookies and CSRF.",
            ambiguous_detail="Ambiguous purchase session",
        )

    return _pick_cookie(
        _iter_ticket_cookies(cookies),
        missing_detail="Missing ticket session",
        ambiguous_detail="Ambiguous ticket session",
    )


def _resolve_purchase_id(session: link_sessions.LinkSession) -> int:
    if session.purchase_id:
        return int(session.purchase_id)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT purchase_id FROM ticket WHERE id = %s", (session.ticket_id,))
            row = cur.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="Purchase not found for ticket")
        return int(row[0])
    finally:
        conn.close()


def _require_view_session(
    request: Request,
    ticket_id: int | None = None,
    purchase_id: int | None = None,
) -> tuple[link_sessions.LinkSession, int, int, str]:
    target_id, cookie_name, session_id = _extract_session_cookie(
        request, ticket_id=ticket_id, purchase_id=purchase_id
    )

    session = link_sessions.get_session(
        session_id,
        scope="view",
        require_redeemed=True,
    )
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    now = datetime.now(timezone.utc)
    if session.exp <= now:
        raise HTTPException(status_code=401, detail="Session expired")

    resolved_purchase_id = _resolve_purchase_id(session)
    if purchase_id is not None and resolved_purchase_id != purchase_id:
        raise HTTPException(status_code=403, detail="Session does not match purchase")

    if ticket_id is not None and session.ticket_id != ticket_id:
        raise HTTPException(status_code=403, detail="Session does not match ticket")

    if purchase_id is None and target_id != resolved_purchase_id:
        # Cookie may have been issued for a specific ticket; keep compatibility by
        # ensuring it matches the associated purchase.
        if target_id != session.ticket_id:
            raise HTTPException(status_code=403, detail="Session mismatch")

    return session, session.ticket_id, resolved_purchase_id, cookie_name


def _require_purchase_context(
    request: Request,
    purchase_id: int,
    scope: str,
) -> tuple[link_sessions.LinkSession, int, int, str]:
    session, ticket_id, resolved_purchase_id, cookie_name = _require_view_session(
        request, purchase_id=purchase_id
    )
    guard_public_request(
        request,
        scope,
        ticket_id=ticket_id,
        purchase_id=resolved_purchase_id,
    )
    _require_csrf(request)
    link_sessions.touch_session_usage(session.jti, scope="view")
    return session, ticket_id, resolved_purchase_id, cookie_name


def _load_purchase_state(
    cur,
    purchase_id: int,
    *,
    for_update: bool = False,
) -> tuple[float, str]:
    query = "SELECT amount_due, status FROM purchase WHERE id = %s"
    if for_update:
        query += " FOR UPDATE"
    cur.execute(query, (purchase_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Purchase not found")
    amount_due = _round_currency(row[0])
    status = str(row[1]) if row[1] is not None else "reserved"
    return amount_due, status


def _ensure_purchase_active(status: str) -> None:
    if status in {"cancelled", "refunded"}:
        raise HTTPException(status_code=409, detail="Purchase is not active")


def _status_for_balance(current_status: str, new_amount_due: float, *, has_tickets: bool = True) -> str:
    if not has_tickets:
        return "cancelled"
    if new_amount_due <= 0:
        return "paid" if current_status != "refunded" else current_status
    return "reserved"


def _load_ticket_dto(ticket_id: int, lang: str = _DEFAULT_LANG) -> Mapping[str, Any]:
    conn = get_connection()
    try:
        try:
            return get_ticket_dto(ticket_id, lang, conn)
        except ValueError as exc:  # pragma: no cover - defensive logging
            raise HTTPException(status_code=404, detail="Ticket not found") from exc
    finally:
        conn.close()


def _load_purchase_view(purchase_id: int, lang: str = _DEFAULT_LANG) -> Mapping[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, amount_due, customer_name, customer_email,
                       customer_phone, update_at
                  FROM purchase
                 WHERE id = %s
                """,
                (purchase_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Purchase not found")

        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id FROM ticket WHERE purchase_id = %s ORDER BY id",
                (purchase_id,),
            )
            ticket_ids = [int(r[0]) for r in cur.fetchall()]
        finally:
            cur.close()

        raw_dtos = [get_ticket_dto(tid, lang, conn) for tid in ticket_ids]
        timestamp = row[6]

        purchase_status = row[1]
        amount_due = float(row[2]) if row[2] is not None else None
        customer = {
            "name": row[3],
            "email": row[4],
            "phone": row[5],
        }

        # Transform ticket DTOs into PurchaseTicket shape expected by client
        tickets = []
        passengers_map: dict[int, dict] = {}
        for dto in raw_dtos:
            t = dto.get("ticket") or {}
            passenger = dto.get("passenger") or {}
            tour_info = dto.get("tour") or {}
            route_info = dto.get("route") or {}
            segment_info = dto.get("segment") or {}
            pricing_info = dto.get("pricing") or {}

            # Build PurchaseTicket-compatible object
            ticket_obj = {
                "id": t.get("id"),
                "passenger_id": passenger.get("id"),
                "status": purchase_status,
                "seat_id": t.get("seat_id"),
                "seat_num": t.get("seat_number"),
                "extra_baggage": t.get("extra_baggage"),
                "tour": {
                    "id": tour_info.get("id"),
                    "date": tour_info.get("date"),
                    "route_id": route_info.get("id"),
                    "route_name": route_info.get("name"),
                },
                "segments": [],
                "route": {
                    "id": route_info.get("id"),
                    "name": route_info.get("name"),
                    "stops": route_info.get("stops"),
                },
                "pricing": {
                    "price": pricing_info.get("price"),
                    "currency": pricing_info.get("currency_code"),
                },
                "segment_details": segment_info,
            }
            tickets.append(ticket_obj)

            # Collect passengers
            pid = passenger.get("id")
            if pid is not None and pid not in passengers_map:
                passengers_map[pid] = {
                    "id": pid,
                    "name": passenger.get("name"),
                    "email": customer.get("email"),
                    "phone": customer.get("phone"),
                }

        passengers = list(passengers_map.values())

        return {
            "purchase": {
                "id": purchase_id,
                "status": purchase_status,
                "created_at": timestamp.isoformat() if timestamp else None,
                "amount_due": amount_due,
                "currency": "BGN",
            },
            "passengers": passengers,
            "tickets": tickets,
            "trips": [],
            "totals": {
                "paid": amount_due if purchase_status == "paid" else 0,
                "due": 0 if purchase_status == "paid" else (amount_due or 0),
                "baggage_count": 0,
                "pax_count": len(passengers),
            },
            "customer": customer,
        }
    finally:
        conn.close()


def _verify_ticket_purchase_access(ticket_id: int, purchase_id: int, email: str) -> None:
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.customer_email
                  FROM ticket AS t
                  JOIN purchase AS p ON p.id = t.purchase_id
                 WHERE t.id = %s
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")

    resolved_purchase_id, stored_email = int(row[0]), row[1]
    if resolved_purchase_id != purchase_id:
        raise HTTPException(status_code=403, detail="Ticket does not belong to purchase")

    stored_normalized = (stored_email or "").strip().lower()
    if not stored_normalized or stored_normalized != normalized_email:
        raise HTTPException(status_code=403, detail="Email does not match purchase")


def _extract_purchase_id_from_order(order_id: str) -> int | None:
    if not order_id:
        return None
    if order_id.startswith("purchase-"):
        suffix = order_id[len("purchase-") :]
        return int(suffix) if suffix.isdigit() else None
    if order_id.startswith("ticket-"):
        parts = order_id.split("-")
        if len(parts) >= 3 and parts[-1].isdigit():
            return int(parts[-1])
    return None




def _is_undefined_column_error(exc: Exception) -> bool:
    if isinstance(exc, psycopg2.errors.UndefinedColumn):
        return True
    if isinstance(exc, psycopg2.ProgrammingError):
        message = str(exc).lower()
        return "does not exist" in message and "column" in message
    return False


def _normalize_liqpay_result_status(value: str | None) -> Literal["paid", "pending", "failed"]:
    status = (value or "").strip().lower()
    if status in {"success", "sandbox", "wait_accept", "subscribed"}:
        return "paid"
    if status in {"failure", "error", "reversed", "unsubscribed"}:
        return "failed"
    return "pending"


def _sync_purchase_paid_from_liqpay_callback(
    purchase_id: int,
    order_id: str,
    payload: Mapping[str, Any],
    background_tasks: BackgroundTasks | None = None,
) -> tuple[str, str | None]:
    status = str(payload.get("status") or "")
    payment_id = str(payload.get("payment_id") or "") or None
    liqpay_status = status.lower()

    from ._ticket_link_helpers import issue_ticket_links
    from .purchase import _collect_ticket_specs_for_purchase, _log_action, _queue_ticket_emails

    conn = get_connection()
    cur = conn.cursor()
    tickets: list[dict[str, Any]] = []
    customer_email: str | None = None
    try:
        cur.execute(
            "SELECT amount_due, status, customer_email FROM purchase WHERE id=%s FOR UPDATE",
            (purchase_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Purchase not found")

        amount_due, purchase_status, customer_email = float(row[0]), row[1], row[2]
        liqpay_columns = ("liqpay_order_id", "liqpay_status", "liqpay_payment_id", "liqpay_payload")
        missing_liqpay_columns = _missing_purchase_columns(cur, liqpay_columns)
        if not missing_liqpay_columns:
            try:
                cur.execute(
                    """
                    UPDATE purchase
                       SET liqpay_order_id=%s,
                           liqpay_status=%s,
                           liqpay_payment_id=%s,
                           liqpay_payload=%s,
                           update_at=NOW()
                     WHERE id=%s
                    """,
                    (order_id, liqpay_status or None, payment_id, json.dumps(payload), purchase_id),
                )
            except Exception as exc:
                if not _is_undefined_column_error(exc):
                    raise
                conn.rollback()
                cur = conn.cursor()
                cur.execute(
                    "SELECT amount_due, status, customer_email FROM purchase WHERE id=%s FOR UPDATE",
                    (purchase_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Purchase not found")
                amount_due, purchase_status, customer_email = float(row[0]), row[1], row[2]
                missing_liqpay_columns = _missing_purchase_columns(cur, liqpay_columns)
                logger.warning(
                    "Skipping LiqPay tracking persistence for purchase=%s; missing columns: %s",
                    purchase_id,
                    ", ".join(missing_liqpay_columns) or "unknown",
                )
        else:
            logger.warning(
                "Skipping LiqPay tracking persistence for purchase=%s; missing columns: %s",
                purchase_id,
                ", ".join(missing_liqpay_columns),
            )

        normalized = _normalize_liqpay_result_status(liqpay_status)
        logger.info(
            "LiqPay callback processed for purchase=%s order_id=%s payment_id=%s liqpay_status=%s normalized=%s",
            purchase_id,
            order_id,
            payment_id,
            liqpay_status or None,
            normalized,
        )
        if normalized != "paid":
            logger.info(
                "Skipping fiscalization flow for purchase=%s because LiqPay status is not paid (normalized=%s)",
                purchase_id,
                normalized,
            )
            conn.commit()
            return normalized, payment_id

        if purchase_status == "paid":
            logger.info(
                "Purchase already paid via LiqPay for purchase=%s order_id=%s payment_id=%s",
                purchase_id,
                order_id,
                payment_id,
            )
            conn.commit()
            return "paid", payment_id

        if purchase_status != "reserved":
            logger.warning(
                "Skipping fiscalization flow for purchase=%s because purchase status is %s (expected reserved)",
                purchase_id,
                purchase_status,
            )
            raise HTTPException(status_code=409, detail="Purchase cannot be paid")

        ticket_specs = _collect_ticket_specs_for_purchase(cur, purchase_id)
        from ..services.checkbox import is_enabled as checkbox_enabled

        fiscal_columns = (
            "fiscal_status",
            "checkbox_receipt_id",
            "checkbox_fiscal_code",
            "fiscal_last_error",
            "fiscal_attempts",
            "fiscalized_at",
        )
        missing_fiscal_columns = _missing_purchase_columns(cur, fiscal_columns)
        if missing_fiscal_columns:
            logger.warning(
                "Skipping fiscal purchase columns update for purchase=%s; missing columns: %s",
                purchase_id,
                ", ".join(missing_fiscal_columns),
            )
            fiscal_sql = "UPDATE purchase SET status='paid', update_at=NOW() WHERE id=%s"
        elif checkbox_enabled():
            fiscal_sql = (
                "UPDATE purchase "
                "SET status='paid', fiscal_status='pending', update_at=NOW() "
                "WHERE id=%s"
            )
        else:
            fiscal_sql = (
                "UPDATE purchase "
                "SET status='paid', fiscal_status=NULL, checkbox_receipt_id=NULL, "
                "checkbox_fiscal_code=NULL, update_at=NOW() "
                "WHERE id=%s"
            )
        cur.execute(fiscal_sql, (purchase_id,))
        _log_action(cur, purchase_id, "paid", amount_due, by="liqpay", method="online")
        try:
            tickets = issue_ticket_links(ticket_specs, None, conn=conn)
        except Exception:
            logger.exception(
                "Failed to issue ticket links after LiqPay callback for purchase=%s; payment is still marked as paid",
                purchase_id,
            )
            tickets = []
        logger.info(
            "Purchase marked paid from LiqPay callback purchase=%s order_id=%s payment_id=%s amount_due=%s",
            purchase_id,
            order_id,
            payment_id,
            amount_due,
        )
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:  # pragma: no cover - defensive
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        cur.close()
        conn.close()

    if background_tasks:
        _queue_ticket_emails(background_tasks, tickets, None, customer_email)
        # Trigger CheckBox fiscalization as a non-blocking background task.
        # Only runs for online (LiqPay) payments — admin path never calls this function.
        from ..services.checkbox import is_enabled as checkbox_enabled, fiscalize_purchase
        if checkbox_enabled():
            background_tasks.add_task(fiscalize_purchase, purchase_id)
            logger.info("Queued CheckBox fiscalization task for purchase=%s", purchase_id)
        else:
            logger.info(
                "CheckBox fiscalization is disabled (CHECKBOX_ENABLED=false); skipping purchase=%s",
                purchase_id,
            )
    else:
        logger.warning(
            "BackgroundTasks is unavailable for LiqPay callback; fiscalization queue skipped for purchase=%s",
            purchase_id,
        )
    return "paid", payment_id


@router.get("/payments/resolve", response_model=PaymentResolveOut)
def resolve_payment(order_id: str = Query(..., min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")):
    purchase_id = _extract_purchase_id_from_order(order_id)
    if purchase_id is None:
        raise HTTPException(status_code=400, detail="Unrecognized order_id format")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            has_liqpay_tracking = _purchase_has_column(cur, "liqpay_order_id")
            if has_liqpay_tracking:
                try:
                    cur.execute(
                        """
                        SELECT id, status, amount_due, customer_email, customer_name,
                               liqpay_order_id, liqpay_status,
                               fiscal_status, checkbox_receipt_id, checkbox_fiscal_code
                          FROM purchase
                         WHERE id=%s
                        """,
                        (purchase_id,),
                    )
                except Exception as exc:
                    if not _is_undefined_column_error(exc):
                        raise
                    conn.rollback()
                    cur.execute(
                        """
                        SELECT id, status, amount_due, customer_email, customer_name,
                               NULL::TEXT AS liqpay_order_id,
                               NULL::TEXT AS liqpay_status,
                               NULL::TEXT AS fiscal_status,
                               NULL::TEXT AS checkbox_receipt_id,
                               NULL::TEXT AS checkbox_fiscal_code
                          FROM purchase
                         WHERE id=%s
                        """,
                        (purchase_id,),
                    )
            else:
                cur.execute(
                    """
                    SELECT id, status, amount_due, customer_email, customer_name,
                           NULL::TEXT AS liqpay_order_id,
                           NULL::TEXT AS liqpay_status,
                           NULL::TEXT AS fiscal_status,
                           NULL::TEXT AS checkbox_receipt_id,
                           NULL::TEXT AS checkbox_fiscal_code
                      FROM purchase
                     WHERE id=%s
                    """,
                    (purchase_id,),
                )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Purchase not found")
    finally:
        conn.close()

    stored_order_id = row[5]
    if stored_order_id and stored_order_id != order_id:
        raise HTTPException(status_code=404, detail="order_id does not match purchase")

    purchase_status = str(row[1] or "")
    liqpay_status = row[6]

    resolved_status = "pending"
    if purchase_status == "paid":
        resolved_status = "paid"
    elif liqpay_status:
        resolved_status = _normalize_liqpay_result_status(liqpay_status)

    if resolved_status != "paid":
        try:
            verify_payload = liqpay.verify_order(order_id)
        except Exception:
            verify_payload = None

        if isinstance(verify_payload, Mapping):
            verified_order_id = str(verify_payload.get("order_id") or order_id)
            if verified_order_id == order_id:
                try:
                    verified_status, _ = _sync_purchase_paid_from_liqpay_callback(
                        purchase_id,
                        order_id,
                        verify_payload,
                    )
                except HTTPException as exc:
                    if exc.status_code < 500:
                        raise
                    logger.exception(
                        "Failed to sync purchase state from LiqPay verify for purchase=%s order_id=%s",
                        purchase_id,
                        order_id,
                    )
                else:
                    resolved_status = verified_status

    from ..services.checkbox import get_receipt_png_url

    receipt_id = str(row[8]) if row[8] else None
    fiscal_receipt_url = get_receipt_png_url(receipt_id) if receipt_id else None

    purchase = {
        "id": int(row[0]),
        "status": resolved_status,
        "amount_due": _round_currency(float(row[2] or 0.0)),
        "customer_email": row[3],
        "customer_name": row[4],
        "tickets": [],
    }

    tickets_conn = get_connection()
    try:
        with tickets_conn.cursor() as tcur:
            tcur.execute(
                """
                SELECT t.id, s.seat_num, r.name, tr.date,
                       dep.stop_name, arr.stop_name
                  FROM ticket t
                  LEFT JOIN seat s ON s.id = t.seat_id
                  LEFT JOIN tour tr ON tr.id = t.tour_id
                  LEFT JOIN route r ON r.id = tr.route_id
                  LEFT JOIN stop dep ON dep.id = t.departure_stop_id
                  LEFT JOIN stop arr ON arr.id = t.arrival_stop_id
                 WHERE t.purchase_id = %s
                 ORDER BY t.id
                """,
                (purchase_id,),
            )
            purchase["tickets"] = [
                {
                    "ticket_id": int(r[0]),
                    "seat_number": r[1],
                    "route_label": r[2],
                    "trip_date": str(r[3]) if r[3] else None,
                    "departure_name": r[4],
                    "arrival_name": r[5],
                }
                for r in tcur.fetchall()
            ]
    finally:
        tickets_conn.close()

    return {
        "status": resolved_status,
        "purchaseId": int(row[0]),
        "amount_due": _round_currency(float(row[2] or 0.0)),
        "tickets": purchase["tickets"],
        "fiscal_status": row[7],
        "fiscal_receipt_url": fiscal_receipt_url,
        "checkbox_fiscal_code": row[9],
        "purchase": purchase,
    }




async def _extract_liqpay_post_payload(request: Request) -> tuple[str | None, str | None]:
    data: str | None = None
    signature: str | None = None

    try:
        form = await request.form()
    except AssertionError:
        form = None

    if form is not None:
        raw_data = form.get("data")
        raw_signature = form.get("signature")
        data = str(raw_data) if raw_data else None
        signature = str(raw_signature) if raw_signature else None

    if data and signature:
        return data, signature

    body_bytes = await request.body()
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        try:
            payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            payload = {}
        if isinstance(payload, Mapping):
            raw_data = payload.get("data")
            raw_signature = payload.get("signature")
            return (str(raw_data) if raw_data else None, str(raw_signature) if raw_signature else None)
        return None, None

    form_payload = parse_qs(body_bytes.decode("utf-8"), keep_blank_values=False) if body_bytes else {}
    raw_data_list = form_payload.get("data")
    raw_signature_list = form_payload.get("signature")
    raw_data = raw_data_list[0] if raw_data_list else None
    raw_signature = raw_signature_list[0] if raw_signature_list else None
    return raw_data, raw_signature


@router.post("/payment/liqpay/callback")
async def liqpay_callback(request: Request, background_tasks: BackgroundTasks) -> Mapping[str, Any]:
    data, signature = await _extract_liqpay_post_payload(request)

    if not data or not signature:
        raise HTTPException(status_code=400, detail="Missing LiqPay data")

    if not liqpay.verify_signature(data, signature):
        raise HTTPException(status_code=400, detail="Invalid LiqPay signature")

    payload = liqpay.decode_payload(data)
    order_id = str(payload.get("order_id") or "")
    purchase_id = _extract_purchase_id_from_order(order_id)
    if purchase_id is None:
        raise HTTPException(status_code=400, detail="Unrecognized LiqPay order")

    try:
        resolved_status, payment_id = _sync_purchase_paid_from_liqpay_callback(
            purchase_id,
            order_id,
            payload,
            background_tasks,
        )
    except HTTPException as exc:
        if exc.status_code < 500:
            raise
        logger.exception(
            "Failed to process LiqPay callback for purchase=%s order_id=%s",
            purchase_id,
            order_id,
        )
        resolved_status, payment_id = "pending", None
    logger.info(
        "LiqPay callback result purchase=%s order_id=%s status=%s payment_id=%s",
        purchase_id,
        order_id,
        resolved_status,
        payment_id,
    )
    return {
        "ok": True,
        "status": resolved_status,
        "purchase_id": purchase_id,
        "payment_id": payment_id,
    }


def _fetch_route_stops(cur, route_id: int) -> list[int]:
    cur.execute(
        'SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY "order"',
        (route_id,),
    )
    rows = cur.fetchall()
    if not rows:
        raise HTTPException(status_code=400, detail="Route has no stops configured")
    return [int(row[0]) for row in rows]


def _segments_between(
    stops: Iterable[int], departure_stop_id: int, arrival_stop_id: int
) -> tuple[list[str], list[tuple[int, int]]]:
    stops_list = list(stops)
    if departure_stop_id not in stops_list or arrival_stop_id not in stops_list:
        raise HTTPException(status_code=400, detail="Invalid stops for this route")
    idx_from = stops_list.index(departure_stop_id)
    idx_to = stops_list.index(arrival_stop_id)
    if idx_from >= idx_to:
        raise HTTPException(status_code=400, detail="Arrival must come after departure")
    tokens = [str(i + 1) for i in range(idx_from, idx_to)]
    pairs = [(stops_list[i], stops_list[i + 1]) for i in range(idx_from, idx_to)]
    return tokens, pairs


def _normalize_availability(avail: str | None) -> str:
    if not avail or avail == "0":
        return ""
    return avail


def _ensure_segments_available(avail: str | None, segments: Iterable[str]) -> None:
    base = _normalize_availability(avail)
    for segment in segments:
        if segment not in base:
            raise HTTPException(status_code=409, detail="Seat not available for the selected tour")


def _merge_available(avail: str | None, segments: Iterable[str]) -> str:
    base = _normalize_availability(avail)
    merged = sorted(set(base + "".join(segments)), key=int)
    return "".join(merged) if merged else "0"


def _remove_segments(avail: str | None, segments: Iterable[str]) -> str:
    base = _normalize_availability(avail)
    updated = "".join(ch for ch in base if ch not in set(segments))
    return updated or "0"


def _resolve_ticket_price(cur, tour_id: int, departure_stop_id: int, arrival_stop_id: int):
    cur.execute("SELECT pricelist_id FROM tour WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    if not row:
        return None
    pricelist_id = row[0]
    cur.execute(
        """
        SELECT price
          FROM prices
         WHERE pricelist_id = %s
           AND departure_stop_id = %s
           AND arrival_stop_id = %s
        """,
        (pricelist_id, departure_stop_id, arrival_stop_id),
    )
    price_row = cur.fetchone()
    return price_row[0] if price_row else None


def _perform_reschedule(
    cur,
    *,
    ticket_id: int,
    current_seat_id: int,
    target_tour_id: int,
    seat_num: int,
    departure_stop_id: int,
    arrival_stop_id: int,
) -> None:
    cur.execute("SELECT tour_id FROM seat WHERE id = %s", (current_seat_id,))
    seat_tour_row = cur.fetchone()
    if not seat_tour_row:
        raise HTTPException(status_code=404, detail="Seat not found")
    current_tour_id = int(seat_tour_row[0])

    cur.execute("SELECT route_id FROM tour WHERE id = %s", (current_tour_id,))
    current_route_row = cur.fetchone()
    if not current_route_row:
        raise HTTPException(status_code=404, detail="Tour not found")
    current_stops = _fetch_route_stops(cur, int(current_route_row[0]))
    current_segments, _ = _segments_between(current_stops, departure_stop_id, arrival_stop_id)

    cur.execute("SELECT available FROM seat WHERE id = %s FOR UPDATE", (current_seat_id,))
    current_avail_row = cur.fetchone()
    if not current_avail_row:
        raise HTTPException(status_code=404, detail="Seat not found")
    current_avail = current_avail_row[0]

    cur.execute("SELECT route_id FROM tour WHERE id = %s", (target_tour_id,))
    target_route_row = cur.fetchone()
    if not target_route_row:
        raise HTTPException(status_code=404, detail="Target tour not found")
    target_stops = _fetch_route_stops(cur, int(target_route_row[0]))
    target_segments, _ = _segments_between(target_stops, departure_stop_id, arrival_stop_id)

    cur.execute(
        "SELECT id, available FROM seat WHERE tour_id = %s AND seat_num = %s FOR UPDATE",
        (target_tour_id, seat_num),
    )
    target_seat_row = cur.fetchone()
    if not target_seat_row:
        raise HTTPException(status_code=404, detail="Seat not found on target tour")
    target_seat_id, target_avail = target_seat_row
    if target_avail == "0":
        raise HTTPException(status_code=409, detail="Seat is blocked on the selected tour")
    _ensure_segments_available(target_avail, target_segments)

    released_current_avail = _merge_available(current_avail, current_segments)
    updated_target_avail = _remove_segments(target_avail, target_segments)

    cur.execute(
        "UPDATE seat SET available = %s WHERE id = %s",
        (released_current_avail, current_seat_id),
    )
    cur.execute(
        "UPDATE seat SET available = %s WHERE id = %s",
        (updated_target_avail, target_seat_id),
    )
    cur.execute(
        """
        UPDATE ticket
           SET tour_id = %s,
               seat_id = %s
         WHERE id = %s
        """,
        (target_tour_id, target_seat_id, ticket_id),
    )

    recalc_available(cur, current_tour_id)
    if current_tour_id != target_tour_id:
        recalc_available(cur, target_tour_id)


def _plan_reschedule(
    cur,
    purchase_id: int,
    specs: Sequence[RescheduleTicketSpec],
    *,
    lock_tickets: bool = False,
    lock_seats: bool = False,
) -> tuple[list[dict[str, Any]], float]:
    if not specs:
        raise HTTPException(status_code=400, detail="No tickets provided")

    seen: set[int] = set()
    seat_state: dict[int, str] = {}
    tour_route_cache: dict[int, int] = {}
    route_stop_cache: dict[int, list[int]] = {}
    plans: list[dict[str, Any]] = []
    total_difference = 0.0

    for spec in specs:
        if spec.ticket_id in seen:
            raise HTTPException(status_code=400, detail="Duplicate ticket in request")
        seen.add(spec.ticket_id)

        ticket_query = (
            "SELECT seat_id, tour_id, departure_stop_id, arrival_stop_id, purchase_id FROM ticket WHERE id = %s"
        )
        if lock_tickets:
            ticket_query += " FOR UPDATE"
        cur.execute(ticket_query, (spec.ticket_id,))
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        current_seat_id, current_tour_id, dep_id, arr_id, purchase_ref = ticket_row
        if purchase_ref != purchase_id:
            raise HTTPException(status_code=403, detail="Ticket does not belong to this purchase")

        seat_query = "SELECT seat_num, available FROM seat WHERE id = %s"
        if lock_seats:
            seat_query += " FOR UPDATE"
        cur.execute(seat_query, (current_seat_id,))
        seat_row = cur.fetchone()
        if not seat_row:
            raise HTTPException(status_code=404, detail="Seat not found")
        current_seat_num = int(seat_row[0])
        current_avail = seat_row[1]

        current_state = seat_state.get(current_seat_id)
        if current_state is None:
            current_state = _normalize_availability(current_avail)

        current_route_id = tour_route_cache.get(current_tour_id)
        if current_route_id is None:
            cur.execute("SELECT route_id FROM tour WHERE id = %s", (current_tour_id,))
            route_row = cur.fetchone()
            if not route_row:
                raise HTTPException(status_code=404, detail="Tour not found")
            current_route_id = int(route_row[0])
            tour_route_cache[current_tour_id] = current_route_id

        current_stops = route_stop_cache.get(current_route_id)
        if current_stops is None:
            current_stops = _fetch_route_stops(cur, current_route_id)
            route_stop_cache[current_route_id] = current_stops
        current_segments, _ = _segments_between(current_stops, dep_id, arr_id)
        released_state = _merge_available(current_state, current_segments)
        seat_state[current_seat_id] = released_state

        current_price = _resolve_ticket_price(cur, current_tour_id, dep_id, arr_id)
        if current_price is None:
            raise HTTPException(status_code=400, detail="Unable to calculate fare difference")

        target_route_id = tour_route_cache.get(spec.new_tour_id)
        if target_route_id is None:
            cur.execute("SELECT route_id FROM tour WHERE id = %s", (spec.new_tour_id,))
            route_row = cur.fetchone()
            if not route_row:
                raise HTTPException(status_code=404, detail="Target tour not found")
            target_route_id = int(route_row[0])
            tour_route_cache[spec.new_tour_id] = target_route_id

        target_stops = route_stop_cache.get(target_route_id)
        if target_stops is None:
            target_stops = _fetch_route_stops(cur, target_route_id)
            route_stop_cache[target_route_id] = target_stops
        target_segments, _ = _segments_between(target_stops, dep_id, arr_id)

        target_query = "SELECT id, available FROM seat WHERE tour_id = %s AND seat_num = %s"
        if lock_seats:
            target_query += " FOR UPDATE"
        cur.execute(target_query, (spec.new_tour_id, spec.seat_num))
        target_row = cur.fetchone()
        if not target_row:
            raise HTTPException(status_code=404, detail="Seat not found on target tour")
        target_seat_id, target_avail = target_row
        if target_avail == "0" and target_seat_id != current_seat_id:
            raise HTTPException(status_code=409, detail="Seat is blocked on the selected tour")

        target_state = seat_state.get(target_seat_id)
        if target_state is None:
            target_state = _normalize_availability(target_avail)
        _ensure_segments_available(target_state, target_segments)
        seat_state[target_seat_id] = _remove_segments(target_state, target_segments)

        target_price = _resolve_ticket_price(cur, spec.new_tour_id, dep_id, arr_id)
        if target_price is None:
            raise HTTPException(status_code=400, detail="Unable to calculate fare difference")

        difference = float(target_price - current_price)
        total_difference += difference

        plans.append(
            {
                "ticket_id": int(spec.ticket_id),
                "current_tour_id": int(current_tour_id),
                "target_tour_id": int(spec.new_tour_id),
                "seat_num": int(spec.seat_num),
                "current_seat_num": current_seat_num,
                "current_price": float(current_price),
                "target_price": float(target_price),
                "difference": difference,
                "current_seat_id": int(current_seat_id),
                "target_seat_id": int(target_seat_id),
                "departure_stop_id": int(dep_id),
                "arrival_stop_id": int(arr_id),
                "no_change": current_tour_id == spec.new_tour_id
                and current_seat_id == target_seat_id,
            }
        )

    return plans, total_difference


def _plan_baggage(
    cur,
    purchase_id: int,
    specs: Sequence[BaggageTicketSpec],
    purchase_status: str,
    *,
    lock_tickets: bool = False,
) -> tuple[list[dict[str, Any]], float]:
    if not specs:
        raise HTTPException(status_code=400, detail="No tickets provided")

    seen: set[int] = set()
    plans: list[dict[str, Any]] = []
    total_delta = 0.0

    for spec in specs:
        if spec.ticket_id in seen:
            raise HTTPException(status_code=400, detail="Duplicate ticket in request")
        seen.add(spec.ticket_id)

        ticket_query = (
            "SELECT tour_id, departure_stop_id, arrival_stop_id, extra_baggage, purchase_id FROM ticket WHERE id = %s"
        )
        if lock_tickets:
            ticket_query += " FOR UPDATE"
        cur.execute(ticket_query, (spec.ticket_id,))
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        tour_id, dep_id, arr_id, current_extra, purchase_ref = ticket_row
        if purchase_ref != purchase_id:
            raise HTTPException(status_code=403, detail="Ticket does not belong to this purchase")

        current_extra_count = int(current_extra or 0)
        new_extra_count = int(spec.extra_baggage)
        if new_extra_count < current_extra_count and purchase_status == "paid":
            raise HTTPException(status_code=409, detail="Cannot remove paid baggage")

        base_price = _resolve_ticket_price(cur, tour_id, dep_id, arr_id)
        if base_price is None:
            raise HTTPException(status_code=400, detail="Unable to calculate baggage price")

        delta_count = new_extra_count - current_extra_count
        delta = float(base_price) * 0.1 * delta_count
        delta = round(delta, 2)
        total_delta += delta

        plans.append(
            {
                "ticket_id": int(spec.ticket_id),
                "tour_id": int(tour_id),
                "departure_stop_id": int(dep_id),
                "arrival_stop_id": int(arr_id),
                "current_extra_baggage": current_extra_count,
                "new_extra_baggage": new_extra_count,
                "delta": delta,
            }
        )

    return plans, total_delta


def _plan_cancel(
    cur,
    purchase_id: int,
    ticket_ids: Sequence[int],
    *,
    lock_tickets: bool = False,
) -> tuple[list[dict[str, Any]], float]:
    if not ticket_ids:
        raise HTTPException(status_code=400, detail="No tickets provided")

    seen: set[int] = set()
    plans: list[dict[str, Any]] = []
    total_delta = 0.0

    for ticket_id in ticket_ids:
        if ticket_id in seen:
            raise HTTPException(status_code=400, detail="Duplicate ticket in request")
        seen.add(ticket_id)

        ticket_query = (
            "SELECT tour_id, departure_stop_id, arrival_stop_id, extra_baggage, purchase_id FROM ticket WHERE id = %s"
        )
        if lock_tickets:
            ticket_query += " FOR UPDATE"
        cur.execute(ticket_query, (ticket_id,))
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        tour_id, dep_id, arr_id, extra_baggage, purchase_ref = ticket_row
        if purchase_ref != purchase_id:
            raise HTTPException(status_code=403, detail="Ticket does not belong to this purchase")

        base_price = _resolve_ticket_price(cur, tour_id, dep_id, arr_id)
        if base_price is None:
            raise HTTPException(status_code=400, detail="Unable to calculate ticket price")

        baggage_price = float(base_price) * 0.1 * int(extra_baggage or 0)
        ticket_value = float(base_price) + baggage_price
        ticket_value = round(ticket_value, 2)
        total_delta -= ticket_value

        plans.append(
            {
                "ticket_id": int(ticket_id),
                "tour_id": int(tour_id),
                "value": ticket_value,
                "extra_baggage": int(extra_baggage or 0),
            }
        )

    return plans, total_delta


@session_router.get("/q/{opaque}")
def exchange_qr_session(opaque: str, request: Request) -> RedirectResponse:
    guard_public_request(request, "qr_exchange")
    session = link_sessions.redeem_session(opaque, scope="view")
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(timezone.utc)
    if session.exp <= now:
        raise HTTPException(status_code=410, detail="Session expired")

    purchase_id = _resolve_purchase_id(session)

    guard_public_request(
        request,
        "qr_exchange",
        ticket_id=session.ticket_id,
        purchase_id=purchase_id,
    )

    remaining = int((session.exp - now).total_seconds())
    if remaining <= 0:
        remaining = 60

    response = RedirectResponse(
        url=_redirect_base_url(purchase_id),
        status_code=302,
    )
    csrf_token = _generate_csrf_token()
    response.set_cookie(
        _purchase_cookie_name(purchase_id),
        session.jti,
        max_age=remaining,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        _CSRF_COOKIE_NAME,
        csrf_token,
        max_age=remaining,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/tickets/{ticket_id}")
def get_public_ticket(ticket_id: int, request: Request) -> Any:
    session, resolved_ticket_id, resolved_purchase_id, _cookie = _require_view_session(
        request, ticket_id=ticket_id
    )
    guard_public_request(
        request,
        "ticket_view",
        ticket_id=resolved_ticket_id,
        purchase_id=resolved_purchase_id,
    )

    link_sessions.touch_session_usage(session.jti, scope="view")

    dto = _load_ticket_dto(resolved_ticket_id, _DEFAULT_LANG)
    payload: dict[str, Any] = {"ticket": dto}
    if isinstance(dto, Mapping):
        payload.update(dto)
    return jsonable_encoder(payload)


@router.post("/tickets/{ticket_id}/reschedule")
def reschedule_public_ticket(
    ticket_id: int, data: TicketRescheduleRequest, request: Request
) -> Any:
    session, resolved_ticket_id, resolved_purchase_id, _cookie = _require_view_session(
        request, ticket_id=ticket_id
    )
    guard_public_request(
        request,
        "ticket_reschedule",
        ticket_id=resolved_ticket_id,
        purchase_id=resolved_purchase_id,
    )
    _require_csrf(request)
    link_sessions.touch_session_usage(session.jti, scope="view")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT seat_id, tour_id, departure_stop_id, arrival_stop_id
              FROM ticket
             WHERE id = %s
             FOR UPDATE
            """,
            (resolved_ticket_id,),
        )
        ticket_row = cur.fetchone()
        if not ticket_row:
            raise HTTPException(status_code=404, detail="Ticket not found")

        current_seat_id, _current_tour_id, departure_stop_id, arrival_stop_id = ticket_row
        if current_seat_id is None:
            raise HTTPException(status_code=400, detail="Ticket has no assigned seat")
        if departure_stop_id is None or arrival_stop_id is None:
            raise HTTPException(status_code=400, detail="Ticket has no route information")

        _perform_reschedule(
            cur,
            ticket_id=resolved_ticket_id,
            current_seat_id=int(current_seat_id),
            target_tour_id=data.tour_id,
            seat_num=data.seat_num,
            departure_stop_id=int(departure_stop_id),
            arrival_stop_id=int(arrival_stop_id),
        )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:  # pragma: no cover - defensive
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        cur.close()
        conn.close()

    dto = _load_ticket_dto(resolved_ticket_id, _DEFAULT_LANG)
    payload: dict[str, Any] = {"ticket": dto}
    if isinstance(dto, Mapping):
        payload.update(dto)
    return jsonable_encoder(payload)


@router.get("/purchase/{purchase_id}")
def get_public_purchase(purchase_id: int, request: Request) -> Any:
    session, resolved_ticket_id, resolved_purchase_id, _cookie = _require_view_session(
        request, purchase_id=purchase_id
    )
    guard_public_request(
        request,
        "purchase_view",
        ticket_id=resolved_ticket_id,
        purchase_id=resolved_purchase_id,
    )

    link_sessions.touch_session_usage(session.jti, scope="view")

    dto = _load_purchase_view(resolved_purchase_id, _DEFAULT_LANG)
    return jsonable_encoder(dto)


@router.get("/tickets/{ticket_id}/pdf")
def get_public_ticket_pdf(
    ticket_id: int,
    request: Request,
    purchase_id: int = Query(..., gt=0),
    email: str = Query(..., min_length=1),
) -> Response:
    guard_public_request(
        request,
        "ticket_pdf",
        ticket_id=ticket_id,
        purchase_id=purchase_id,
    )
    _verify_ticket_purchase_access(ticket_id, purchase_id, email)

    dto = _load_ticket_dto(ticket_id, _DEFAULT_LANG)

    deep_link: str | None = None
    purchase_info = dto.get("purchase") if isinstance(dto, Mapping) else None
    segment = dto.get("segment") if isinstance(dto, Mapping) else None
    departure_ctx = {}
    if isinstance(segment, Mapping):
        departure_ctx = segment.get("departure") or {}
    tour = dto.get("tour") if isinstance(dto, Mapping) else None
    tour_date = tour.get("date") if isinstance(tour, Mapping) else None
    departure_time = departure_ctx.get("time") if isinstance(departure_ctx, Mapping) else None

    departure_dt: datetime | None = None
    if tour_date:
        try:
            departure_dt = combine_departure_datetime(tour_date, departure_time)
        except ValueError:
            departure_dt = None

    resolved_purchase_id = purchase_id
    if isinstance(purchase_info, Mapping):
        purchase_ref = purchase_info.get("id")
        if purchase_ref:
            resolved_purchase_id = purchase_ref

    try:
        opaque, _expires_at = get_or_create_view_session(
            ticket_id,
            purchase_id=resolved_purchase_id,
            lang=_DEFAULT_LANG,
            departure_dt=departure_dt,
            scopes=DEFAULT_TICKET_SCOPES,
        )
    except Exception:  # pragma: no cover - defensive fallback
        logger.exception("Failed to prepare public ticket deep link for %s", ticket_id)
    else:
        try:
            base_url = get_client_app_base()
        except ValueError as exc:
            raise HTTPException(500, str(exc)) from exc
        deep_link = build_deep_link(opaque, base_url=base_url)

    try:
        pdf_bytes = render_ticket_pdf(dto, deep_link)
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        logger.exception(
            "Failed to render public ticket PDF for ticket %s (purchase %s)",
            ticket_id,
            resolved_purchase_id,
        )
        raise HTTPException(500, "Failed to render ticket PDF") from exc

    headers = {
        "Content-Disposition": f'inline; filename="ticket-{ticket_id}.pdf"',
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.get("/purchase/{purchase_id}/pdf")
def get_public_purchase_pdf(purchase_id: int, request: Request) -> Response:
    session, resolved_ticket_id, resolved_purchase_id, _cookie = _require_view_session(
        request, purchase_id=purchase_id
    )
    guard_public_request(
        request,
        "purchase_pdf",
        ticket_id=resolved_ticket_id,
        purchase_id=resolved_purchase_id,
    )

    link_sessions.touch_session_usage(session.jti, scope="view")

    purchase = _load_purchase_view(resolved_purchase_id, _DEFAULT_LANG)
    tickets = purchase.get("tickets", []) if isinstance(purchase, Mapping) else []
    try:
        base_url = get_client_app_base()
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc
    deep_link = build_deep_link(session.jti, base_url=base_url)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for ticket in tickets:
            ticket_info = ticket if isinstance(ticket, Mapping) else {}
            ticket_obj = ticket_info.get("ticket") if isinstance(ticket_info.get("ticket"), Mapping) else None
            ticket_id_value = None
            if isinstance(ticket_obj, Mapping):
                ticket_id_value = ticket_obj.get("id")
            if ticket_id_value is None:
                ticket_id_value = ticket_info.get("id")
            if ticket_id_value is None:
                continue
            try:
                pdf_bytes = render_ticket_pdf(ticket_info, deep_link)
            except Exception as exc:  # pragma: no cover - runtime diagnostics
                logger.exception(
                    "Failed to render purchase ticket PDF for ticket %s (purchase %s)",
                    ticket_id_value,
                    resolved_purchase_id,
                )
                raise HTTPException(500, "Failed to render ticket PDF") from exc
            archive.writestr(f"ticket-{ticket_id_value}.pdf", pdf_bytes)

    buffer.seek(0)
    headers = {
        "Content-Disposition": f'attachment; filename="purchase-{resolved_purchase_id}.zip"',
    }
    return Response(content=buffer.getvalue(), media_type="application/zip", headers=headers)


@router.post("/purchase/{purchase_id}/pay")
def public_pay(purchase_id: int, request: Request) -> Mapping[str, Any]:
    _session, ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "pay"
    )

    amount_due = 0.0
    payment_description = None
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            amount_due, status = _load_purchase_state(cur, resolved_purchase_id)
            _ensure_purchase_active(status)
            payment_description = liqpay.build_purchase_description(cur, resolved_purchase_id)
    finally:
        conn.close()

    if amount_due <= 0:
        raise HTTPException(status_code=400, detail="Purchase has no outstanding balance")

    checkout = liqpay.build_checkout_payload(
        resolved_purchase_id,
        amount_due,
        ticket_id=ticket_id,
        description=payment_description,
    )
    payload = checkout.get("payload") if isinstance(checkout, Mapping) else None
    order_id = payload.get("order_id") if isinstance(payload, Mapping) else None
    if order_id:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if _purchase_has_column(cur, "liqpay_order_id"):
                    cur.execute(
                        "UPDATE purchase SET liqpay_order_id=%s, update_at=NOW() WHERE id=%s",
                        (str(order_id), resolved_purchase_id),
                    )
                else:
                    logger.warning(
                        "Skipping LiqPay order_id persistence for purchase=%s because column liqpay_order_id is missing",
                        resolved_purchase_id,
                    )
            conn.commit()
        finally:
            conn.close()

    return checkout


@router.post("/purchase/{purchase_id}/reschedule/quote")
def public_reschedule_quote(
    purchase_id: int, data: RescheduleRequest, request: Request
) -> Mapping[str, Any]:
    _session, _ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "reschedule_quote"
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        amount_due, status = _load_purchase_state(cur, resolved_purchase_id)
        _ensure_purchase_active(status)
        plans, difference = _plan_reschedule(cur, resolved_purchase_id, data.tickets)
    finally:
        cur.close()
        conn.close()

    total_difference = round(difference, 2)
    new_amount_due = _round_currency(amount_due + difference)

    response = {
        "tickets": [
            {
                "ticket_id": plan["ticket_id"],
                "current_tour_id": plan["current_tour_id"],
                "new_tour_id": plan["target_tour_id"],
                "seat_num": plan["seat_num"],
                "current_price": round(plan["current_price"], 2),
                "new_price": round(plan["target_price"], 2),
                "difference": round(plan["difference"], 2),
                "no_change": bool(plan["no_change"]),
            }
            for plan in plans
        ],
        "total_difference": total_difference,
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "need_payment": new_amount_due > 0,
    }
    return jsonable_encoder(response)


@router.post("/purchase/{purchase_id}/reschedule")
def public_reschedule(
    purchase_id: int, data: RescheduleRequest, request: Request
) -> Mapping[str, Any]:
    session, _ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "reschedule"
    )

    conn = get_connection()
    cur = conn.cursor()
    plans: list[dict[str, Any]] = []
    amount_due = 0.0
    difference = 0.0
    new_amount_due = 0.0
    status = "reserved"
    try:
        amount_due, status = _load_purchase_state(
            cur, resolved_purchase_id, for_update=True
        )
        _ensure_purchase_active(status)
        plans, difference = _plan_reschedule(
            cur,
            resolved_purchase_id,
            data.tickets,
            lock_tickets=True,
            lock_seats=True,
        )

        for plan in plans:
            if plan["no_change"]:
                continue
            _perform_reschedule(
                cur,
                ticket_id=plan["ticket_id"],
                current_seat_id=plan["current_seat_id"],
                target_tour_id=plan["target_tour_id"],
                seat_num=plan["seat_num"],
                departure_stop_id=plan["departure_stop_id"],
                arrival_stop_id=plan["arrival_stop_id"],
            )

        new_amount_due = _round_currency(amount_due + difference)
        status_update = _status_for_balance(status, new_amount_due, has_tickets=True)
        cur.execute(
            "UPDATE purchase SET amount_due=%s, status=%s, update_at=NOW() WHERE id=%s",
            (new_amount_due, status_update, resolved_purchase_id),
        )

        total_difference = round(difference, 2)
        if total_difference != 0:
            _log_sale(
                cur,
                resolved_purchase_id,
                "reschedule",
                total_difference,
                actor=session.jti,
            )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    response = {
        "tickets": [
            {
                "ticket_id": plan["ticket_id"],
                "current_tour_id": plan["current_tour_id"],
                "new_tour_id": plan["target_tour_id"],
                "seat_num": plan["seat_num"],
                "current_price": round(plan["current_price"], 2),
                "new_price": round(plan["target_price"], 2),
                "difference": round(plan["difference"], 2),
                "no_change": bool(plan["no_change"]),
            }
            for plan in plans
        ],
        "total_difference": round(difference, 2),
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "need_payment": new_amount_due > 0,
    }
    return jsonable_encoder(response)


@router.post("/purchase/{purchase_id}/baggage/quote")
def public_baggage_quote(
    purchase_id: int, data: BaggageRequest, request: Request
) -> Mapping[str, Any]:
    _session, _ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "baggage_quote"
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        amount_due, status = _load_purchase_state(cur, resolved_purchase_id)
        _ensure_purchase_active(status)
        plans, delta = _plan_baggage(cur, resolved_purchase_id, data.tickets, status)
    finally:
        cur.close()
        conn.close()

    total_delta = round(delta, 2)
    new_amount_due = _round_currency(amount_due + delta)

    response = {
        "tickets": [
            {
                "ticket_id": plan["ticket_id"],
                "current_extra_baggage": plan["current_extra_baggage"],
                "new_extra_baggage": plan["new_extra_baggage"],
                "delta": plan["delta"],
            }
            for plan in plans
        ],
        "total_delta": total_delta,
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "need_payment": new_amount_due > 0,
    }
    return jsonable_encoder(response)


@router.post("/purchase/{purchase_id}/cancel/preview")
def public_cancel_preview(
    purchase_id: int, data: CancelRequest, request: Request
) -> Mapping[str, Any]:
    _session, _ticket_id, resolved_purchase_id, _cookie_name = _require_purchase_context(
        request, purchase_id, "cancel_preview"
    )

    conn = get_connection()
    cur = conn.cursor()
    try:
        amount_due, status = _load_purchase_state(cur, resolved_purchase_id)
        _ensure_purchase_active(status)
        plans, delta = _plan_cancel(
            cur,
            resolved_purchase_id,
            data.ticket_ids,
            lock_tickets=False,
        )
    finally:
        cur.close()
        conn.close()

    new_amount_due = _round_currency(amount_due + delta)

    response = {
        "ticket_ids": [plan["ticket_id"] for plan in plans],
        "amount_delta": round(delta, 2),
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "need_payment": new_amount_due > 0,
    }
    return jsonable_encoder(response)


@router.post("/purchase/{purchase_id}/baggage")
def public_baggage(
    purchase_id: int, data: BaggageRequest, request: Request
) -> Mapping[str, Any]:
    session, _ticket_id, resolved_purchase_id, _cookie = _require_purchase_context(
        request, purchase_id, "baggage"
    )

    conn = get_connection()
    cur = conn.cursor()
    plans: list[dict[str, Any]] = []
    amount_due = 0.0
    delta = 0.0
    new_amount_due = 0.0
    status = "reserved"
    try:
        amount_due, status = _load_purchase_state(
            cur, resolved_purchase_id, for_update=True
        )
        _ensure_purchase_active(status)
        plans, delta = _plan_baggage(
            cur,
            resolved_purchase_id,
            data.tickets,
            status,
            lock_tickets=True,
        )

        for plan in plans:
            if plan["current_extra_baggage"] == plan["new_extra_baggage"]:
                continue
            cur.execute(
                "UPDATE ticket SET extra_baggage=%s WHERE id=%s",
                (plan["new_extra_baggage"], plan["ticket_id"]),
            )

        new_amount_due = _round_currency(amount_due + delta)
        status_update = _status_for_balance(status, new_amount_due, has_tickets=True)
        cur.execute(
            "UPDATE purchase SET amount_due=%s, status=%s, update_at=NOW() WHERE id=%s",
            (new_amount_due, status_update, resolved_purchase_id),
        )

        total_delta = round(delta, 2)
        if total_delta != 0:
            _log_sale(
                cur,
                resolved_purchase_id,
                "baggage",
                total_delta,
                actor=session.jti,
            )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    response = {
        "tickets": [
            {
                "ticket_id": plan["ticket_id"],
                "current_extra_baggage": plan["current_extra_baggage"],
                "new_extra_baggage": plan["new_extra_baggage"],
                "delta": plan["delta"],
            }
            for plan in plans
        ],
        "total_delta": round(delta, 2),
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "need_payment": new_amount_due > 0,
    }
    return jsonable_encoder(response)


@router.post("/purchase/{purchase_id}/cancel")
def public_cancel(
    purchase_id: int, data: CancelRequest, request: Request
) -> JSONResponse:
    session, _ticket_id, resolved_purchase_id, cookie_name = _require_purchase_context(
        request, purchase_id, "cancel"
    )

    conn = get_connection()
    cur = conn.cursor()
    plans: list[dict[str, Any]] = []
    amount_due = 0.0
    delta = 0.0
    new_amount_due = 0.0
    status = "reserved"
    remaining_tickets = 0
    try:
        amount_due, status = _load_purchase_state(
            cur, resolved_purchase_id, for_update=True
        )
        _ensure_purchase_active(status)
        plans, delta = _plan_cancel(
            cur,
            resolved_purchase_id,
            data.ticket_ids,
            lock_tickets=True,
        )

        for plan in plans:
            free_ticket(cur, plan["ticket_id"])
            link_sessions.revoke_ticket_sessions(plan["ticket_id"], conn=conn)

        cur.execute(
            "SELECT COUNT(*) FROM ticket WHERE purchase_id = %s",
            (resolved_purchase_id,),
        )
        count_row = cur.fetchone()
        remaining_tickets = int(count_row[0]) if count_row else 0
        has_tickets = remaining_tickets > 0

        new_amount_due = _round_currency(amount_due + delta)
        status_update = _status_for_balance(
            status, new_amount_due, has_tickets=has_tickets
        )
        cur.execute(
            "UPDATE purchase SET amount_due=%s, status=%s, update_at=NOW() WHERE id=%s",
            (new_amount_due, status_update, resolved_purchase_id),
        )

        total_delta = round(delta, 2)
        if total_delta != 0:
            _log_sale(
                cur,
                resolved_purchase_id,
                "cancelled",
                total_delta,
                actor=session.jti,
            )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    payload = {
        "cancelled_ticket_ids": [plan["ticket_id"] for plan in plans],
        "amount_delta": round(delta, 2),
        "current_amount_due": amount_due,
        "new_amount_due": new_amount_due,
        "remaining_tickets": remaining_tickets,
    }
    response = JSONResponse(jsonable_encoder(payload))
    if remaining_tickets == 0:
        response.set_cookie(
            _purchase_cookie_name(resolved_purchase_id),
            "",
            max_age=0,
            httponly=True,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            _CSRF_COOKIE_NAME,
            "",
            max_age=0,
            httponly=False,
            samesite="lax",
            path="/",
        )
    return response


__all__ = ["router", "session_router"]
