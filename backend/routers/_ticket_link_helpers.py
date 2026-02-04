"""Shared utilities for issuing ticket deep links."""

from __future__ import annotations

import logging
import os
from datetime import date as date_cls, datetime as dt_cls, time as time_cls, timezone
from typing import Any, Dict, List, Mapping, Sequence, TypedDict, cast
from typing import NotRequired, Required

from fastapi import HTTPException

from ..services import ticket_links
from ..services.link_sessions import get_or_create_view_session
from ..services.ticket_dto import get_ticket_dto
from ..database import get_connection

logger = logging.getLogger(__name__)

DEFAULT_TICKET_LANG = "bg"
DEFAULT_TICKET_SCOPES = (
    "view",
    "download",
    "pay",
    "cancel",
    "edit",
    "seat",
    "reschedule",
)


class TicketIssueSpec(TypedDict):
    """Parameters required to issue a ticket link."""

    ticket_id: int
    purchase_id: int | None
    departure_dt: dt_cls


class TicketStopSummary(TypedDict, total=False):
    """Minimal information about a stop shown alongside the ticket."""

    id: NotRequired[int]
    name: NotRequired[str | None]
    time: NotRequired[str | None]
    description: NotRequired[str | None]
    location: NotRequired[str | None]


class TicketLinkResult(TypedDict, total=False):
    """Structure returned for issued ticket links."""

    ticket_id: Required[int]
    deep_link: Required[str]
    seat_number: NotRequired[int | None]
    departure: NotRequired[TicketStopSummary | None]
    arrival: NotRequired[TicketStopSummary | None]
    trip_date: NotRequired[str | None]
    trip_date_text: NotRequired[str | None]
    route_name: NotRequired[str | None]
    route_label: NotRequired[str | None]
    duration_minutes: NotRequired[int | None]
    duration_text: NotRequired[str | None]


def _normalize_date(value: Any) -> date_cls:
    if isinstance(value, date_cls):
        return value
    if isinstance(value, dt_cls):
        return value.date()
    if isinstance(value, str):
        try:
            return dt_cls.fromisoformat(value).date()
        except ValueError:
            try:
                return dt_cls.strptime(value, "%Y-%m-%d").date()
            except ValueError as exc:  # pragma: no cover - defensive
                raise ValueError("Invalid date value") from exc
    raise ValueError("Unsupported date value")


def _normalize_time(value: Any) -> time_cls:
    if value is None:
        return time_cls(0, 0)
    if isinstance(value, time_cls):
        return value
    if isinstance(value, dt_cls):
        return value.time()
    if isinstance(value, str):
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return dt_cls.strptime(value, fmt).time()
            except ValueError:
                continue
    return time_cls(0, 0)


def combine_departure_datetime(tour_date: Any, departure_time: Any) -> dt_cls:
    """Combine tour date and stop departure time into an aware datetime."""

    date_value = _normalize_date(tour_date)
    time_value = _normalize_time(departure_time)
    combined = dt_cls.combine(date_value, time_value)
    if combined.tzinfo is None:
        return combined.replace(tzinfo=timezone.utc)
    return combined.astimezone(timezone.utc)


def build_deep_link(opaque: str, *, base_url: str | None = None) -> str:
    """Construct a deep link URL for a ticket session."""

    configured = base_url or resolve_ticket_link_base_url()
    if not configured:
        raise ValueError("Ticket link base URL is required to build ticket links")
    configured = configured.rstrip("/")
    return f"{configured}/q/{opaque}"


def resolve_ticket_link_base_url() -> str | None:
    """Resolve the base URL for ticket deep links."""

    configured = os.getenv("CLIENT_FRONTEND_ORIGIN")
    if configured:
        return configured
    configured = os.getenv("TICKET_LINK_BASE_URL")
    if configured:
        return configured
    return os.getenv("APP_PUBLIC_URL")


def issue_ticket_links(
    specs: Sequence[TicketIssueSpec],
    lang: str | None,
    *,
    conn=None,
) -> List[TicketLinkResult]:
    """Issue ticket links for provided specs and return deep-link payloads."""

    if not specs:
        return []

    lang_value = (lang or DEFAULT_TICKET_LANG).lower()
    results: List[TicketLinkResult] = []
    base_url = resolve_ticket_link_base_url()
    if not base_url:
        raise HTTPException(500, "Ticket link base URL is required to build ticket links")

    for spec in specs:
        try:
            opaque, _expires_at = get_or_create_view_session(
                spec["ticket_id"],
                purchase_id=spec["purchase_id"],
                lang=lang_value,
                departure_dt=spec["departure_dt"],
                scopes=DEFAULT_TICKET_SCOPES,
                conn=conn,
            )
        except ticket_links.TicketLinkError as exc:
            logger.exception(
                "Failed to issue ticket link for ticket %s", spec["ticket_id"]
            )
            raise HTTPException(500, "Failed to issue ticket link") from exc
        except Exception as exc:  # pragma: no cover - unexpected failure
            logger.exception(
                "Unexpected error while issuing ticket link for ticket %s",
                spec["ticket_id"],
            )
            raise HTTPException(500, "Failed to issue ticket link") from exc

        deep_link = build_deep_link(opaque, base_url=base_url)
        logger.info(
            "Issued ticket link for ticket %s (purchase %s): %s",
            spec["ticket_id"],
            spec["purchase_id"],
            opaque,
        )

        results.append(
            cast(
                TicketLinkResult,
                {
                    "ticket_id": spec["ticket_id"],
                    "deep_link": deep_link,
                },
            )
        )

    return results


def _format_trip_date(raw: str | None) -> tuple[str | None, str | None]:
    """Return both ISO and human-readable representations for the trip date."""

    if not raw:
        return None, None
    try:
        parsed = date_cls.fromisoformat(raw)
    except ValueError:
        return raw, raw
    return raw, parsed.strftime("%d.%m.%Y")


def _humanize_duration(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    hours, mins = divmod(minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}\u00a0ч")
    if mins:
        parts.append(f"{mins}\u00a0мин")
    if not parts:
        parts.append("0\u00a0мин")
    return " ".join(parts)


def _compose_stop_summary(
    segment_stop: Mapping[str, Any] | None,
    stop_details: Mapping[str, Any] | None,
) -> TicketStopSummary | None:
    if not segment_stop and not stop_details:
        return None

    merged: Dict[str, Any] = {}
    if stop_details:
        merged.update(stop_details)
    if segment_stop:
        merged.update(segment_stop)

    summary: TicketStopSummary = {}
    stop_id = merged.get("id")
    if stop_id is not None:
        summary["id"] = stop_id

    name = merged.get("name")
    if name:
        summary["name"] = name

    time_value = (
        merged.get("time")
        or merged.get("departure_time")
        or merged.get("arrival_time")
    )
    if time_value:
        summary["time"] = str(time_value)

    description = merged.get("description")
    if description:
        summary["description"] = description

    location = merged.get("location")
    if location:
        summary["location"] = location

    return summary


def _ticket_details_from_dto(dto: Mapping[str, Any]) -> Dict[str, Any]:
    ticket_info = dto.get("ticket") or {}
    route = dto.get("route") or {}
    segment = dto.get("segment") or {}
    tour = dto.get("tour") or {}

    stops = {
        stop.get("id"): stop
        for stop in (route.get("stops") or [])
        if isinstance(stop, Mapping)
    }

    departure_seg = segment.get("departure") if isinstance(segment, Mapping) else None
    arrival_seg = segment.get("arrival") if isinstance(segment, Mapping) else None

    departure_summary = _compose_stop_summary(
        departure_seg if isinstance(departure_seg, Mapping) else None,
        stops.get((departure_seg or {}).get("id")) if isinstance(departure_seg, Mapping) else None,
    )
    arrival_summary = _compose_stop_summary(
        arrival_seg if isinstance(arrival_seg, Mapping) else None,
        stops.get((arrival_seg or {}).get("id")) if isinstance(arrival_seg, Mapping) else None,
    )

    trip_raw, trip_text = _format_trip_date(
        tour.get("date") if isinstance(tour, Mapping) else None
    )
    duration_minutes = segment.get("duration_minutes") if isinstance(segment, Mapping) else None

    dep_name = (
        departure_seg.get("name")
        if isinstance(departure_seg, Mapping)
        else None
    )
    arr_name = (
        arrival_seg.get("name")
        if isinstance(arrival_seg, Mapping)
        else None
    )
    route_label = None
    if dep_name or arr_name:
        route_label = f"{dep_name or ''} → {arr_name or ''}".strip()

    details: Dict[str, Any] = {
        "seat_number": ticket_info.get("seat_number"),
        "departure": departure_summary,
        "arrival": arrival_summary,
        "trip_date": trip_raw,
        "trip_date_text": trip_text,
        "route_name": route.get("name") if isinstance(route, Mapping) else None,
        "route_label": route_label,
        "duration_minutes": duration_minutes,
        "duration_text": _humanize_duration(duration_minutes),
    }

    return {k: v for k, v in details.items() if v is not None}


def enrich_ticket_link_results(
    tickets: Sequence[TicketLinkResult],
    lang: str | None,
    *,
    conn=None,
) -> List[TicketLinkResult]:
    """Attach structured journey information to ticket payloads."""

    if not tickets:
        return list(tickets)

    lang_value = (lang or DEFAULT_TICKET_LANG).lower()
    connection = conn
    owns_conn = False
    if connection is None:
        connection = get_connection()
        owns_conn = True

    try:
        enriched: List[TicketLinkResult] = []
        for ticket in tickets:
            if not isinstance(ticket, dict):
                enriched.append(ticket)
                continue
            ticket_id = ticket.get("ticket_id")
            if ticket_id is None:
                enriched.append(ticket)
                continue
            try:
                dto = get_ticket_dto(ticket_id, lang_value, connection)
            except ValueError:
                enriched.append(ticket)
                continue
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to enrich ticket %s", ticket_id)
                enriched.append(ticket)
                continue

            details = _ticket_details_from_dto(dto)
            ticket.update(details)
            enriched.append(ticket)
        return enriched
    finally:
        if owns_conn and connection is not None:
            connection.close()


__all__ = [
    "TicketIssueSpec",
    "TicketLinkResult",
    "combine_departure_datetime",
    "build_deep_link",
    "issue_ticket_links",
    "enrich_ticket_link_results",
]
