import os
import sys
import importlib
from fastapi.testclient import TestClient
import pytest

class DummyCursor:
    def __init__(self):
        self.queries = []
        self.query = ""
        self.rowcount = 1
        self.purchase_amount = 0
        self.purchase_status = 'reserved'

    def execute(self, query, params=None):
        self.query = query
        self.queries.append((query, params))
        q = query.lower()
        if 'insert into purchase' in q and params:
            # params: name, email, phone, amount_due, payment_method
            self.purchase_amount = params[3]
            if "'paid'" in q:
                self.purchase_status = 'paid'
            else:
                self.purchase_status = 'reserved'
        if 'update purchase set amount_due' in q and params:
            self.purchase_amount = params[0]
            if 'status=%s' in q:
                self.purchase_status = params[1]
            elif "status='paid'" in q:
                self.purchase_status = 'paid'

    def fetchone(self):
        q = self.query.lower()
        if 'select amount_due, status from purchase' in q:
            return [self.purchase_amount, self.purchase_status]
        if 'select amount_due, customer_email from purchase' in q:
            return [self.purchase_amount, 'a@b.com']
        if 'select route_id, pricelist_id from tour' in q:
            return [1, 1]
        if 'select id, available from seat' in q:
            return [1, '1234']
        if 'select price from prices' in q:
            return [10]
        if 'insert into purchase' in q:
            return [1]
        if 'select id, seat_id from ticket' in q:
            return [1, 1]
        return [1]

    def fetchall(self):
        q = self.query.lower()
        if 'select stop_id from routestop' in q:
            return [(1,), (2,), (3,), (4,)]
        return []

    def close(self):
        pass

class DummyConn:
    def __init__(self, cursor):
        self.cursor_obj = cursor
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
    cursor = DummyCursor()
    def fake_get_connection():
        conn = DummyConn(cursor)
        store['cursor'] = cursor
        return conn
    payloads = {
        "token-pay": {
            "ticket_id": 1,
            "purchase_id": 1,
            "scopes": ["pay"],
            "lang": "bg",
            "exp": 4102444800,
            "jti": "jti-pay",
        },
        "token-no-pay": {
            "ticket_id": 1,
            "purchase_id": 1,
            "scopes": [],
            "lang": "bg",
            "exp": 4102444800,
            "jti": "jti-no-pay",
        },
    }

    from backend.services import ticket_links

    def fake_verify(token):
        payload = payloads.get(token)
        if not payload:
            raise ticket_links.TokenInvalid("invalid token")
        return payload

    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: DummyConn(cursor))
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
    return TestClient(app), store


def test_reserved_to_paid_purchase(client):
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
    pid = resp.json()['purchase_id']
    assert store['cursor'].purchase_status == 'reserved'
    assert store['cursor'].purchase_amount == 10

    store['cursor'].queries.clear()

    resp = cli.post('/purchase?token=token-no-pay', json={
        'tour_id': 1,
        'seat_nums': [2],
        'passenger_names': ['B'],
        'passenger_phone': '1',
        'passenger_email': 'a@b.com',
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'adult_count': 1,
        'discount_count': 0,
        'purchase_id': pid,
    })
    assert resp.status_code == 403

    resp = cli.post('/purchase?token=token-pay', json={
        'tour_id': 1,
        'seat_nums': [2],
        'passenger_names': ['B'],
        'passenger_phone': '1',
        'passenger_email': 'a@b.com',
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'adult_count': 1,
        'discount_count': 0,
        'purchase_id': pid,
    })
    assert resp.status_code == 200
    assert store['cursor'].purchase_status == 'paid'
    assert store['cursor'].purchase_amount == 20
    assert any('update purchase set amount_due' in q[0].lower() and 'status' in q[0].lower() for q in store['cursor'].queries)
    assert any('insert into sales' in q[0].lower() for q in store['cursor'].queries)
    assert any('update_at=now()' in q[0].lower() for q in store['cursor'].queries)
