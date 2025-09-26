import os
import sys
from datetime import date, datetime, time
from decimal import Decimal

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services.ticket_dto import get_ticket_dto


class ScriptedCursor:
    """A minimal cursor that replays predetermined query results."""

    def __init__(self, script):
        self._script = list(script)
        self._current = None
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if not self._script:
            raise AssertionError("No scripted response left for query")
        self._current = self._script.pop(0)

    def fetchone(self):
        if isinstance(self._current, list):
            result = self._current[0] if self._current else None
        else:
            result = self._current
        self._current = None
        return result

    def fetchall(self):
        if self._current is None:
            return []
        if isinstance(self._current, list):
            result = self._current
            self._current = None
            return result
        raise AssertionError("fetchall called for scalar result")

    def close(self):
        pass


class ScriptedConnection:
    def __init__(self, script):
        self._script = script

    def cursor(self):
        return ScriptedCursor(self._script)


def test_ticket_dto_localization_and_duration():
    base_row = (
        1,  # ticket id
        3,  # seat id
        12,  # seat number
        5,  # passenger id
        "Ivan Petrov",  # passenger name
        10,  # departure stop id
        30,  # arrival stop id
        2,  # extra baggage
        100,  # tour id
        date(2024, 5, 1),  # tour date
        7,  # route id
        "Sofia - Varna",  # route name
        9,  # pricelist id
        2,  # layout variant
        1,  # booking terms -> EXPIRE_BEFORE_48H
        50,  # purchase id
        "Alex Buyer",  # customer name
        "alex@example.com",  # customer email
        "+359111111",  # customer phone
        Decimal("45.50"),  # amount due
        datetime(2024, 4, 30, 12, 0),  # deadline
        "reserved",  # status
        "online",  # payment method
        datetime(2024, 4, 25, 9, 30),  # update at
        Decimal("49.90"),  # price
    )

    stops_rows = [
        (
            10,
            1,
            None,
            time(8, 0),
            "Sofia",
            "Sofia EN",
            "София",
            "Софія",
            "Central station",
            "https://example.com/a",
        ),
        (
            20,
            2,
            time(10, 30),
            time(10, 45),
            "Plovdiv",
            "Plovdiv EN",
            "Пловдив",
            "Пловдив",
            "Mid stop",
            None,
        ),
        (
            30,
            3,
            time(13, 30),
            None,
            "Varna",
            "Varna EN",
            "Варна",
            "Варна",
            "Sea station",
            "https://example.com/c",
        ),
    ]

    conn = ScriptedConnection([base_row, stops_rows])

    dto = get_ticket_dto(1, "bg", conn)

    assert dto["ticket"]["seat_number"] == 12
    assert dto["passenger"]["name"] == "Ivan Petrov"
    assert dto["pricing"]["price"] == pytest.approx(49.90)

    # Localised names are taken from ``stop_bg`` when available.
    assert dto["route"]["stops"][0]["name"] == "София"
    assert dto["segment"]["departure"]["name"] == "София"
    assert dto["segment"]["arrival"]["name"] == "Варна"
    assert dto["segment"]["intermediate_stops"][0]["name"] == "Пловдив"

    # Duration is computed from the timetable entries.
    assert dto["segment"]["duration_minutes"] == 330
    assert dto["segment"]["duration_human"] == "5h 30m"

    # Booking rules and payment status are exposed for UI rendering.
    assert dto["booking_rules"]["code"] == "EXPIRE_BEFORE_48H"
    assert dto["purchase"]["flags"]["is_paid"] is False
    assert dto["purchase"]["customer"]["email"] == "alex@example.com"


def test_ticket_dto_without_purchase_and_language_fallback():
    base_row = (
        2,
        6,
        18,
        11,
        "Maria Ivanova",
        101,
        202,
        0,
        300,
        date(2024, 7, 20),
        14,
        "Night Route",
        22,
        1,
        2,  # booking terms -> NO_EXPIRY
        None,  # purchase id
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        Decimal("35.00"),
    )

    stops_rows = [
        (
            101,
            1,
            None,
            time(22, 30),
            "Origin",
            None,
            None,
            None,
            None,
            None,
        ),
        (
            202,
            2,
            time(2, 0),
            None,
            "Destination",
            None,
            None,
            None,
            None,
            None,
        ),
    ]

    conn = ScriptedConnection([base_row, stops_rows])

    dto = get_ticket_dto(2, "de", conn)

    # Unsupported languages fall back to the default stop name column.
    assert dto["route"]["stops"][0]["name"] == "Origin"
    assert dto["segment"]["arrival"]["name"] == "Destination"

    # Purchase section is omitted when the ticket is not linked to a purchase.
    assert dto["purchase"] is None
    assert dto["payment_status"] is None

    # Duration handles overnight trips (arrival time before departure).
    assert dto["segment"]["duration_minutes"] == 210
    assert dto["segment"]["duration_human"] == "3h 30m"
    assert dto["booking_rules"]["code"] == "NO_EXPIRY"


def test_ticket_dto_missing_ticket():
    conn = ScriptedConnection([None])
    with pytest.raises(ValueError):
        get_ticket_dto(999, "en", conn)

