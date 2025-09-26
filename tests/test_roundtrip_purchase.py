import importlib
import os
import sys
from fastapi.testclient import TestClient
import pytest

class UniqueSalesCursor:
    def __init__(self):
        self.queries = []
        self.query = ""
        self.rowcount = 1
        self.sales_keys = set()
    def execute(self, query, params=None):
        q = query.lower()
        if "insert into sales" in q and "where not exists" not in q:
            key = (params[0], params[1])
            if key in self.sales_keys:
                raise Exception("duplicate sales")
            self.sales_keys.add(key)
        self.query = query
        self.queries.append((query, params))
    def fetchone(self):
        q = self.query.lower()
        if "select route_id, pricelist_id from tour" in q:
            return [1, 1]
        if "select stop_id from routestop" in q:
            return [(1,), (2,)]
        if "select price from prices" in q:
            return [10]
        if "select id, available from seat" in q:
            return [1, "1234"]
        if "select amount_due, status from purchase" in q:
            return [10, 'paid']
        if "select amount_due, customer_email from purchase" in q:
            return [10, 'a@b.com']
        if "select amount_due from purchase" in q:
            return [10]
        return [1]
    def fetchall(self):
        if "select stop_id from routestop" in self.query.lower():
            return [(1,), (2,), (3,), (4,)]
        return []
    def close(self):
        pass

class UniqueSalesConn:
    def __init__(self):
        self.cursor_obj = UniqueSalesCursor()
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
    def fake_get_connection():
        return UniqueSalesConn()
    payloads = {
        "token-pay": {
            "ticket_id": 1,
            "purchase_id": 1,
            "scopes": ["pay"],
            "lang": "bg",
            "exp": 4102444800,
            "jti": "jti-pay",
        }
    }

    from backend.services import ticket_links

    def fake_verify(token):
        payload = payloads.get(token)
        if not payload:
            raise ticket_links.TokenInvalid("invalid token")
        return payload
    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: UniqueSalesConn())
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import backend.database
    monkeypatch.setattr('backend.database.get_connection', fake_get_connection)
    monkeypatch.setattr('backend.ticket_utils.free_ticket', lambda *a, **k: None)
    monkeypatch.setattr('backend.routers.purchase.free_ticket', lambda *a, **k: None)
    monkeypatch.setattr('backend.services.ticket_links.verify', fake_verify)
    monkeypatch.setattr('backend.routers.purchase.render_ticket_pdf', lambda *a, **k: b'%PDF-FAKE%')
    monkeypatch.setattr(
        'backend.routers.purchase.render_ticket_email',
        lambda dto, deep_link, lang: ("subject", "<p>body</p>"),
    )
    monkeypatch.setattr('backend.routers.purchase.send_ticket_email', lambda *a, **k: None)
    if 'backend.main' in sys.modules:
        importlib.reload(sys.modules['backend.main'])
    else:
        importlib.import_module('backend.main')
    app = sys.modules['backend.main'].app
    monkeypatch.setattr('backend.routers.purchase.get_connection', fake_get_connection)
    return TestClient(app)


def test_multiple_purchases_same_id(client):
    # first purchase to create id
    resp1 = client.post('/purchase?token=token-pay', json={
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
    assert resp1.status_code == 200
    purchase_id = resp1.json()['purchase_id']
    # second purchase using same purchase id simulating return trip
    resp2 = client.post('/purchase?token=token-pay', json={
        'tour_id': 1,
        'seat_nums': [2],
        'passenger_names': ['B'],
        'passenger_phone': '1',
        'passenger_email': 'a@b.com',
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'adult_count': 1,
        'discount_count': 0,
        'purchase_id': purchase_id
    })
    assert resp2.status_code == 200
