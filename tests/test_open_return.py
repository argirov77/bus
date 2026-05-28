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
    PurchaseQuote,
    _fare,
    _passenger_multiplier,
    _create_purchase,
    quote_purchase,
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


class FakeQuoteCursor:
    def __init__(self, forward=10, reverse=10, currency="UAH"):
        self.query = ""
        self._forward = forward
        self._reverse = reverse
        self._currency = currency
        self._price_calls = 0

    def execute(self, query, params=None):
        self.query = query.lower()
        self.params = params

    def fetchone(self):
        q = self.query
        if "select pricelist_id from tour" in q:
            return [1]
        if "select price from prices" in q:
            # First lookup is forward, second (if any) is the reverse direction.
            self._price_calls += 1
            return [self._forward] if self._price_calls == 1 else [self._reverse]
        if "select currency from pricelist" in q:
            return [self._currency]
        return [1]

    def close(self):
        pass


class FakeQuoteConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def close(self):
        pass


def _patch_quote(monkeypatch, cur):
    monkeypatch.setattr(purchase, "guard_public_request", lambda *a, **k: None)
    monkeypatch.setattr(purchase, "get_connection", lambda: FakeQuoteConn(cur))


def test_quote_one_way(monkeypatch):
    cur = FakeQuoteCursor(forward=10)
    _patch_quote(monkeypatch, cur)
    data = PurchaseQuote(
        tour_id=1, departure_stop_id=1, arrival_stop_id=2, adult_count=2, discount_count=0
    )
    result = quote_purchase(data, request=object())
    assert result == {"amount_due": 20.0, "currency": "UAH"}


def test_quote_return_leg_discount(monkeypatch):
    cur = FakeQuoteCursor(forward=10)
    _patch_quote(monkeypatch, cur)
    data = PurchaseQuote(
        tour_id=1,
        departure_stop_id=2,
        arrival_stop_id=1,
        adult_count=1,
        discount_count=0,
        is_return_leg=True,
    )
    result = quote_purchase(data, request=object())
    assert result["amount_due"] == 8.5


def test_quote_open_return_adds_reverse_leg(monkeypatch):
    cur = FakeQuoteCursor(forward=10, reverse=10)
    _patch_quote(monkeypatch, cur)
    data = PurchaseQuote(
        tour_id=1,
        departure_stop_id=1,
        arrival_stop_id=2,
        adult_count=1,
        discount_count=0,
        open_return=True,
    )
    result = quote_purchase(data, request=object())
    # forward 10 + open return 10*0.85 = 18.5
    assert result["amount_due"] == 18.5


def test_void_open_returns_cancels_open_vouchers():
    captured = {}

    class C:
        def execute(self, query, params=None):
            captured["q"] = query.lower()
            captured["p"] = params

    purchase._void_open_returns(C(), 5)
    assert "update open_ticket set status='cancelled'" in captured["q"]
    assert "status='open'" in captured["q"]
    assert captured["p"] == (5,)


class _Sess:
    jti = "jti-1"


class FakeActivateCursor:
    """Cursor for activate_open_return where the parent purchase is unpaid."""

    OPEN_ROW = (
        1,    # id
        1,    # purchase_id
        10,   # passenger_id
        1,    # pricelist_id
        2,    # departure_stop_id
        1,    # arrival_stop_id
        False,  # is_discount
        0,    # extra_baggage
        100.0,  # amount_paid
        "open",  # status
        None,  # expires_at (active)
        None,  # redeemed_ticket_id
        None,  # redeemed_at
    )

    def __init__(self, purchase_status="reserved"):
        self.query = ""
        self._purchase_status = purchase_status

    def execute(self, query, params=None):
        self.query = query.lower()

    def fetchone(self):
        q = self.query
        if "from open_ticket where id" in q:
            return self.OPEN_ROW
        if "select status from purchase where id" in q:
            return [self._purchase_status]
        return None

    def close(self):
        pass


class FakeActivateConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_activate_rejects_unpaid_purchase(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from backend.routers import public
    from backend.routers.public import activate_open_return, OpenReturnActivateRequest

    cur = FakeActivateCursor(purchase_status="reserved")
    monkeypatch.setattr(public, "get_connection", lambda: FakeActivateConn(cur))
    monkeypatch.setattr(
        public, "_require_view_session", lambda request, **k: (_Sess(), 1, 1, "cookie")
    )
    monkeypatch.setattr(public, "guard_public_request", lambda *a, **k: None)
    monkeypatch.setattr(public, "_require_csrf", lambda request: "csrf")
    monkeypatch.setattr(public.link_sessions, "touch_session_usage", lambda *a, **k: None)

    data = OpenReturnActivateRequest(tour_id=456, seat_num=15)
    with pytest.raises(HTTPException) as exc:
        activate_open_return(1, data, request=object())
    assert exc.value.status_code == 409
    assert "not paid" in exc.value.detail.lower()
