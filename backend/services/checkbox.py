"""CheckBox (Ukrainian PRRO) fiscalization service.

Handles authentication, shift management, receipt creation and status polling
against the CheckBox API.  Fiscalization is triggered only for online (LiqPay)
payments — admin/offline payments must never call into this module.
"""

import logging
import os
import time
import threading
from typing import Any

import httpx

logger = logging.getLogger(__name__)

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

    login = _env("CHECKBOX_CASHIER_LOGIN")
    password = _env("CHECKBOX_CASHIER_PASSWORD")

    if not login or not password:
        raise RuntimeError("CHECKBOX_CASHIER_LOGIN and CHECKBOX_CASHIER_PASSWORD are required")

    resp = httpx.post(
        f"{_api_url()}/api/v1/cashier/signin",
        json={"login": login, "password": password},
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
        return

    from ..database import get_connection

    conn = get_connection()
    cur = conn.cursor()
    try:
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
            _ensure_shift()
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

    except Exception as exc:
        conn.rollback()
        error_msg = str(exc)[:500]
        logger.exception("Fiscalization failed for purchase %s", purchase_id)

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
