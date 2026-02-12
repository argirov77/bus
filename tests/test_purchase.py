import importlib
import os
import sys
from datetime import date, time, datetime, timezone

from fastapi.testclient import TestClient
import pytest
import jwt

class DummyCursor:
    status_resp = "reserved"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

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
        if "select amount_due, status, customer_email from purchase" in q:
            return [10, "reserved", "a@b.com"]
        if "select amount_due, customer_email from purchase" in q:
            return [10, "a@b.com"]
        if "select amount_due, status from purchase" in q:
            return [10, "reserved"]
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
        self.was_committed = False
        self.was_rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.was_committed = True

    def rollback(self):
        self.was_rolled_back = True

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    last = {}
    monkeypatch.setenv("APP_PUBLIC_URL", "https://example.test")
    monkeypatch.setenv("CLIENT_FRONTEND_ORIGIN", "https://example.test")
    monkeypatch.setenv("TICKET_LINK_BASE_URL", "https://example.test")

    def fake_get_connection():
        conn = DummyConn()
        last['cursor'] = conn.cursor_obj
        last['conn'] = conn
        return conn

    token_counter = {"value": 0}

    def fake_issue(ticket_id, purchase_id, scopes, lang, departure_dt, conn=None):
        token_counter['value'] += 1
        return f"token-{token_counter['value']}"

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
        "token-cancel": {
            "ticket_id": 1,
            "purchase_id": 1,
            "scopes": ["cancel"],
            "lang": "bg",
            "exp": 4102444800,
            "jti": "jti-cancel",
        },
        "token-no-cancel": {
            "ticket_id": 1,
            "purchase_id": 1,
            "scopes": ["pay"],
            "lang": "bg",
            "exp": 4102444800,
            "jti": "jti-no-cancel",
        },
        "token-pay-other-purchase": {
            "ticket_id": 1,
            "purchase_id": 2,
            "scopes": ["pay"],
            "lang": "bg",
            "exp": 4102444800,
            "jti": "jti-pay-other",
        },
    }

    from backend.services import ticket_links

    def fake_verify(token):
        payload = payloads.get(token)
        if not payload:
            raise ticket_links.TokenInvalid("invalid token")
        return payload

    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: DummyConn())
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import backend.database
    monkeypatch.setattr('backend.database.get_connection', fake_get_connection)
    monkeypatch.setattr('backend.ticket_utils.free_ticket', lambda *a, **k: None)
    monkeypatch.setattr('backend.routers.purchase.free_ticket', lambda *a, **k: None)
    monkeypatch.setattr('backend.services.ticket_links.issue', fake_issue)
    monkeypatch.setattr('backend.services.ticket_links.verify', fake_verify)
    def fake_decode_token(token):
        if token == "admin-token":
            return {"role": "admin", "jti": "admin-jti"}
        raise jwt.PyJWTError("invalid")

    monkeypatch.setattr('backend.auth.decode_token', fake_decode_token)
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
    assert resp.json()['tickets'][0]['deep_link'].endswith('/q/opaque-1')

    store['cursor'].queries.clear()

    resp = cli.post('/pay', json={'purchase_id': 1})
    assert resp.status_code == 401

    resp = cli.post('/pay?token=token-no-pay', json={'purchase_id': 1})
    assert resp.status_code == 403

    resp = cli.post('/pay?token=token-pay-other-purchase', json={'purchase_id': 1})
    assert resp.status_code == 403

    resp = cli.post('/pay?token=token-pay', json={'purchase_id': 1})
    assert resp.status_code == 200
    assert resp.json()["provider"] == "liqpay"
    assert resp.json()["payload"]["result_url"] == "https://example.test/return"

    store['cursor'].queries.clear()

    resp = cli.post('/purchase?token=token-no-pay', json={
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
    assert resp.status_code == 403

    resp = cli.post('/purchase?token=token-pay', json={
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
    assert resp.json()['tickets'][0]['deep_link'].endswith('/q/opaque-2')

    store['cursor'].queries.clear()

    DummyCursor.status_resp = 'reserved'
    resp = cli.post('/cancel/1?token=token-no-cancel')
    assert resp.status_code == 403

    resp = cli.post('/cancel/1?token=token-cancel')
    assert resp.status_code == 204
    assert any("status='cancelled'" in q[0] for q in store['cursor'].queries)
    assert any('INSERT INTO sales' in q[0] for q in store['cursor'].queries)

    store['cursor'].queries.clear()
    DummyCursor.status_resp = 'paid'
    resp = cli.post('/refund/1?token=token-no-cancel')
    assert resp.status_code == 403

    resp = cli.post('/refund/1?token=token-cancel')
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


def test_admin_pay_logs_offline_method(client):
    cli, store = client
    reserve_resp = cli.post('/book', json={
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
    assert reserve_resp.status_code == 200
    store['cursor'].queries.clear()

    resp = cli.post(
        '/pay',
        json={'purchase_id': 1},
        headers={'Authorization': 'Bearer admin-token'},
    )

    assert resp.status_code == 204
    sales_inserts = [
        (query, params)
        for query, params in store['cursor'].queries
        if 'insert into sales' in query.lower() and params is not None
    ]
    assert sales_inserts, 'Expected INSERT INTO sales for admin /pay'
    assert sales_inserts[-1][1][4] == 'offline'


def test_result_url_is_consistent_between_pay_endpoints(client, monkeypatch):
    cli, _store = client

    from backend.routers import public as public_module

    def fake_require_purchase_context(request, purchase_id, scope):
        return object(), 77, purchase_id, "purchase_session"

    monkeypatch.setattr(public_module, "_require_purchase_context", fake_require_purchase_context)

    pay_resp = cli.post('/pay?token=token-pay', json={'purchase_id': 1})
    public_pay_resp = cli.post('/public/purchase/1/pay')

    assert pay_resp.status_code == 200
    assert public_pay_resp.status_code == 200

    pay_result_url = pay_resp.json()["payload"]["result_url"]
    public_result_url = public_pay_resp.json()["payload"]["result_url"]

    assert pay_result_url == public_result_url == "https://example.test/return"
    assert pay_resp.json()["payload"]["server_url"] == "https://example.test/api/public/payment/liqpay/callback"
    assert public_pay_resp.json()["payload"]["server_url"] == "https://example.test/api/public/payment/liqpay/callback"


def test_result_url_rejects_localhost_in_production_config(client, monkeypatch):
    cli, _store = client

    monkeypatch.setenv("CLIENT_APP_BASE", "http://localhost:3000")

    resp = cli.post('/pay?token=token-pay', json={'purchase_id': 1})

    assert resp.status_code == 500
    assert "localhost" in resp.json()["detail"].lower()




def test_result_url_rejects_non_https_client_base(client, monkeypatch):
    cli, _store = client

    monkeypatch.setenv("CLIENT_APP_BASE", "http://example.test")

    resp = cli.post('/pay?token=token-pay', json={'purchase_id': 1})

    assert resp.status_code == 500
    assert "https" in resp.json()["detail"].lower()


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


def test_booking_rolls_back_when_ticket_issue_fails(client, monkeypatch):
    cli, store = client

    from backend.services import ticket_links

    def failing_issue(ticket_id, purchase_id, scopes, lang, departure_dt, conn=None):
        raise ticket_links.TicketLinkError("boom")

    monkeypatch.setattr('backend.services.ticket_links.issue', failing_issue)

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

    assert resp.status_code == 500
    assert store['conn'].was_rolled_back
    assert not store['conn'].was_committed
