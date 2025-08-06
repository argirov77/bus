import importlib
import os
import sys
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
        if "SELECT id, seat_id FROM ticket" in self.query:
            return [1, 1]
        return [1]

    def fetchall(self):
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

    def fake_get_connection():
        conn = DummyConn()
        store['cursor'] = conn.cursor_obj
        return conn

    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: DummyConn())
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import backend.database
    monkeypatch.setattr('backend.database.get_connection', fake_get_connection)
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
    })
    assert any('reserved' in q[0].lower() for q in store['cursor'].queries)
    assert any('insert into sales' in q[0].lower() for q in store['cursor'].queries)

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
    })
    assert any('paid' in q[0].lower() for q in store['cursor'].queries)
    assert any('insert into sales' in q[0].lower() for q in store['cursor'].queries)

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
