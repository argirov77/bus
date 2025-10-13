"""Ticket DTO aggregator.

The application renders ticket details in several places (PDF tickets,
customer e-mails, admin tools).  Each of those entry points previously had
to issue its own SQL queries which was both error prone and hard to extend.
This module centralises the data gathering logic in a single helper function
so the callers can simply request a ready-to-use dictionary.

The :func:`get_ticket_dto` helper pulls together information about the ticket
itself, the passenger, purchase/payment metadata, the tour (including the
route and localisation-aware stop titles) and pricing details.  Additionally
it calculates convenience fields such as the segment duration and a
structured description of the journey portion covered by the ticket.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, time
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from ..models import BookingTermsEnum


# Mapping between supported languages and the column that stores a translated
# stop name.  Unknown languages fall back to ``stop_name`` automatically.
_LANG_TO_STOP_COLUMN: Dict[str, str] = {
    "bg": "stop_bg",
    "en": "stop_en",
    "ua": "stop_ua",
}


_STOP_COLUMN_INDEX = {
    "stop_name": 4,
    "stop_en": 5,
    "stop_bg": 6,
    "stop_ua": 7,
}


def _format_time(value: Optional[time]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%H:%M")


def _format_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _choose_stop_name(row: Sequence, lang: str) -> str:
    lang_key = (lang or "").lower()
    column = _LANG_TO_STOP_COLUMN.get(lang_key)
    if column:
        idx = _STOP_COLUMN_INDEX[column]
        localized = row[idx]
        if localized:
            return localized
    # fall back to the default column
    return row[_STOP_COLUMN_INDEX["stop_name"]]


def _humanize_duration(minutes: Optional[int]) -> Optional[str]:
    if minutes is None:
        return None
    hours, mins = divmod(minutes, 60)
    parts: List[str] = []
    if hours:
        parts.append(f"{hours}h")
    if mins or not parts:
        parts.append(f"{mins}m")
    return " ".join(parts)


def _booking_rules(terms: BookingTermsEnum) -> Dict[str, Optional[object]]:
    """Return a structured description for the booking terms."""

    if terms == BookingTermsEnum.EXPIRE_AFTER_48H:
        return {
            "code": terms.name,
            "kind": "expires_after_booking",
            "expires_in_hours": 48,
            "description": "Reservation expires 48 hours after booking if not paid.",
        }
    if terms == BookingTermsEnum.EXPIRE_BEFORE_48H:
        return {
            "code": terms.name,
            "kind": "expires_before_departure",
            "expires_in_hours": 48,
            "description": "Reservation must be paid at least 48 hours before departure.",
        }
    if terms == BookingTermsEnum.NO_EXPIRY:
        return {
            "code": terms.name,
            "kind": "pay_on_board",
            "expires_in_hours": None,
            "description": "Reservation remains valid until departure; payment on board.",
        }
    if terms == BookingTermsEnum.NO_BOOKING:
        return {
            "code": terms.name,
            "kind": "purchase_only",
            "expires_in_hours": None,
            "description": "Booking is not available; tickets must be purchased immediately.",
        }
    # Fallback, should not normally happen but keeps the function future-proof.
    return {
        "code": terms.name,
        "kind": "unknown",
        "expires_in_hours": None,
        "description": None,
    }


def _payment_flags(status: Optional[str]) -> Dict[str, object]:
    status_value = status or ""
    return {
        "status": status_value,
        "is_reserved": status_value == "reserved",
        "is_paid": status_value in {"paid", "refunded"},
        "is_cancelled": status_value == "cancelled",
        "is_refunded": status_value == "refunded",
        "is_active": status_value in {"reserved", "paid"},
    }


def _build_stop(row: Sequence, lang: str) -> Dict[str, object]:
    stop_id, order, arrival_time, departure_time, *_rest = row
    return {
        "id": stop_id,
        "order": order,
        "name": _choose_stop_name(row, lang),
        "arrival_time": _format_time(arrival_time),
        "departure_time": _format_time(departure_time),
        "description": row[8],
        "location": row[9],
    }


def _segment_times(
    tour_date: Optional[date],
    departure: Optional[time],
    arrival: Optional[time],
) -> Tuple[Optional[int], Optional[str]]:
    if tour_date is None or departure is None or arrival is None:
        return None, None
    dep_dt = datetime.combine(tour_date, departure)
    arr_dt = datetime.combine(tour_date, arrival)
    if arr_dt <= dep_dt:
        arr_dt += timedelta(days=1)
    delta = arr_dt - dep_dt
    minutes = int(delta.total_seconds() // 60)
    return minutes, _humanize_duration(minutes)


def get_ticket_dto(ticket_id: int, lang: str, conn) -> Dict[str, object]:
    """Aggregate a comprehensive DTO for the specified ticket.

    Parameters
    ----------
    ticket_id:
        Identifier of the ticket to load.
    lang:
        Language code used when choosing the stop title (``bg``, ``en``, ``ua``)
        with graceful fallback to the default name.
    conn:
        Database connection (psycopg2 connection or a compatible object).
    """

    base_query = """
        SELECT
            t.id,
            t.seat_id,
            s.seat_num,
            t.passenger_id,
            pa.name,
            t.departure_stop_id,
            t.arrival_stop_id,
            t.extra_baggage,
            t.tour_id,
            tr.date,
            tr.route_id,
            r.name,
            tr.pricelist_id,
            tr.layout_variant,
            tr.booking_terms,
            t.purchase_id,
            pu.customer_name,
            pu.customer_email,
            pu.customer_phone,
            pu.amount_due,
            pu.deadline,
            pu.status,
            pu.payment_method,
            pu.update_at,
            pr.price,
            pl.currency
        FROM ticket t
        JOIN passenger pa ON pa.id = t.passenger_id
        LEFT JOIN seat s ON s.id = t.seat_id
        LEFT JOIN tour tr ON tr.id = t.tour_id
        LEFT JOIN route r ON r.id = tr.route_id
        LEFT JOIN purchase pu ON pu.id = t.purchase_id
        LEFT JOIN prices pr
            ON pr.pricelist_id = tr.pricelist_id
           AND pr.departure_stop_id = t.departure_stop_id
           AND pr.arrival_stop_id = t.arrival_stop_id
        LEFT JOIN pricelist pl ON pl.id = tr.pricelist_id
        WHERE t.id = %s
    """

    stops_query = """
        SELECT
            rs.stop_id,
            rs."order",
            rs.arrival_time,
            rs.departure_time,
            st.stop_name,
            st.stop_en,
            st.stop_bg,
            st.stop_ua,
            st.description,
            st.location
        FROM routestop rs
        JOIN stop st ON st.id = rs.stop_id
        WHERE rs.route_id = %s
        ORDER BY rs."order"
    """

    cur = conn.cursor()
    try:
        cur.execute(base_query, (ticket_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Ticket {ticket_id} not found")

        (
            _ticket_id,
            seat_id,
            seat_num,
            passenger_id,
            passenger_name,
            departure_stop_id,
            arrival_stop_id,
            extra_baggage,
            tour_id,
            tour_date,
            route_id,
            route_name,
            pricelist_id,
            layout_variant,
            booking_terms_value,
            purchase_id,
            customer_name,
            customer_email,
            customer_phone,
            amount_due,
            deadline,
            purchase_status,
            payment_method,
            updated_at,
            price,
            currency,
        ) = row

        currency = currency or "UAH"

        booking_terms_enum = BookingTermsEnum(booking_terms_value)

        cur.execute(stops_query, (route_id,))
        stops_rows = cur.fetchall()
    finally:
        cur.close()

    stops: List[Dict[str, object]] = []
    stop_times: Dict[int, Dict[str, Optional[time]]] = {}
    for stop_row in stops_rows:
        stop = _build_stop(stop_row, lang)
        stops.append(stop)
        stop_times[int(stop_row[0])] = {
            "arrival": stop_row[2],
            "departure": stop_row[3],
        }

    departure_stop = next((s for s in stops if s["id"] == departure_stop_id), None)
    arrival_stop = next((s for s in stops if s["id"] == arrival_stop_id), None)

    dep_time_obj = stop_times.get(departure_stop_id, {}).get("departure") or stop_times.get(
        departure_stop_id, {}
    ).get("arrival")
    arr_time_obj = stop_times.get(arrival_stop_id, {}).get("arrival") or stop_times.get(
        arrival_stop_id, {}
    ).get("departure")

    duration_minutes, duration_label = _segment_times(tour_date, dep_time_obj, arr_time_obj)

    if departure_stop and arrival_stop:
        start_order = departure_stop["order"]
        end_order = arrival_stop["order"]
        between = [
            {
                "id": stop["id"],
                "name": stop["name"],
                "order": stop["order"],
                "arrival_time": stop["arrival_time"],
                "departure_time": stop["departure_time"],
            }
            for stop in stops
            if start_order < stop["order"] < end_order
        ]
    else:
        between = []

    segment = {
        "departure": None if departure_stop is None else {
            "id": departure_stop["id"],
            "name": departure_stop["name"],
            "order": departure_stop["order"],
            "time": departure_stop["departure_time"] or departure_stop["arrival_time"],
        },
        "arrival": None if arrival_stop is None else {
            "id": arrival_stop["id"],
            "name": arrival_stop["name"],
            "order": arrival_stop["order"],
            "time": arrival_stop["arrival_time"] or arrival_stop["departure_time"],
        },
        "intermediate_stops": between,
        "duration_minutes": duration_minutes,
        "duration_human": duration_label,
    }

    purchase_info: Optional[Dict[str, object]]
    payment_details: Optional[Dict[str, object]]
    if purchase_id is not None:
        flags = _payment_flags(purchase_status)
        purchase_info = {
            "id": purchase_id,
            "customer": {
                "name": customer_name,
                "email": customer_email,
                "phone": customer_phone,
            },
            "amount_due": _decimal_to_float(amount_due),
            "deadline": _format_datetime(deadline),
            "payment_method": payment_method,
            "updated_at": _format_datetime(updated_at),
            "status": purchase_status,
            "flags": flags,
        }
        payment_details = flags
    else:
        purchase_info = None
        payment_details = None

    dto = {
        "ticket": {
            "id": ticket_id,
            "seat_id": seat_id,
            "seat_number": seat_num,
            "departure_stop_id": departure_stop_id,
            "arrival_stop_id": arrival_stop_id,
            "extra_baggage": extra_baggage,
        },
        "passenger": {
            "id": passenger_id,
            "name": passenger_name,
        },
        "tour": {
            "id": tour_id,
            "date": tour_date.isoformat() if tour_date else None,
            "layout_variant": layout_variant,
            "pricelist_id": pricelist_id,
            "booking_terms": {
                "value": int(booking_terms_enum),
                "code": booking_terms_enum.name,
            },
        },
        "route": {
            "id": route_id,
            "name": route_name,
            "stops": stops,
        },
        "segment": segment,
        "pricing": {
            "price": _decimal_to_float(price),
            "currency_code": currency,
        },
        "purchase": purchase_info,
        "payment_status": payment_details,
        "booking_rules": _booking_rules(booking_terms_enum),
    }

    return dto

