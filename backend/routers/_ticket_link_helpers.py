"""Shared utilities for issuing ticket deep links."""

from __future__ import annotations

import logging
import os
from datetime import date as date_cls, datetime as dt_cls, time as time_cls, timezone
from typing import Any, List, Sequence, TypedDict, cast

from fastapi import HTTPException

from ..services import ticket_links
from ..services.link_sessions import get_or_create_view_session

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


class TicketLinkResult(TypedDict):
    """Structure returned for issued ticket links."""

    ticket_id: int
    deep_link: str


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

    configured = base_url or os.getenv("TICKET_LINK_BASE_URL")
    if not configured:
        configured = os.getenv("APP_PUBLIC_URL", "https://t.example.com")
    configured = configured.rstrip("/")
    return f"{configured}/q/{opaque}"


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

        deep_link = build_deep_link(opaque)
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


__all__ = [
    "TicketIssueSpec",
    "TicketLinkResult",
    "combine_departure_datetime",
    "build_deep_link",
    "issue_ticket_links",
]
