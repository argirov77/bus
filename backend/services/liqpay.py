import base64
import hashlib
import json
import os
from typing import Any, Mapping

from ..utils.client_app import get_client_app_base


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
    result_url: str,
) -> dict[str, Any]:
    public_key = _env("LIQPAY_PUBLIC_KEY", "sandbox")
    currency = _env("LIQPAY_CURRENCY", "UAH")

    description = f"Ticket #{ticket_id}" if ticket_id is not None else f"Purchase #{purchase_id}"
    payload = {
        "version": "3",
        "public_key": public_key,
        "action": "pay",
        "amount": round(max(amount, 0.0), 2),
        "currency": currency,
        "description": description,
        "order_id": f"purchase-{purchase_id}" if ticket_id is None else f"ticket-{ticket_id}-{purchase_id}",
        "result_url": result_url,
    }

    data, signature = encode_payload(payload)

    return {
        "provider": "liqpay",
        "data": data,
        "signature": signature,
        "payload": payload,
    }


def build_checkout_payload(
    purchase_id: int,
    amount: float,
    *,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Single source of truth for all online payment payload scenarios."""
    result_url = f"{get_client_app_base()}/purchase/{purchase_id}"
    return build_payment_payload(
        purchase_id,
        amount,
        ticket_id=ticket_id,
        result_url=result_url,
    )


def verify_signature(data: str, signature: str) -> bool:
    expected_signature = sign(data)
    return expected_signature == signature
