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

_SUBJECT_TEMPLATES = {
    "bg": "Вашият билет №{ticket}",
    "en": "Your ticket #{ticket}",
    "ua": "Ваш квиток №{ticket}",
}

_STATUS_LABELS = {
    "bg": {
        "paid": "потвърден",
        "reserved": "резервиран",
        "refunded": "възстановен",
        "cancelled": "отменен",
        "canceled": "отменен",
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


def _resolve_subject(lang: str, ticket_number: Any, purchase_id: Any) -> str:
    template = _SUBJECT_TEMPLATES.get(lang) or _SUBJECT_TEMPLATES[DEFAULT_EMAIL_LANG]
    ticket_value = ticket_number or purchase_id or ""
    purchase_value = purchase_id or ticket_value
    return template.format(ticket=ticket_value, purchase=purchase_value)


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


def _load_template(lang: str):
    template_name = f"ticket_{lang}.html"
    if not (_TEMPLATES_DIR / template_name).exists():
        template_name = f"ticket_{DEFAULT_EMAIL_LANG}.html"
    return _ENV.get_template(template_name)


def render_ticket_email(
    dto: Mapping[str, Any],
    deep_link: str,
    lang: str | None,
) -> Tuple[str, str]:
    """Render ticket email subject and HTML body for the given DTO."""

    lang_value = _resolve_lang(lang)
    template = _load_template(lang_value)

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
    status_text = _status_text(lang_value, status_value)

    departure = (segment or {}).get("departure") or {}
    arrival = (segment or {}).get("arrival") or {}

    context = {
        "lang": lang_value,
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
        "status_text": status_text,
        "is_paid": bool(flags.get("is_paid")),
        "deep_link": deep_link,
    }

    html = template.render(**context)
    subject = _resolve_subject(lang_value, ticket_number, purchase_id)
    return subject, html


def send_ticket_email(
    to: str,
    subject: str,
    html_body: str,
    pdf_bytes: bytes | None,
) -> None:
    """Send a ticket email with the provided HTML body and PDF attachment."""

    try:
        host = _get_env("SMTP_HOST")
        port_raw = _get_env("SMTP_PORT")
        username = _get_env("SMTP_USERNAME", required=False)
        password = _get_env("SMTP_PASSWORD", required=False)
        from_email = _get_env("SMTP_FROM")
        from_name = _get_env("SMTP_FROM_NAME", required=False)
    except EmailConfigurationError:
        logger.info("Skipping ticket email delivery because SMTP is not configured")
        return

    port = int(port_raw) if port_raw else 587

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

    context = ssl.create_default_context()
    use_ssl = port == 465

    if use_ssl:
        smtp_cls = smtplib.SMTP_SSL
        smtp_kwargs = {"context": context}
    else:
        smtp_cls = smtplib.SMTP
        smtp_kwargs = {}

    with smtp_cls(host, port, timeout=30, **smtp_kwargs) as server:
        if not use_ssl:
            server.starttls(context=context)
        if username and password:
            server.login(username, password)
        server.send_message(message)


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
    "send_otp_email",
]
