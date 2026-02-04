import os
import sys
import importlib
from datetime import datetime, timezone
from fastapi.testclient import TestClient
import pytest

class DummyCursor:
    def __init__(self):
        self.queries = []
        self.query = ""
        self.rowcount = 1
        self.purchase_amount = 0
        self.purchase_status = 'paid'

    def execute(self, query, params=None):
        self.query = query
        self.queries.append((query, params))
        q = query.lower()
        if 'insert into purchase' in q and params:
            # params: customer_name, email, phone, amount_due, payment_method
            self.purchase_amount = params[3]
        if 'update purchase set amount_due' in q and params:
            self.purchase_amount = params[0]

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
    token_counter = {"value": 0}
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

    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: DummyConn(cursor))
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import backend.database
    monkeypatch.setattr('backend.database.get_connection', fake_get_connection)
    monkeypatch.setenv("CLIENT_FRONTEND_ORIGIN", "https://example.test")
    monkeypatch.setenv("TICKET_LINK_BASE_URL", "https://example.test")
    def fake_issue(ticket_id, purchase_id, scopes, lang, departure_dt, conn=None):
        token_counter["value"] += 1
        return f"token-{token_counter['value']}"

    monkeypatch.setattr('backend.ticket_utils.free_ticket', lambda *a, **k: None)
    monkeypatch.setattr('backend.routers.purchase.free_ticket', lambda *a, **k: None)
    monkeypatch.setattr('backend.services.ticket_links.verify', fake_verify)
    monkeypatch.setattr('backend.services.ticket_links.issue', fake_issue)
    session_counter = {"value": 0}

    def fake_get_or_create_view_session(
        ticket_id: int,
        *,
        purchase_id: int | None,
        lang: str,
        departure_dt,
        scopes,
        conn=None,
    ) -> tuple[str, datetime]:
        ticket_links.issue(
            ticket_id,
            purchase_id,
            scopes,
            lang,
            departure_dt,
            conn=conn,
        )
        session_counter["value"] += 1
        return f"opaque-{session_counter['value']}", datetime(2030, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr('backend.routers._ticket_link_helpers.get_or_create_view_session', fake_get_or_create_view_session)
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


def test_purchase_round_trip(client):
    cli, store = client
    # First purchase
    resp = cli.post('/purchase?token=token-pay', json={
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
    assert store['cursor'].purchase_amount == 10
    store['cursor'].queries.clear()

    # Second purchase with same purchase_id (return trip)
    resp = cli.post('/purchase?token=token-pay', json={
        'tour_id': 2,
        'seat_nums': [1],
        'passenger_names': ['A'],
        'passenger_phone': '1',
        'passenger_email': 'a@b.com',
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'adult_count': 1,
        'discount_count': 0,
        'purchase_id': pid,
    })
    assert resp.status_code == 200
    assert store['cursor'].purchase_amount == 20
    # ensure update query executed
    assert any('update purchase set amount_due' in q[0].lower() for q in store['cursor'].queries)
