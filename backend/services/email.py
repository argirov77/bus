"""Email utilities for sending ticket notifications."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Mapping, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

DEFAULT_EMAIL_LANG = "bg"

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"

_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

logger = logging.getLogger(__name__)

# Emails are multilingual: every message carries all supported languages at
# once, so the recipient always finds their own. This is the display order.
EMAIL_LANGS = ("ua", "ru", "bg", "en")

# Combined subject lines (all languages in one). Kept short so they read well
# in an inbox list.
_TICKET_SUBJECT = "Квиток / Билет / Ticket №{ticket} — Maximov Tours"
_RECEIPT_SUBJECT = "Чек / Фискален чек / Fiscal receipt №{purchase} — Maximov Tours"

_STATUS_LABELS = {
    "bg": {
        "paid": "потвърден",
        "reserved": "резервиран",
        "refunded": "възстановен",
        "cancelled": "отменен",
        "canceled": "отменен",
        "default": "активен",
    },
    "ru": {
        "paid": "оплачен",
        "reserved": "забронирован",
        "refunded": "возвращён",
        "cancelled": "отменён",
        "canceled": "отменён",
        "default": "активен",
    },
    "en": {
        "paid": "confirmed",
        "reserved": "reserved",
        "refunded": "refunded",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "default": "active",
    },
    "ua": {
        "paid": "підтверджений",
        "reserved": "зарезервований",
        "refunded": "повернений",
        "cancelled": "скасований",
        "canceled": "скасований",
        "default": "активний",
    },
}


class EmailConfigurationError(RuntimeError):
    """Raised when SMTP configuration is invalid or missing."""


def _get_env(name: str, required: bool = True) -> str | None:
    value = os.getenv(name)
    if required and not value:
        raise EmailConfigurationError(f"Environment variable {name} is not configured")
    return value


def _resolve_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_EMAIL_LANG
    return lang.lower()


def _format_date(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value
        return dt.strftime("%d.%m.%Y")
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _status_text(lang: str, status_value: str | None) -> str:
    labels = _STATUS_LABELS.get(lang) or _STATUS_LABELS[DEFAULT_EMAIL_LANG]
    key = (status_value or "").lower()
    if key in labels:
        return labels[key]
    return labels["default"]


def render_ticket_email(
    dto: Mapping[str, Any],
    deep_link: str,
    lang: str | None = None,
) -> Tuple[str, str]:
    """Render the multilingual ticket email subject and HTML body.

    ``lang`` is accepted for backwards compatibility but the rendered message
    always contains every language in :data:`EMAIL_LANGS`.
    """

    template = _ENV.get_template("ticket.html")

    ticket = dto.get("ticket") if isinstance(dto, Mapping) else None
    purchase = dto.get("purchase") if isinstance(dto, Mapping) else None
    passenger = dto.get("passenger") if isinstance(dto, Mapping) else None
    route = dto.get("route") if isinstance(dto, Mapping) else None
    segment = dto.get("segment") if isinstance(dto, Mapping) else None
    tour = dto.get("tour") if isinstance(dto, Mapping) else None

    ticket_number = (ticket or {}).get("id")
    seat_number = (ticket or {}).get("seat_number")

    purchase_id = (purchase or {}).get("id")
    purchase_status = (purchase or {}).get("status")
    flags = (purchase or {}).get("flags") or dto.get("payment_status") or {}
    status_value = flags.get("status") or purchase_status
    status_texts = {code: _status_text(code, status_value) for code in EMAIL_LANGS}

    departure = (segment or {}).get("departure") or {}
    arrival = (segment or {}).get("arrival") or {}

    context = {
        "langs": EMAIL_LANGS,
        "customer_name": ((purchase or {}).get("customer") or {}).get("name")
        or (passenger or {}).get("name"),
        "ticket_number": ticket_number,
        "purchase_id": purchase_id,
        "seat_number": seat_number,
        "route_name": (route or {}).get("name"),
        "tour_date": _format_date((tour or {}).get("date")),
        "departure_name": departure.get("name"),
        "departure_time": departure.get("time"),
        "arrival_name": arrival.get("name"),
        "arrival_time": arrival.get("time"),
        "status_texts": status_texts,
        "is_paid": bool(flags.get("is_paid")),
        "deep_link": deep_link,
    }

    html = template.render(**context)
    subject = _TICKET_SUBJECT.format(ticket=ticket_number or purchase_id or "")
    return subject, html


def _load_smtp_settings() -> Tuple[str, int, str | None, str | None, str, str | None]:
    """Read SMTP configuration from the environment.

    Raises ``EmailConfigurationError`` when a required variable is missing.
    """
    host = _get_env("SMTP_HOST")
    port_raw = _get_env("SMTP_PORT")
    username = _get_env("SMTP_USERNAME", required=False)
    password = _get_env("SMTP_PASSWORD", required=False)
    from_email = _get_env("SMTP_FROM")
    from_name = _get_env("SMTP_FROM_NAME", required=False)
    port = int(port_raw) if port_raw else 587
    return host, port, username, password, from_email, from_name


def _dispatch_message(
    message: EmailMessage,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    to: str,
) -> None:
    """Open an SMTP connection and send an already-built message (best effort)."""
    context = ssl.create_default_context()
    use_ssl = port == 465

    if use_ssl:
        smtp_cls = smtplib.SMTP_SSL
        smtp_kwargs = {"context": context}
    else:
        smtp_cls = smtplib.SMTP
        smtp_kwargs = {}

    try:
        with smtp_cls(host, port, timeout=30, **smtp_kwargs) as server:
            if not use_ssl:
                server.starttls(context=context)
            if username and password:
                server.login(username, password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Failed to send email to %s: %s", to, exc)


def send_ticket_email(
    to: str,
    subject: str,
    html_body: str,
    pdf_bytes: bytes | None,
) -> None:
    """Send a ticket email with the provided HTML body and PDF attachment."""

    try:
        host, port, username, password, from_email, from_name = _load_smtp_settings()
    except EmailConfigurationError:
        logger.info("Skipping ticket email delivery because SMTP is not configured")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    message["To"] = to
    message.set_content(
        "This email requires an HTML-compatible client to display the ticket."
    )
    message.add_alternative(html_body, subtype="html")

    if pdf_bytes:
        filename = "ticket.pdf"
        if subject:
            safe_subject = subject.replace(" ", "-")
            filename = f"{safe_subject}.pdf"
        message.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=filename,
        )

    _dispatch_message(message, host, port, username, password, to)


def render_receipt_email(
    *,
    purchase_id: Any,
    fiscal_code: Any,
    receipt_url: str | None,
    customer_name: str | None = None,
    amount_text: str | None = None,
    lang: str | None = None,
) -> Tuple[str, str]:
    """Render the multilingual fiscal-receipt email subject and HTML body.

    ``lang`` is accepted for backwards compatibility but the rendered message
    always contains every language in :data:`EMAIL_LANGS`.
    """

    template = _ENV.get_template("receipt.html")

    context = {
        "langs": EMAIL_LANGS,
        "customer_name": customer_name,
        "purchase_id": purchase_id,
        "fiscal_code": fiscal_code,
        "receipt_url": receipt_url,
        "amount_text": amount_text,
    }

    html = template.render(**context)
    subject = _RECEIPT_SUBJECT.format(purchase=purchase_id or "")
    return subject, html


def send_receipt_email(
    to: str,
    subject: str,
    html_body: str,
    png_bytes: bytes | None,
) -> None:
    """Send a fiscal-receipt email with the receipt PNG attached."""

    try:
        host, port, username, password, from_email, from_name = _load_smtp_settings()
    except EmailConfigurationError:
        logger.info("Skipping receipt email delivery because SMTP is not configured")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    message["To"] = to
    message.set_content(
        "This email requires an HTML-compatible client to display the fiscal receipt."
    )
    message.add_alternative(html_body, subtype="html")

    if png_bytes:
        message.add_attachment(
            png_bytes,
            maintype="image",
            subtype="png",
            filename="receipt.png",
        )

    _dispatch_message(message, host, port, username, password, to)


def send_otp_email(to: str, code: str, lang: str | None = None) -> None:
    """Send a lightweight OTP message to the passenger email."""

    lang_value = _resolve_lang(lang)
    subject_templates = {
        "bg": "Код за потвърждение: {code}",
        "en": "Verification code: {code}",
        "ua": "Код підтвердження: {code}",
    }
    body_templates = {
        "bg": "Вашият код за потвърждение е {code}.",
        "en": "Your confirmation code is {code}.",
        "ua": "Ваш код підтвердження: {code}.",
    }

    subject_template = subject_templates.get(lang_value) or subject_templates[DEFAULT_EMAIL_LANG]
    body_template = body_templates.get(lang_value) or body_templates[DEFAULT_EMAIL_LANG]

    try:
        host = _get_env("SMTP_HOST")
        port_raw = _get_env("SMTP_PORT")
        username = _get_env("SMTP_USERNAME", required=False)
        password = _get_env("SMTP_PASSWORD", required=False)
        from_email = _get_env("SMTP_FROM")
        from_name = _get_env("SMTP_FROM_NAME", required=False)
    except EmailConfigurationError:
        logger.info("Skipping OTP email delivery because SMTP is not configured")
        return

    port = int(port_raw) if port_raw else 587
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=context)
        if username and password:
            server.login(username, password)

        message = EmailMessage()
        message["Subject"] = subject_template.format(code=code)
        message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
        message["To"] = to
        message.set_content(body_template.format(code=code))
        server.send_message(message)


__all__ = [
    "EmailConfigurationError",
    "render_ticket_email",
    "send_ticket_email",
    "render_receipt_email",
    "send_receipt_email",
    "send_otp_email",
]
