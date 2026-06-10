"""CheckBox (Ukrainian PRRO) fiscalization service.

Handles authentication, shift management, receipt creation and status polling
against the CheckBox API.  Fiscalization is triggered only for online (LiqPay)
payments — admin/offline payments must never call into this module.
"""

import logging
import os
import time
import threading
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)
_uvicorn_error_logger = logging.getLogger("uvicorn.error")


def _emit_fiscal_log(message: str, *args: Any) -> None:
    logger.warning(message, *args)
    _uvicorn_error_logger.warning(message, *args)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def is_enabled() -> bool:
    """Return True when CheckBox integration is switched on."""
    return _env("CHECKBOX_ENABLED", "false").lower() in ("true", "1", "yes")


def _api_url() -> str:
    return _env("CHECKBOX_API_URL", "https://api.checkbox.ua").rstrip("/")


# ---------------------------------------------------------------------------
# Token cache (module-level, thread-safe)
# ---------------------------------------------------------------------------

_token_lock = threading.Lock()
_cached_token: str | None = None
_token_expires_at: float = 0.0
_TOKEN_TTL = 12 * 3600  # refresh every 12 hours


def _get_token() -> str:
    """Authenticate cashier and return a bearer token (cached)."""
    global _cached_token, _token_expires_at

    with _token_lock:
        if _cached_token and time.time() < _token_expires_at:
            return _cached_token

    pin_code = _env("CHECKBOX_CASHIER_PIN")
    license_key = _env("CHECKBOX_LICENSE_KEY")

    if not pin_code:
        raise RuntimeError("CHECKBOX_CASHIER_PIN is required")

    headers: dict[str, str] = {}
    if license_key:
        headers["X-License-Key"] = license_key

    resp = httpx.post(
        f"{_api_url()}/api/v1/cashier/signinPinCode",
        json={"pin_code": pin_code},
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("CheckBox signin did not return access_token")

    with _token_lock:
        _cached_token = token
        _token_expires_at = time.time() + _TOKEN_TTL

    logger.info("CheckBox cashier token refreshed")
    return token


def _invalidate_token() -> None:
    global _cached_token, _token_expires_at
    with _token_lock:
        _cached_token = None
        _token_expires_at = 0.0


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_token()}"}


def get_token_for_healthcheck() -> str:
    """Public wrapper for token retrieval used by health checks."""
    return _get_token()


def get_cashier_shift_status(token: str) -> tuple[int, dict[str, Any] | None]:
    """Fetch current cashier shift status for diagnostics."""
    license_key = _env("CHECKBOX_LICENSE_KEY")
    headers = {"Authorization": f"Bearer {token}"}
    if license_key:
        headers["X-License-Key"] = license_key

    resp = httpx.get(
        f"{_api_url()}/api/v1/cashier/shift",
        headers=headers,
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.status_code, resp.json()



def _purchase_has_column(cur, column_name: str) -> bool:
    cur.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'purchase'
           AND column_name = %s
         LIMIT 1
        """,
        (column_name,),
    )
    return cur.fetchone() is not None


def _has_required_fiscal_columns(cur) -> tuple[bool, list[str]]:
    required = (
        "fiscal_status",
        "checkbox_receipt_id",
        "checkbox_fiscal_code",
        "fiscal_last_error",
        "fiscal_attempts",
        "fiscalized_at",
    )
    missing = [name for name in required if not _purchase_has_column(cur, name)]
    return (len(missing) == 0, missing)

# ---------------------------------------------------------------------------
# Shift management
# ---------------------------------------------------------------------------

_shift_lock = threading.Lock()
_active_shift_id: str | None = None


def _ensure_shift() -> str:
    """Ensure an OPENED shift exists, opening one if needed. Returns shift id."""
    global _active_shift_id

    license_key = _env("CHECKBOX_LICENSE_KEY")
    headers = {**_auth_headers()}
    if license_key:
        headers["X-License-Key"] = license_key

    # Check if there's already an active shift for this cashier
    try:
        resp = httpx.get(
            f"{_api_url()}/api/v1/cashier/shift",
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code == 200:
            shift = resp.json()
            if shift and shift.get("status") == "OPENED":
                shift_id = shift["id"]
                with _shift_lock:
                    _active_shift_id = shift_id
                return shift_id
    except Exception:
        logger.debug("Could not check existing shift, will try to open new one")

    # Open a new shift
    resp = httpx.post(
        f"{_api_url()}/api/v1/shifts",
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    shift = resp.json()
    shift_id = shift["id"]

    # Poll until OPENED (max 30s)
    deadline = time.time() + 30
    while time.time() < deadline:
        poll = httpx.get(
            f"{_api_url()}/api/v1/shifts/{shift_id}",
            headers=headers,
            timeout=10.0,
        )
        poll.raise_for_status()
        data = poll.json()
        if data.get("status") == "OPENED":
            with _shift_lock:
                _active_shift_id = shift_id
            logger.info("CheckBox shift %s opened", shift_id)
            return shift_id
        time.sleep(2)

    raise RuntimeError(f"CheckBox shift {shift_id} did not reach OPENED status within 30s")


# ---------------------------------------------------------------------------
# Receipt creation and polling
# ---------------------------------------------------------------------------

def _create_receipt(items: list[dict[str, Any]], payment_amount_kopecks: int) -> str:
    """Create a sell receipt and return the receipt id."""
    license_key = _env("CHECKBOX_LICENSE_KEY")
    headers = {**_auth_headers()}
    if license_key:
        headers["X-License-Key"] = license_key

    body: dict[str, Any] = {
        "goods": items,
        "payments": [
            {
                "type": "CASHLESS",
                "value": payment_amount_kopecks,
            }
        ],
    }

    resp = httpx.post(
        f"{_api_url()}/api/v1/receipts/sell",
        json=body,
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    receipt_id = data.get("id")
    if not receipt_id:
        raise RuntimeError("CheckBox receipt creation did not return id")
    logger.info("CheckBox receipt %s created", receipt_id)
    return receipt_id


def _poll_receipt(receipt_id: str) -> dict[str, Any]:
    """Poll receipt until terminal status. Returns receipt data."""
    headers = _auth_headers()
    deadline = time.time() + 60
    while time.time() < deadline:
        resp = httpx.get(
            f"{_api_url()}/api/v1/receipts/{receipt_id}",
            headers=headers,
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "")
        if status == "DONE":
            return data
        if status in ("ERROR", "CANCELLED"):
            raise RuntimeError(f"CheckBox receipt {receipt_id} ended with status {status}")
        time.sleep(2)
    raise RuntimeError(f"CheckBox receipt {receipt_id} did not reach DONE within 60s")


def get_receipt_png_url(receipt_id: str) -> str:
    """Return URL for the receipt PNG image."""
    return f"{_api_url()}/api/v1/receipts/{receipt_id}/png"


# ---------------------------------------------------------------------------
# Refund receipts
# ---------------------------------------------------------------------------

def _load_refund_items_for_tickets(
    cur, purchase_id: int, ticket_ids: list[int]
) -> tuple[list[dict[str, Any]], int]:
    """Build CheckBox refund goods entries from the listed tickets.

    Mirrors the structure of ``_load_purchase_receipt_items`` but limited to a
    subset of tickets — used when an admin issues a partial refund.
    """
    if not ticket_ids:
        return [], 0

    cur.execute(
        """
        SELECT
            t.id,
            t.extra_baggage,
            COALESCE(dep.stop_ua, dep.stop_name) AS departure_name,
            COALESCE(arr.stop_ua, arr.stop_name) AS arrival_name,
            p.price
        FROM ticket t
        JOIN tour tr ON tr.id = t.tour_id
        JOIN stop dep ON dep.id = t.departure_stop_id
        JOIN stop arr ON arr.id = t.arrival_stop_id
        JOIN prices p ON p.departure_stop_id = t.departure_stop_id
                     AND p.arrival_stop_id = t.arrival_stop_id
                     AND p.pricelist_id = tr.pricelist_id
        WHERE t.purchase_id = %s
          AND t.id = ANY(%s)
        ORDER BY t.id
        """,
        (purchase_id, list(ticket_ids)),
    )
    rows = cur.fetchall() or []

    items: list[dict[str, Any]] = []
    total_kopecks = 0
    for ticket_id, extra_baggage, dep_name, arr_name, base_price in rows:
        price_kopecks = int(round(float(base_price) * 100))
        items.append({
            "good": {
                "code": str(ticket_id),
                "name": f"Повернення: квиток {dep_name} – {arr_name}",
                "price": price_kopecks,
            },
            "quantity": 1000,
        })
        total_kopecks += price_kopecks

        extra_bag = int(extra_baggage or 0)
        if extra_bag > 0:
            baggage_price_kopecks = int(round(float(base_price) * 0.1 * extra_bag * 100))
            items.append({
                "good": {
                    "code": f"{ticket_id}-bag",
                    "name": "Повернення: додатковий багаж",
                    "price": baggage_price_kopecks,
                },
                "quantity": 1000,
            })
            total_kopecks += baggage_price_kopecks

    return items, total_kopecks


def _flat_refund_items(purchase_id: int, amount_kopecks: int) -> list[dict[str, Any]]:
    """Single-line refund position used when no ticket list is supplied."""
    return [
        {
            "good": {
                "code": f"refund-{purchase_id}",
                "name": f"Повернення коштів за замовлення #{purchase_id}",
                "price": amount_kopecks,
            },
            "quantity": 1000,
        }
    ]


def _create_refund_receipt_request(
    items: list[dict[str, Any]],
    amount_kopecks: int,
    *,
    related_receipt_id: str | None = None,
) -> str:
    """Post a refund (return) receipt to CheckBox and return the receipt id."""
    license_key = _env("CHECKBOX_LICENSE_KEY")
    headers = {**_auth_headers()}
    if license_key:
        headers["X-License-Key"] = license_key

    body: dict[str, Any] = {
        "goods": items,
        "payments": [
            {
                "type": "CASHLESS",
                "value": amount_kopecks,
            }
        ],
    }
    if related_receipt_id:
        body["related_receipt_id"] = related_receipt_id

    resp = httpx.post(
        f"{_api_url()}/api/v1/receipts/service",
        json=body,
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    receipt_id = data.get("id")
    if not receipt_id:
        raise RuntimeError("CheckBox refund receipt creation did not return id")
    logger.info("CheckBox refund receipt %s created", receipt_id)
    return receipt_id


def create_refund_receipt(
    purchase_id: int,
    ticket_ids: list[int] | None,
    amount: Decimal | float,
) -> dict[str, Any]:
    """Create a fiscal refund receipt for the given purchase/tickets.

    Each call produces a fresh fiscal document with its own number — partial
    refunds therefore get an independent receipt per call. When ``ticket_ids``
    is empty/None the receipt carries a single aggregate refund line for the
    requested amount.

    Returns ``{receipt_id, fiscal_number, status}``.
    """
    amount_kopecks = int(round(float(amount) * 100))
    if amount_kopecks <= 0:
        raise ValueError("refund amount must be positive")

    if not is_enabled():
        raise RuntimeError("CheckBox is disabled")

    from ..database import get_connection

    related_receipt_id: str | None = None
    items: list[dict[str, Any]]

    conn = get_connection()
    cur = conn.cursor()
    try:
        if _purchase_has_column(cur, "checkbox_receipt_id"):
            cur.execute(
                "SELECT checkbox_receipt_id FROM purchase WHERE id = %s",
                (purchase_id,),
            )
            row = cur.fetchone()
            if row and row[0]:
                related_receipt_id = str(row[0])

        if ticket_ids:
            items, items_kopecks = _load_refund_items_for_tickets(cur, purchase_id, list(ticket_ids))
            if not items:
                items = _flat_refund_items(purchase_id, amount_kopecks)
                items_kopecks = amount_kopecks
        else:
            items = _flat_refund_items(purchase_id, amount_kopecks)
            items_kopecks = amount_kopecks
    finally:
        cur.close()
        conn.close()

    # Use the explicit amount as the source of truth (admin can override the
    # ticket-aggregate). Items are informational; payments line drives the
    # fiscal total.
    _ensure_shift()
    receipt_id = _create_refund_receipt_request(
        items,
        amount_kopecks,
        related_receipt_id=related_receipt_id,
    )

    try:
        receipt_data = _poll_receipt(receipt_id)
    except Exception:
        # The receipt was accepted but did not reach DONE in time. Surface the
        # id so the caller can persist it and retry status polling later.
        return {
            "receipt_id": receipt_id,
            "fiscal_number": None,
            "status": "pending",
        }

    fiscal_number = (
        receipt_data.get("fiscal_code")
        or receipt_data.get("fiscal_number")
        or receipt_data.get("number")
    )

    return {
        "receipt_id": receipt_id,
        "fiscal_number": str(fiscal_number) if fiscal_number else None,
        "status": "done",
    }


# ---------------------------------------------------------------------------
# Data loading for receipt items
# ---------------------------------------------------------------------------

def _load_purchase_receipt_items(cur, purchase_id: int) -> tuple[list[dict[str, Any]], int]:
    """Query DB and build CheckBox receipt goods for a purchase.

    Returns (items, total_kopecks).
    """
    cur.execute(
        """
        SELECT
            t.id,
            t.extra_baggage,
            COALESCE(dep.stop_ua, dep.stop_name) AS departure_name,
            COALESCE(arr.stop_ua, arr.stop_name) AS arrival_name,
            p.price
        FROM ticket t
        JOIN tour tr ON tr.id = t.tour_id
        JOIN stop dep ON dep.id = t.departure_stop_id
        JOIN stop arr ON arr.id = t.arrival_stop_id
        JOIN prices p ON p.departure_stop_id = t.departure_stop_id
                     AND p.arrival_stop_id = t.arrival_stop_id
                     AND p.pricelist_id = tr.pricelist_id
        WHERE t.purchase_id = %s
        ORDER BY t.id
        """,
        (purchase_id,),
    )
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError(f"No tickets found for purchase {purchase_id}")

    items: list[dict[str, Any]] = []
    total_kopecks = 0

    for _ticket_id, extra_baggage, dep_name, arr_name, base_price in rows:
        price_kopecks = int(round(float(base_price) * 100))
        items.append({
            "good": {
                "code": str(_ticket_id),
                "name": f"Автобусний квиток {dep_name} – {arr_name}",
                "price": price_kopecks,
            },
            "quantity": 1000,  # 1 item in thousandths
        })
        total_kopecks += price_kopecks

        extra_bag = int(extra_baggage or 0)
        if extra_bag > 0:
            baggage_price_kopecks = int(round(float(base_price) * 0.1 * extra_bag * 100))
            items.append({
                "good": {
                    "code": f"{_ticket_id}-bag",
                    "name": "Додатковий багаж",
                    "price": baggage_price_kopecks,
                },
                "quantity": 1000,
            })
            total_kopecks += baggage_price_kopecks

    return items, total_kopecks


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def fiscalize_purchase(purchase_id: int) -> None:
    """Fiscalize a purchase via CheckBox. Safe to call multiple times (idempotent).

    This function manages its own DB connection and never raises — all errors
    are caught and persisted to the purchase row for later retry.
    """
    if not is_enabled():
        _emit_fiscal_log(
            "Skipping fiscalization for purchase=%s: CHECKBOX_ENABLED=false",
            purchase_id,
        )
        return
    _emit_fiscal_log("Starting fiscalization for purchase=%s", purchase_id)

    from ..database import get_connection

    conn = get_connection()
    cur = conn.cursor()
    try:
        has_columns, missing_columns = _has_required_fiscal_columns(cur)
        if not has_columns:
            logger.warning(
                "Skipping fiscalization for purchase=%s; missing columns: %s",
                purchase_id,
                ", ".join(missing_columns),
            )
            return

        # Lock the row and check current fiscal status
        cur.execute(
            "SELECT fiscal_status, checkbox_receipt_id FROM purchase WHERE id = %s FOR UPDATE",
            (purchase_id,),
        )
        row = cur.fetchone()
        if not row:
            logger.warning("fiscalize_purchase: purchase %s not found", purchase_id)
            return

        fiscal_status, existing_receipt_id = row

        # Idempotency: skip if already done
        if fiscal_status == "done":
            logger.info("Purchase %s already fiscalized, skipping", purchase_id)
            conn.commit()
            return

        # Skip if currently being processed by another thread
        if fiscal_status == "processing":
            logger.info("Purchase %s fiscalization already in progress, skipping", purchase_id)
            conn.commit()
            return

        # Mark as processing
        cur.execute(
            "UPDATE purchase SET fiscal_status = 'processing', update_at = NOW() WHERE id = %s",
            (purchase_id,),
        )
        conn.commit()

        # Load receipt items
        items, total_kopecks = _load_purchase_receipt_items(cur, purchase_id)

        # If we already have a receipt_id from a previous attempt, try polling it
        # instead of creating a duplicate
        receipt_id = existing_receipt_id
        if not receipt_id:
            _emit_fiscal_log("Opening/ensuring CheckBox shift for purchase=%s", purchase_id)
            _ensure_shift()
            _emit_fiscal_log("Creating CheckBox receipt for purchase=%s amount_kopecks=%s", purchase_id, total_kopecks)
            receipt_id = _create_receipt(items, total_kopecks)
            # Persist receipt_id immediately so we don't create duplicates on retry
            cur.execute(
                "UPDATE purchase SET checkbox_receipt_id = %s, update_at = NOW() WHERE id = %s",
                (receipt_id, purchase_id),
            )
            conn.commit()

        # Poll until DONE
        receipt_data = _poll_receipt(receipt_id)
        fiscal_code = receipt_data.get("fiscal_code", "")

        # Success — persist final state
        cur.execute(
            """
            UPDATE purchase
               SET fiscal_status = 'done',
                   checkbox_receipt_id = %s,
                   checkbox_fiscal_code = %s,
                   fiscal_last_error = NULL,
                   fiscalized_at = NOW(),
                   update_at = NOW()
             WHERE id = %s
            """,
            (receipt_id, fiscal_code, purchase_id),
        )
        conn.commit()
        logger.info(
            "Purchase %s fiscalized successfully: receipt=%s fiscal_code=%s",
            purchase_id, receipt_id, fiscal_code,
        )
        _emit_fiscal_log(
            "Fiscalization completed for purchase=%s receipt=%s fiscal_code=%s",
            purchase_id,
            receipt_id,
            fiscal_code,
        )

    except Exception as exc:
        conn.rollback()
        error_msg = str(exc)[:500]
        logger.exception("Fiscalization failed for purchase %s", purchase_id)
        _emit_fiscal_log(
            "Fiscalization failed for purchase=%s reason=%s",
            purchase_id,
            error_msg,
        )

        # If auth-related, invalidate cached token for next attempt
        if "401" in error_msg or "403" in error_msg or "Unauthorized" in error_msg:
            _invalidate_token()

        try:
            cur.execute(
                """
                UPDATE purchase
                   SET fiscal_status = 'failed',
                       fiscal_last_error = %s,
                       fiscal_attempts = COALESCE(fiscal_attempts, 0) + 1,
                       update_at = NOW()
                 WHERE id = %s
                """,
                (error_msg, purchase_id),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to persist fiscal error for purchase %s", purchase_id)
            conn.rollback()
    finally:
        cur.close()
        conn.close()
