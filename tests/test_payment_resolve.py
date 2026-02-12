import importlib
import os
import sys

from fastapi.testclient import TestClient
import pytest


class ResolveCursor:
    def __init__(self, row):
        self._row = row
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
        if "from purchase" in self.query.lower():
            return self._row
        return None

    def close(self):
        pass


class ResolveConn:
    def __init__(self, row):
        self.cursor_obj = ResolveCursor(row)

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
        "verify_called": 0,
        "synced": 0,
    }

    def fake_get_connection():
        return ResolveConn(state["row"])

    def fake_verify_order(order_id: str):
        state["verify_called"] += 1
        return {"order_id": order_id, "status": "success", "payment_id": "p-1"}

    def fake_sync(purchase_id, order_id, payload, background_tasks=None):
        state["synced"] += 1
        return "paid", "p-1"

    monkeypatch.setattr("psycopg2.connect", lambda *a, **kw: ResolveConn(state["row"]))
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
    assert state["verify_called"] == 1
    assert state["synced"] == 1


def test_payments_resolve_rejects_unknown_order_format(client):
    cli, _ = client

    resp = cli.get("/public/payments/resolve", params={"order_id": "bad.order"})

    assert resp.status_code == 422
