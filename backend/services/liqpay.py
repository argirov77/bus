import base64
import hashlib
import json
import logging
import os
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Sequence

import httpx

from ..utils.client_app import build_liqpay_result_url, build_liqpay_server_url


logger = logging.getLogger(__name__)

LIQPAY_CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"
LIQPAY_API_URL = "https://www.liqpay.ua/api/request"


def _env(key: str, default: str) -> str:
    value = os.getenv(key)
    return value if value else default


def sign(data: str, private_key: str | None = None) -> str:
    key = private_key or _env("LIQPAY_PRIVATE_KEY", "sandbox")
    signature_raw = f"{key}{data}{key}".encode("utf-8")
    return base64.b64encode(hashlib.sha1(signature_raw).digest()).decode("utf-8")


def encode_payload(payload: Mapping[str, Any]) -> tuple[str, str]:
    payload_json = json.dumps(payload, separators=(",", ":"))
    data = base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")
    signature = sign(data)
    return data, signature


def decode_payload(data: str) -> Mapping[str, Any]:
    decoded_json = base64.b64decode(data).decode("utf-8")
    return json.loads(decoded_json)


def build_payment_payload(
    purchase_id: int,
    amount: float,
    *,
    ticket_id: int | None = None,
    description: str | None = None,
    result_url: str,
    server_url: str,
    order_id: str,
) -> dict[str, Any]:
    public_key = _env("LIQPAY_PUBLIC_KEY", "sandbox")
    currency = _env("LIQPAY_CURRENCY", "UAH")

    description_value = description or (
        f"Ticket #{ticket_id}" if ticket_id is not None else f"Purchase #{purchase_id}"
    )
    payload = {
        "version": "3",
        "public_key": public_key,
        "action": "pay",
        "amount": round(max(amount, 0.0), 2),
        "currency": currency,
        "description": description_value,
        "order_id": order_id,
        "result_url": result_url,
        "server_url": server_url,
    }

    data, signature = encode_payload(payload)

    return {
        "provider": "liqpay",
        "checkout_url": f"{LIQPAY_CHECKOUT_URL}?data={data}&signature={signature}",
        "checkout_form_url": LIQPAY_CHECKOUT_URL,
        "data": data,
        "signature": signature,
        "payload": payload,
    }


def build_checkout_payload(
    purchase_id: int,
    amount: float,
    *,
    ticket_id: int | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Single source of truth for all online payment payload scenarios."""
    order_id = f"purchase-{purchase_id}" if ticket_id is None else f"ticket-{ticket_id}-{purchase_id}"
    result_url = build_liqpay_result_url(order_id=order_id, purchase_id=purchase_id)
    server_url = build_liqpay_server_url()
    return build_payment_payload(
        purchase_id,
        amount,
        ticket_id=ticket_id,
        description=description,
        result_url=result_url,
        server_url=server_url,
        order_id=order_id,
    )


def build_purchase_description(cur, purchase_id: int) -> str | None:
    """Build a human-friendly LiqPay payment description for a purchase."""

    cur.execute(
        """
        SELECT
            tr.date,
            COALESCE(dep.stop_ua, dep.stop_name),
            COALESCE(arr.stop_ua, arr.stop_name)
        FROM ticket t
        JOIN tour tr ON tr.id = t.tour_id
        JOIN stop dep ON dep.id = t.departure_stop_id
        JOIN stop arr ON arr.id = t.arrival_stop_id
        WHERE t.purchase_id = %s
        ORDER BY tr.date ASC, t.id ASC
        """,
        (purchase_id,),
    )
    rows: Sequence[tuple[date, str, str]] = cur.fetchall() or []
    if not rows:
        return None

    outbound_date, departure_name, arrival_name = rows[0]
    seats_count = len(rows)
    outbound_date_text = outbound_date.strftime("%d.%m.%Y")
    unique_dates = sorted({row[0] for row in rows})

    parts = [
        f"Відправлення: {departure_name}",
        f"Прибуття: {arrival_name}",
        f"Дата: {outbound_date_text}",
        f"Місць: {seats_count}",
    ]

    if len(unique_dates) > 1:
        return_date_text = unique_dates[1].strftime("%d.%m.%Y")
        parts.append(f"Зворотна дата: {return_date_text}")

    return "; ".join(parts)[:255]


def verify_signature(data: str, signature: str) -> bool:
    expected_signature = sign(data)
    return expected_signature == signature


def extract_error(body: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    """Pull LiqPay's error code/description out of an API response body.

    Only the ``err_*``/``error_*`` keys are read: a successful response echoes
    back the payment ``description`` we sent, which is not an error at all.
    """
    if not isinstance(body, Mapping):
        return None, None
    code = body.get("err_code") or body.get("error_code")
    description = body.get("err_description") or body.get("error_description")
    return (
        str(code) if code not in (None, "") else None,
        str(description) if description not in (None, "") else None,
    )


def describe_refund_result(result: Mapping[str, Any]) -> str:
    """Human-readable one-liner for a rejected refund.

    ``status=error`` alone is useless when triaging: LiqPay always ships the
    real cause in ``err_code``/``err_description``, so keep them together.
    """
    parts = [f"status={result.get('status') or 'unknown'}"]
    err_code = result.get("err_code")
    err_description = result.get("err_description")
    if err_code:
        parts.append(f"code={err_code}")
    if err_description:
        parts.append(f"description={err_description}")
    return " ".join(parts)


def refund_payment(
    order_id: str,
    amount: Decimal | float,
    comment: str | None = None,
) -> dict[str, Any]:
    """Issue a (partial or full) refund through LiqPay.

    Returns a normalized dict
    ``{status, err_code, err_description, payment_id, refund_amount, raw}``.
    The LiqPay endpoint expects action=refund and the same order_id used at
    payment time. Partial refunds are supported by passing a smaller amount.
    """

    order_value = (order_id or "").strip()
    if not order_value:
        raise ValueError("order_id is required")

    amount_value = round(float(amount), 2)
    if amount_value <= 0:
        raise ValueError("refund amount must be positive")

    payload: dict[str, Any] = {
        "version": "3",
        "public_key": _env("LIQPAY_PUBLIC_KEY", "sandbox"),
        "action": "refund",
        "amount": amount_value,
        "order_id": order_value,
    }
    if comment:
        payload["description"] = comment[:255]

    data, signature = encode_payload(payload)

    timeout = float(os.getenv("LIQPAY_REFUND_TIMEOUT_S", "15"))
    response = httpx.post(
        LIQPAY_API_URL,
        data={"data": data, "signature": signature},
        timeout=timeout,
    )
    response.raise_for_status()

    body = response.json()
    if not isinstance(body, Mapping):
        raise ValueError("Unexpected LiqPay refund response")

    raw_status = str(body.get("status") or "").lower()
    err_code, err_description = extract_error(body)
    payment_id = body.get("payment_id")
    refund_amount_raw = (
        body.get("refund_amount")
        or body.get("amount_refund")
        or body.get("amount")
        or amount_value
    )
    try:
        refund_amount = float(refund_amount_raw)
    except (TypeError, ValueError):
        refund_amount = amount_value

    result = {
        "status": raw_status,
        "err_code": err_code,
        "err_description": err_description,
        "payment_id": str(payment_id) if payment_id is not None else None,
        "refund_amount": refund_amount,
        "raw": dict(body),
    }

    if not is_refund_success(raw_status):
        # The whole body is logged because LiqPay keeps adding fields and the
        # only chance to see them is the moment a refund is refused.
        logger.warning(
            "LiqPay refund refused for order_id=%s amount=%s: %s | raw=%s",
            order_value,
            amount_value,
            describe_refund_result(result),
            json.dumps(dict(body), ensure_ascii=False, default=str),
        )

    return result


def is_refund_success(status: str | None) -> bool:
    """LiqPay statuses that mean the refund landed at the bank side."""
    return (status or "").lower() in {"success", "ok", "sandbox", "reversed"}


def verify_order(order_id: str) -> Mapping[str, Any]:
    """Verify payment state for a specific order via LiqPay API."""

    order_value = (order_id or "").strip()
    if not order_value:
        raise ValueError("order_id is required")

    payload = {
        "version": "3",
        "public_key": _env("LIQPAY_PUBLIC_KEY", "sandbox"),
        "action": "status",
        "order_id": order_value,
    }
    data, signature = encode_payload(payload)

    timeout = float(os.getenv("LIQPAY_VERIFY_TIMEOUT_S", "8"))
    response = httpx.post(
        "https://www.liqpay.ua/api/request",
        data={"data": data, "signature": signature},
        timeout=timeout,
    )
    response.raise_for_status()

    body = response.json()
    if not isinstance(body, Mapping):
        raise ValueError("Unexpected LiqPay verify response")
    return body
