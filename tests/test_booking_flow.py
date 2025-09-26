import importlib
import os
import sys
from datetime import date, time

from fastapi.testclient import TestClient
import pytest

class DummyCursor:
    def __init__(self):
        self.queries = []
        self.query = ""
        self.rowcount = 1

    def execute(self, query, params=None):
        self.query = query
        self.queries.append((query, params))

    def fetchone(self):
        q = self.query.lower()
        if "select id, seat_id from ticket" in q:
            return [1, 1]
        if "select route_id, pricelist_id, date from tour" in q:
            return [1, 1, date(2024, 1, 1)]
        if "select route_id, date from tour" in q:
            return [1, date(2024, 1, 1)]
        if "select id, available from seat" in q:
            return [1, "1234"]
        if "select price from prices" in q:
            return [10]
        return [1]

    def fetchall(self):
        q = self.query.lower()
        if "select stop_id, departure_time from routestop" in q:
            return [
                (1, time(8, 0)),
                (2, time(9, 0)),
                (3, time(10, 0)),
                (4, time(11, 0)),
            ]
        if "select id from ticket where purchase_id" in q:
            return [(1,)]
        return []

    def close(self):
        pass

class DummyConn:
    def __init__(self):
        self.cursor_obj = DummyCursor()

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

@pytest.fixture
def client(monkeypatch):
    store = {}
    monkeypatch.setenv("APP_PUBLIC_URL", "https://example.test")

    def fake_get_connection():
        conn = DummyConn()
        store['cursor'] = conn.cursor_obj
        return conn

    token_counter = {"value": 0}

    def fake_issue(ticket_id, purchase_id, scopes, lang, departure_dt):
        token_counter["value"] += 1
        return f"token-{token_counter['value']}"

    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: DummyConn())
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import backend.database
    monkeypatch.setattr('backend.database.get_connection', fake_get_connection)
    monkeypatch.setattr('backend.ticket_utils.free_ticket', lambda *a, **k: None)
    monkeypatch.setattr('backend.routers.purchase.free_ticket', lambda *a, **k: None)
    monkeypatch.setattr('backend.services.ticket_links.issue', fake_issue)
    if 'backend.main' in sys.modules:
        importlib.reload(sys.modules['backend.main'])
    else:
        importlib.import_module('backend.main')
    app = sys.modules['backend.main'].app
    monkeypatch.setattr('backend.routers.purchase.get_connection', fake_get_connection)
    return TestClient(app), store


def test_booking_flow(client):
    cli, store = client
    # 1. Booking via /book -> reserved status
    resp = cli.post('/book', json={
        'tour_id': 1,
        'seat_nums': [1],
        'passenger_names': ['A'],
        'passenger_phone': '1',
        'passenger_email': 'a@b.com',
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'adult_count': 1,
        'discount_count': 0,
    })
    assert any('reserved' in q[0].lower() for q in store['cursor'].queries)
    assert any('insert into sales' in q[0].lower() for q in store['cursor'].queries)
    assert 'amount_due' in resp.json()
    assert resp.json()['tickets'][0]['deep_link'] == 'https://example.test/ticket/1?token=token-1'

    store['cursor'].queries.clear()

    # 2. Pay booking -> paid status
    resp = cli.post('/pay', json={'purchase_id': 1})
    assert any('paid' in q[0].lower() for q in store['cursor'].queries)
    assert any('insert into sales' in q[0].lower() for q in store['cursor'].queries)

    store['cursor'].queries.clear()

    # 3. Direct purchase -> paid status
    resp = cli.post('/purchase', json={
        'tour_id': 1,
        'seat_nums': [1],
        'passenger_names': ['A'],
        'passenger_phone': '1',
        'passenger_email': 'a@b.com',
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'adult_count': 1,
        'discount_count': 0,
    })
    assert any('paid' in q[0].lower() for q in store['cursor'].queries)
    assert any('insert into sales' in q[0].lower() for q in store['cursor'].queries)
    assert 'amount_due' in resp.json()
    assert resp.json()['tickets'][0]['deep_link'] == 'https://example.test/ticket/1?token=token-2'

    store['cursor'].queries.clear()

    # 4. Cancel booking -> cancelled status
    resp = cli.post('/cancel/1')
    assert any('cancelled' in q[0].lower() for q in store['cursor'].queries)
    assert any('insert into sales' in q[0].lower() for q in store['cursor'].queries)

    store['cursor'].queries.clear()

    # 5. Refund purchase -> refunded status
    resp = cli.post('/refund/1')
    assert any('refunded' in q[0].lower() for q in store['cursor'].queries)
    assert any('insert into sales' in q[0].lower() for q in store['cursor'].queries)
