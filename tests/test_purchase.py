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
        if "SELECT id, seat_id FROM ticket" in self.query:
            return [1, 1]
        if "SELECT status FROM purchase" in self.query:
            return [self.status_resp]
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
    })
    assert resp.status_code == 200
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
    })
    assert resp.status_code == 200
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
