"""Telegram notification service for staff chat notifications."""

from __future__ import annotations

import html
import logging
import os
import time
from typing import Any, Mapping, Optional

import httpx

logger = logging.getLogger(__name__)

_TELEGRAM_API_URL = "https://api.telegram.org"
_HTTP_TIMEOUT = 5.0
_RETRY_BACKOFFS = (1.0, 2.0, 4.0, 8.0, 16.0)


def is_enabled() -> bool:
    """Return True if Telegram notifications are configured and enabled."""
    if os.getenv("TELEGRAM_ENABLED", "false").strip().lower() not in {"true", "1", "yes"}:
        return False
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def send_message(text: str, parse_mode: Optional[str] = "HTML") -> bool:
    """Send a message to the configured Telegram chat.

    Retries transient network errors and 5xx/429 responses with exponential
    backoff so short DNS/connectivity blips do not drop notifications. Never
    raises — failures are logged so they do not break the main request flow.
    """
    if not is_enabled():
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    api_url = os.getenv("TELEGRAM_API_URL", _TELEGRAM_API_URL).rstrip("/")

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    url = f"{api_url}/bot{token}/sendMessage"
    attempts = len(_RETRY_BACKOFFS) + 1
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.post(url, data=payload, timeout=_HTTP_TIMEOUT)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt < attempts:
                delay = _RETRY_BACKOFFS[attempt - 1]
                logger.warning(
                    "Telegram sendMessage transport error (attempt %s/%s): %s; retrying in %.1fs",
                    attempt, attempts, exc, delay,
                )
                time.sleep(delay)
                continue
            logger.exception("Telegram sendMessage failed after %s attempts", attempts)
            return False
        except Exception:
            logger.exception("Telegram sendMessage raised an unexpected exception")
            return False

        if response.status_code < 400:
            return True

        retriable = response.status_code >= 500 or response.status_code == 429
        if retriable and attempt < attempts:
            delay = _RETRY_BACKOFFS[attempt - 1]
            logger.warning(
                "Telegram sendMessage retriable status=%s (attempt %s/%s); retrying in %.1fs body=%s",
                response.status_code, attempt, attempts, delay, response.text[:500],
            )
            time.sleep(delay)
            continue

        logger.error(
            "Telegram sendMessage failed: status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        return False

    return False


# ---------------------------------------------------------------------------
# Refund event notifications
# ---------------------------------------------------------------------------

def _escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def _format_amount(amount: Any, currency: str = "UAH") -> str:
    try:
        return f"{float(amount):.2f} {currency}"
    except (TypeError, ValueError):
        return f"{amount} {currency}"


def _purchase_summary(purchase: Mapping[str, Any]) -> str:
    pid = purchase.get("id") or purchase.get("purchase_id")
    name = purchase.get("customer_name") or "—"
    email = purchase.get("customer_email") or "—"
    parts = [
        f"Заказ: <b>#{_escape(pid)}</b>",
        f"Клиент: {_escape(name)} ({_escape(email)})",
    ]
    return "\n".join(parts)


def _request_summary(request: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    ticket_ids = request.get("ticket_ids") or []
    if ticket_ids:
        lines.append(f"Билеты: {', '.join(str(t) for t in ticket_ids)}")
    amount_requested = request.get("amount_requested")
    if amount_requested is not None:
        currency = request.get("currency") or "UAH"
        lines.append(f"Сумма заявки: {_format_amount(amount_requested, currency)}")
    reason = request.get("reason")
    if reason:
        lines.append(f"Причина: {_escape(reason)}")
    return lines


def notify_refund_requested(
    purchase: Mapping[str, Any],
    request: Mapping[str, Any],
    requester: str,
) -> bool:
    """Notify staff that a refund request was created (by customer or admin)."""
    if not is_enabled():
        return False
    header = (
        "🔁 <b>Новая заявка на возврат</b>"
        if (requester or "").lower() != "admin"
        else "🔁 <b>Администратор создал заявку на возврат</b>"
    )
    lines = [header, _purchase_summary(purchase), *_request_summary(request)]
    return send_message("\n".join(lines))


def notify_refund_completed(
    purchase: Mapping[str, Any],
    request: Mapping[str, Any],
) -> bool:
    """Notify staff that a refund was processed end-to-end (LiqPay + fiscal)."""
    if not is_enabled():
        return False
    currency = request.get("currency") or "UAH"
    amount_refunded = request.get("amount_refunded") or request.get("amount_requested")
    lines = [
        "✅ <b>Возврат завершён</b>",
        _purchase_summary(purchase),
        f"Возвращено: <b>{_format_amount(amount_refunded, currency)}</b>",
    ]
    liqpay_id = request.get("liqpay_refund_id")
    if liqpay_id:
        lines.append(f"LiqPay: {_escape(liqpay_id)}")
    fiscal = request.get("fiscal_receipt_number") or request.get("fiscal_receipt_id")
    if fiscal:
        lines.append(f"Фискальный чек: {_escape(fiscal)}")
    return send_message("\n".join(lines))


def notify_refund_failed(
    purchase: Mapping[str, Any],
    request: Mapping[str, Any],
    error: str | None,
) -> bool:
    """Notify staff that a refund processing attempt failed."""
    if not is_enabled():
        return False
    lines = [
        "❌ <b>Ошибка возврата</b>",
        _purchase_summary(purchase),
    ]
    request_id = request.get("id")
    if request_id is not None:
        lines.append(f"Заявка: #{_escape(request_id)}")
    if error:
        lines.append(f"Причина: {_escape(error)[:500]}")
    return send_message("\n".join(lines))
