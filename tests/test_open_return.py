import datetime
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# backend.database connects to PostgreSQL at import time; stub it out so these
# unit tests can exercise the pure purchase logic without a live database.
import psycopg2


class _StubCursor:
    def execute(self, *a, **k):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class _StubConn:
    def cursor(self):
        return _StubCursor()

    def commit(self):
        pass

    def close(self):
        pass


psycopg2.connect = lambda *a, **k: _StubConn()

from backend.routers import purchase
from backend.routers.purchase import (
    PurchaseCreate,
    _fare,
    _passenger_multiplier,
    _create_purchase,
)


def test_passenger_multiplier_combinations():
    assert _passenger_multiplier(False, False) == 1.0
    assert _passenger_multiplier(True, False) == 0.95
    assert _passenger_multiplier(False, True) == 0.85
    # Discount and round-trip stack multiplicatively.
    assert _passenger_multiplier(True, True) == 0.95 * 0.85


def test_fare_one_way_and_roundtrip():
    # one adult, one discount, no baggage, one-way
    assert _fare(100, adult_count=1, discount_count=1, baggage_count=0) == 195.0
    # same, round trip: each fare gets x0.85
    assert _fare(100, adult_count=1, discount_count=1, baggage_count=0, roundtrip=True) == round(
        100 * (0.85 + 0.95 * 0.85), 2
    )
    # baggage is NOT discounted by the round-trip multiplier
    assert _fare(100, adult_count=1, discount_count=0, baggage_count=1, roundtrip=True) == round(
        100 * (0.85 + 0.10), 2
    )


class FakeOpenReturnCursor:
    """Minimal cursor that lets _create_purchase run for an open-return purchase."""

    def __init__(self):
        self.queries = []
        self.query = ""
        self.params = None
        self._passenger_seq = 100
        self._ticket_seq = 500

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        self.queries.append((query, params))

    def fetchone(self):
        q = self.query.lower()
        if "select route_id, pricelist_id, date from tour" in q:
            return [1, 1, datetime.date.today()]
        if "select price from prices" in q:
            return [10]
        if "insert into purchase" in q:
            return [1]
        if "insert into passenger" in q:
            self._passenger_seq += 1
            return [self._passenger_seq]
        if "select id, available from seat" in q:
            return [1, "1234"]
        if "insert into ticket" in q:
            self._ticket_seq += 1
            return [self._ticket_seq]
        return [1]

    def fetchall(self):
        q = self.query.lower()
        if "from routestop" in q:
            t = datetime.time(8, 0)
            return [(1, t), (2, t), (3, t), (4, t)]
        return []

    def close(self):
        pass


def _open_return_payload(**overrides):
    base = dict(
        tour_id=1,
        seat_nums=[1],
        passenger_names=["A"],
        passenger_phone="1",
        passenger_email="a@b.com",
        departure_stop_id=1,
        arrival_stop_id=2,
        adult_count=1,
        discount_count=0,
        open_return=True,
    )
    base.update(overrides)
    return PurchaseCreate(**base)


def test_open_return_creates_voucher_and_adds_to_amount(monkeypatch):
    monkeypatch.setattr(purchase, "_record_sql_hint", lambda *a, **k: None)
    cur = FakeOpenReturnCursor()
    data = _open_return_payload()

    purchase_id, amount_due, specs = _create_purchase(cur, data, "reserved")

    # forward fare 10 + open return 10 * 0.85 = 18.5
    assert amount_due == 18.5
    assert len(specs) == 1

    open_inserts = [q for q, p in cur.queries if "insert into open_ticket" in q.lower()]
    assert len(open_inserts) == 1

    # Reverse-direction price lookup uses swapped stops on the same pricelist.
    reverse_lookups = [
        p
        for q, p in cur.queries
        if "select price from prices" in q.lower() and p == (1, 2, 1)
    ]
    assert reverse_lookups, "expected a reverse-direction price lookup (arrival, departure)"


def test_open_return_discount_passenger_price(monkeypatch):
    monkeypatch.setattr(purchase, "_record_sql_hint", lambda *a, **k: None)
    cur = FakeOpenReturnCursor()
    data = _open_return_payload(adult_count=0, discount_count=1)

    _purchase_id, amount_due, _specs = _create_purchase(cur, data, "reserved")

    # forward льгота 10*0.95 = 9.5 ; open return 10*0.95*0.85 = 8.075 -> 8.08
    assert amount_due == round(9.5 + round(10 * 0.95 * 0.85, 2), 2)
