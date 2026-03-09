import importlib
import os
import sys

from fastapi.testclient import TestClient
import pytest


class ResolveCursor:
    def __init__(self, row, has_liqpay_column=True):
        self._row = row
        self._has_liqpay_column = has_liqpay_column
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchone(self):
        if "from information_schema.columns" in self.query.lower():
            return [1] if self._has_liqpay_column else None
        if "from purchase" in self.query.lower():
            return self._row
        return None

    def close(self):
        pass


class ResolveConn:
    def __init__(self, row, has_liqpay_column=True):
        self.cursor_obj = ResolveCursor(row, has_liqpay_column=has_liqpay_column)

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
    monkeypatch.setenv("APP_PUBLIC_URL", "https://example.test")
    monkeypatch.setenv("CLIENT_APP_BASE", "https://example.test")

    state = {
        "row": [1, "reserved", 15.0, "a@b.com", "Alice", "purchase-1", None],
        "has_liqpay_column": True,
        "verify_called": 0,
        "synced": 0,
    }

    def fake_get_connection():
        return ResolveConn(state["row"], has_liqpay_column=state["has_liqpay_column"])

    def fake_verify_order(order_id: str):
        state["verify_called"] += 1
        return {"order_id": order_id, "status": "success", "payment_id": "p-1"}

    def fake_sync(purchase_id, order_id, payload, background_tasks=None):
        state["synced"] += 1
        return "paid", "p-1"

    monkeypatch.setattr(
        "psycopg2.connect",
        lambda *a, **kw: ResolveConn(state["row"], has_liqpay_column=state["has_liqpay_column"]),
    )
    monkeypatch.setattr("backend.database.get_connection", fake_get_connection)

    if "backend.main" in sys.modules:
        importlib.reload(sys.modules["backend.main"])
    else:
        importlib.import_module("backend.main")

    from backend.routers import public as public_router

    monkeypatch.setattr(public_router, "get_connection", fake_get_connection)
    monkeypatch.setattr(public_router.liqpay, "verify_order", fake_verify_order)
    monkeypatch.setattr(public_router, "_sync_purchase_paid_from_liqpay_callback", fake_sync)

    app = sys.modules["backend.main"].app
    return TestClient(app), state


def test_payments_resolve_returns_paid_from_db(client):
    cli, state = client
    state["row"] = [1, "paid", 15.0, "a@b.com", "Alice", "purchase-1", "success"]

    resp = cli.get("/public/payments/resolve", params={"order_id": "purchase-1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "paid"
    assert body["purchaseId"] == 1
    assert body["purchase"]["id"] == 1
    assert state["verify_called"] == 0


def test_payments_resolve_verifies_and_syncs_pending_purchase(client):
    cli, state = client
    state["row"] = [1, "reserved", 15.0, "a@b.com", "Alice", "purchase-1", None]

    resp = cli.get("/public/payments/resolve", params={"order_id": "purchase-1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "paid"
    assert body["purchase"]["status"] == "paid"
    assert state["verify_called"] == 1
    assert state["synced"] == 1


def test_payments_resolve_rejects_unknown_order_format(client):
    cli, _ = client

    resp = cli.get("/public/payments/resolve", params={"order_id": "bad.order"})

    assert resp.status_code == 422


def test_payments_resolve_handles_missing_liqpay_columns(client):
    cli, state = client
    state["row"] = [1, "reserved", 15.0, "a@b.com", "Alice", None, None]
    state["has_liqpay_column"] = False

    resp = cli.get("/public/payments/resolve", params={"order_id": "purchase-1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "paid"
    assert state["verify_called"] == 1
    assert state["synced"] == 1


def test_payments_resolve_handles_desynced_liqpay_schema(client):
    cli, state = client
    state["row"] = [1, "reserved", 15.0, "a@b.com", "Alice", None, None]

    class UndefinedColumnError(Exception):
        pass

    from backend.routers import public as public_module

    public_module.psycopg2.errors.UndefinedColumn = UndefinedColumnError

    conn = public_module.get_connection()
    original_execute = conn.cursor_obj.execute

    calls = {"purchase_select": 0}

    def flaky_execute(query, params=None):
        q = query.lower()
        if "from purchase" in q and "liqpay_order_id" in q:
            calls["purchase_select"] += 1
            if calls["purchase_select"] == 1:
                raise UndefinedColumnError()
        return original_execute(query, params)

    conn.cursor_obj.execute = flaky_execute

    public_module.get_connection = lambda: conn

    resp = cli.get("/public/payments/resolve", params={"order_id": "purchase-1"})

    assert resp.status_code == 200
    assert resp.json()["purchaseId"] == 1
    assert state["verify_called"] == 1


def test_sync_purchase_paid_handles_desynced_liqpay_columns(monkeypatch):
    from backend.routers import public as public_module
    import psycopg2

    class Cursor:
        def __init__(self):
            self.last_query = ""
            self.update_attempts = 0

        def execute(self, query, params=None):
            self.last_query = query
            q = query.lower()
            if "from information_schema.columns" in q:
                return
            if "update purchase" in q and "liqpay_order_id" in q:
                self.update_attempts += 1
                if self.update_attempts == 1:
                    raise psycopg2.ProgrammingError('column "liqpay_order_id" does not exist')

        def fetchone(self):
            q = self.last_query.lower()
            if "from information_schema.columns" in q:
                return [1]
            if "from purchase" in q:
                return [15.0, "paid", "a@b.com"]
            return None

        def close(self):
            pass

    class Conn:
        def __init__(self):
            self.cursor_obj = Cursor()
            self.rollbacks = 0

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            pass

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            pass

    conn = Conn()
    monkeypatch.setattr(public_module, "get_connection", lambda: conn)

    status, payment_id = public_module._sync_purchase_paid_from_liqpay_callback(
        1,
        "purchase-1",
        {"status": "success", "payment_id": "p-1"},
    )

    assert status == "paid"
    assert payment_id == "p-1"
    assert conn.rollbacks == 1


def test_liqpay_callback_parses_urlencoded_body_without_python_multipart(client, monkeypatch):
    cli, _state = client

    from backend.routers import public as public_module
    import starlette.requests as starlette_requests

    monkeypatch.setattr(starlette_requests, "parse_options_header", None, raising=False)
    monkeypatch.setattr(public_module.liqpay, "verify_signature", lambda data, signature: True)
    monkeypatch.setattr(
        public_module.liqpay,
        "decode_payload",
        lambda _data: {"order_id": "ticket-94-83", "status": "success", "payment_id": "p-1"},
    )
    monkeypatch.setattr(
        public_module,
        "_sync_purchase_paid_from_liqpay_callback",
        lambda purchase_id, order_id, payload, background_tasks=None: ("paid", "p-1"),
    )

    resp = cli.post(
        "/public/payment/liqpay/callback",
        content="data=fake-data&signature=fake-signature",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "paid"
    assert body["purchase_id"] == 83
    assert body["payment_id"] == "p-1"
