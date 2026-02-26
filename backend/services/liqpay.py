import base64
import hashlib
import json
import os
from datetime import date
from typing import Any, Mapping, Sequence

import httpx

from ..utils.client_app import build_liqpay_result_url, build_liqpay_server_url


LIQPAY_CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"


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
