import importlib
import os
import sys
from fastapi.testclient import TestClient
import pytest

class DummyCursor:
    status_resp = "reserved"
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
        if "select status from purchase" in q:
            return [self.status_resp]
        if "select route_id, pricelist_id from tour" in q:
            return [1, 1]
        if "select id, available from seat" in q:
            return [1, "1234"]
        if "select price from prices" in q:
            return [10]
        return [1]
    def fetchall(self):
        q = self.query.lower()
        if "select stop_id from routestop" in q:
            return [(1,), (2,), (3,), (4,)]
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
    last = {}
    def fake_get_connection():
        conn = DummyConn()
        last['cursor'] = conn.cursor_obj
        return conn
    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: DummyConn())
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import importlib
    import backend.database
    monkeypatch.setattr('backend.database.get_connection', fake_get_connection)
    monkeypatch.setattr('backend.ticket_utils.free_ticket', lambda *a, **k: None)
    monkeypatch.setattr('backend.routers.purchase.free_ticket', lambda *a, **k: None)
    if 'backend.main' in sys.modules:
        importlib.reload(sys.modules['backend.main'])
    else:
        importlib.import_module('backend.main')
    app = sys.modules['backend.main'].app
    monkeypatch.setattr('backend.routers.purchase.get_connection', fake_get_connection)
    return TestClient(app), last


def test_purchase_flow(client):
    cli, store = client
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
    assert resp.status_code == 200
    assert 'amount_due' in resp.json()
    assert any('INSERT INTO sales' in q[0] for q in store['cursor'].queries)

    store['cursor'].queries.clear()

    resp = cli.post('/pay', json={'purchase_id': 1})
    assert resp.status_code == 204
    assert any("status='paid'" in q[0] for q in store['cursor'].queries)
    assert any('INSERT INTO sales' in q[0] for q in store['cursor'].queries)

    store['cursor'].queries.clear()

    resp = cli.post('/purchase', json={
        'tour_id': 1,
        'seat_nums': [1],
        'passenger_names': ['B'],
        'passenger_phone': '2',
        'passenger_email': 'b@c.com',
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'adult_count': 1,
        'discount_count': 0,
    })
    assert resp.status_code == 200
    assert 'amount_due' in resp.json()
    assert any('INSERT INTO purchase' in q[0] for q in store['cursor'].queries)
    assert any('INSERT INTO sales' in q[0] for q in store['cursor'].queries)

    store['cursor'].queries.clear()

    DummyCursor.status_resp = 'reserved'
    resp = cli.post('/cancel/1')
    assert resp.status_code == 204
    assert any("status='cancelled'" in q[0] for q in store['cursor'].queries)
    assert any('INSERT INTO sales' in q[0] for q in store['cursor'].queries)

    store['cursor'].queries.clear()
    DummyCursor.status_resp = 'paid'
    resp = cli.post('/refund/1')
    assert resp.status_code == 204
    assert any("status='refunded'" in q[0] for q in store['cursor'].queries)
    assert any('INSERT INTO sales' in q[0] for q in store['cursor'].queries)


def test_passenger_count_mismatch(client):
    cli, _ = client
    resp = cli.post('/book', json={
        'tour_id': 1,
        'seat_nums': [1],
        'passenger_names': ['A'],
        'passenger_phone': '1',
        'passenger_email': 'a@b.com',
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'adult_count': 1,
        'discount_count': 1,
    })
    assert resp.status_code == 400


def test_discount_price_applied(client):
    cli, _ = client
    resp = cli.post('/book', json={
        'tour_id': 1,
        'seat_nums': [1],
        'passenger_names': ['A'],
        'passenger_phone': '1',
        'passenger_email': 'a@b.com',
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'adult_count': 0,
        'discount_count': 1,
    })
    assert resp.status_code == 200
    assert resp.json()['amount_due'] == 9.5
