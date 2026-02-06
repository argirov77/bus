"""Render ticket PDFs using a HTML template and WeasyPrint."""

from __future__ import annotations

import base64
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import qrcode
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

_DEFAULT_I18N: Dict[str, Any] = {
    "lang": "ru",
    "brand_name": "МАКСИМОВ ТУРС",
    "ticket_label": "Электронный билет",
    "ticket_number_label": "№ билета",
    "order_label": "Заказ",
    "trip_date_label": "Дата поездки",
    "seat_label": "Место",
    "baggage_label": "Багаж",
    "baggage_base_count": 1,
    "baggage_piece_word": "место багажа",
    "baggage_piece_word_plural": "мест багажа",
    "hand_luggage": "ручная кладь",
    "passenger_label": "Пассажир",
    "passenger_section": "Пассажир",
    "full_name_label": "ФИО",
    "phone_label": "Телефон",
    "route_label": "Маршрут",
    "price_label": "Стоимость",
    "manage_online_button": "Управлять поездкой",
    "manage_online_hint": "Перейдите по ссылке или отсканируйте QR-код, чтобы оплатить, отменить или перенести свою поездку.",
    "trip_section": "Поездка",
    "datetime_label": "Дата/время",
    "address_label": "Адрес",
    "open_map": "Открыть карту",
    "view_exact_location": "Посмотреть точное место",
    "duration_label": "Длительность",
    "approximate_symbol": "~",
    "hours_suffix": "ч.",
    "minutes_suffix": "мин.",
    "payment_section": "Оплата",
    "status_label": "Статус",
    "method_label": "Метод",
    "amount_label": "Сумма",
    "status_paid": "Оплачен",
    "status_reserved": "Зарезервирован",
    "status_cancelled": "Отменён",
    "status_refunded": "Возврат",
    "status_pending": "Ожидает оплаты",
    "status_unknown": "Статус неизвестен",
    "value_not_available": "—",
    "footer_note": "Полис страхования ответственности перевозчика действует на протяжении всего рейса.",
    "footer_brand": "Since 1992 · Максимов Турс",
    "ticket_page_title": "Электронный билет №{number} — {brand}",
    "departure_label": "Отправление",
    "arrival_label": "Прибытие",
    "currency_code": "UAH",
    "qr_hint": "Сканируйте QR-код, чтобы оплатить, отменить или перенести поездку.",
    "qr_unavailable": "QR-код недоступен",
    "paid_label": "ОПЛАЧЕН",
    "unpaid_label": "НЕ ОПЛАЧЕН",
    "ticket_short_label": "TKT",
    "order_short_label": "ORD",
    "company_phone": "+359 88 123 4567",
    "company_email": "support@maximov.tours",
    "company_web": "https://www.maximov.tours",
}

_STATUS_TO_I18N_KEY = {
    "paid": "status_paid",
    "refunded": "status_refunded",
    "reserved": "status_reserved",
    "pending": "status_pending",
    "awaiting": "status_pending",
    "cancelled": "status_cancelled",
    "canceled": "status_cancelled",
}

_SUCCESS_STATUSES = {"paid", "refunded"}


def _merge_i18n(overrides: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    base = dict(_DEFAULT_I18N)
    if overrides:
        base.update(overrides)
    return base


def _format_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed: Optional[date]
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        try:
            parsed_dt = datetime.fromisoformat(value)
        except ValueError:
            return value
        else:
            parsed = parsed_dt.date()
    return parsed.strftime("%d.%m.%Y")


def _format_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        # Keep HH:MM if already formatted
        datetime.strptime(value, "%H:%M")
        return value
    except ValueError:
        try:
            parsed_dt = datetime.fromisoformat(value)
        except ValueError:
            return value
        return parsed_dt.strftime("%H:%M")


def _format_currency(amount: Optional[Any], currency: str) -> Optional[str]:
    if amount is None:
        return None
    try:
        value = Decimal(str(amount))
    except Exception:  # pragma: no cover - defensive fallback
        return None
    formatted = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    currency = currency.strip()
    if currency:
        return f"{formatted}\u00a0{currency}"
    return formatted


def _format_duration(minutes: Optional[int], fallback: Optional[str], i18n: Mapping[str, Any]) -> Optional[str]:
    if minutes is None:
        return fallback
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}\u00a0{i18n['hours_suffix']}")
    if mins:
        parts.append(f"{mins}\u00a0{i18n['minutes_suffix']}")
    if not parts:
        parts.append(f"0\u00a0{i18n['minutes_suffix']}")
    prefix = i18n.get("approximate_symbol")
    if prefix:
        return f"{prefix} {' '.join(parts)}"
    return " ".join(parts)


def _generate_qr_data_uri(data: Optional[str]) -> Optional[str]:
    if not data:
        return None
    qr = qrcode.QRCode(version=None, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _status_label(status: Optional[str], i18n: Mapping[str, Any]) -> str:
    if not status:
        return i18n["status_unknown"]
    key = _STATUS_TO_I18N_KEY.get(status.lower())
    if key and key in i18n:
        return i18n[key]
    return status


def _status_css_class(status: Optional[str]) -> str:
    if status and status.lower() in _SUCCESS_STATUSES:
        return "ok"
    return ""


def _status_color(status: Optional[str]) -> Optional[str]:
    if status and status.lower() in _SUCCESS_STATUSES:
        return "var(--success)"
    return None


def _format_baggage(extra: Optional[Any], i18n: Mapping[str, Any]) -> Optional[str]:
    hand = i18n.get("hand_luggage")
    base_count = i18n.get("baggage_base_count", 0) or 0
    try:
        base_int = int(base_count)
    except (TypeError, ValueError):
        base_int = 0
    try:
        extra_int = int(extra) if extra is not None else None
    except (TypeError, ValueError):
        extra_int = None
    total = base_int
    if extra_int is not None and extra_int > 0:
        total += extra_int
    if total <= 0:
        return hand
    if total == 1:
        piece = i18n.get("baggage_piece_word", "место багажа")
    else:
        piece = i18n.get("baggage_piece_word_plural", "мест багажа")
    if hand:
        return f"{total}\u00a0{piece} + {hand}"
    return f"{total}\u00a0{piece}"


def _build_passenger(dto: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    passenger = dto.get("passenger") or {}
    purchase = dto.get("purchase") or {}
    customer = purchase.get("customer") or {}
    return {
        "name": passenger.get("name") or customer.get("name") or "",
        "email": customer.get("email"),
        "phone": customer.get("phone"),
    }


def _build_route_context(dto: Mapping[str, Any], i18n: Mapping[str, Any]) -> Dict[str, Any]:
    segment = dto.get("segment") or {}
    route = dto.get("route") or {}
    stops = {stop.get("id"): stop for stop in route.get("stops") or []}

    departure = segment.get("departure") or {}
    arrival = segment.get("arrival") or {}

    dep_stop = stops.get(departure.get("id"))
    arr_stop = stops.get(arrival.get("id"))

    dep_name = departure.get("name") or (dep_stop or {}).get("name") or ""
    arr_name = arrival.get("name") or (arr_stop or {}).get("name") or ""

    trip_date = _format_date((dto.get("tour") or {}).get("date"))

    departure_context = {
        "title": f"{i18n['departure_label']} — {dep_name}" if dep_name else i18n["departure_label"],
        "date": trip_date,
        "time": _format_time(departure.get("time")),
        "address": (dep_stop or {}).get("description"),
        "map_url": (dep_stop or {}).get("location"),
    }

    arrival_context = {
        "title": f"{i18n['arrival_label']} — {arr_name}" if arr_name else i18n["arrival_label"],
        "date": trip_date,
        "time": _format_time(arrival.get("time")),
        "address": (arr_stop or {}).get("description"),
        "map_url": (arr_stop or {}).get("location"),
    }

    duration_text = _format_duration(
        segment.get("duration_minutes"),
        segment.get("duration_human"),
        i18n,
    )

    return {
        "from_city": dep_name,
        "to_city": arr_name,
        "label": f"{dep_name} → {arr_name}".strip(" →"),
        "departure": departure_context,
        "arrival": arrival_context,
        "timeline": {"duration_text": duration_text},
        "trip_date": trip_date,
    }


def _select_currency(dto: Mapping[str, Any], i18n: Mapping[str, Any]) -> str:
    pricing = dto.get("pricing") or {}
    currency = (
        pricing.get("currency_code")
        or pricing.get("currency")
        or i18n.get("currency_code")
        or ""
    )
    return currency


def render_ticket_pdf(dto: Mapping[str, Any], deep_link: Optional[str]) -> bytes:
    """Render a ticket PDF from a DTO and a deep link."""

    if not isinstance(dto, Mapping):
        raise TypeError("dto must be a mapping")

    i18n_overrides = dto.get("i18n") if isinstance(dto, Mapping) else None
    i18n = _merge_i18n(i18n_overrides if isinstance(i18n_overrides, Mapping) else None)

    route_ctx = _build_route_context(dto, i18n)
    passenger = _build_passenger(dto)

    ticket_info = dto.get("ticket") or {}
    purchase = dto.get("purchase") or {}
    payment_status = dto.get("payment_status") or purchase.get("flags") or {}

    status_value = payment_status.get("status") or purchase.get("status")
    status_text = _status_label(status_value, i18n)
    status_css = _status_css_class(status_value)

    baggage_text = _format_baggage(ticket_info.get("extra_baggage"), i18n)

    currency = _select_currency(dto, i18n)
    price_amount = (
        purchase.get("amount_due")
        if purchase.get("amount_due") is not None
        else (dto.get("pricing") or {}).get("price")
    )
    price_text = _format_currency(price_amount, currency) if price_amount is not None else None

    order_number = purchase.get("id")

    page_title_template = i18n.get("ticket_page_title")
    ticket_number = ticket_info.get("id")
    if page_title_template and ticket_number is not None:
        page_title = page_title_template.format(number=ticket_number, brand=i18n.get("brand_name", ""))
    else:
        page_title = i18n.get("ticket_label", "Ticket")

    qr_data_uri = _generate_qr_data_uri(deep_link)

    template = _ENV.get_template("ticket.html")
    html = template.render(
        page_title=page_title,
        i18n=i18n,
        route={
            "from_city": route_ctx["from_city"],
            "to_city": route_ctx["to_city"],
            "label": route_ctx["label"],
        },
        ticket={
            "number": ticket_number,
            "order_number": order_number,
            "trip_date": route_ctx["trip_date"],
            "seat_number": ticket_info.get("seat_number"),
            "baggage_text": baggage_text,
            "price_text": price_text,
        },
        status_chip={
            "text": status_text,
            "css_class": status_css,
        },
        passenger=passenger,
        payment={
            "status_text": status_text,
            "status_color": _status_color(status_value),
            "method_text": purchase.get("payment_method") or i18n["value_not_available"],
            "amount_text": price_text or i18n["value_not_available"],
        },
        timeline={"duration_text": route_ctx["timeline"]["duration_text"]},
        departure=route_ctx["departure"],
        arrival=route_ctx["arrival"],
        deep_link=deep_link,
        qr_data_uri=qr_data_uri,
    )

    base_url = str(_TEMPLATES_DIR.parent.parent.parent)
    pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()
    return pdf_bytes
