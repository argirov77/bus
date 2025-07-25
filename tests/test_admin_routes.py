import importlib
import sys
import os

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


class DummyCursor:
    def execute(self, *args, **kwargs):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class DummyConn:
    def cursor(self):
        return DummyCursor()

    def close(self):
        pass


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr("psycopg2.connect", lambda *a, **kw: DummyConn())
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    if "backend.main" in sys.modules:
        importlib.reload(sys.modules["backend.main"])
    else:
        importlib.import_module("backend.main")
    app = sys.modules["backend.main"].app
    return TestClient(app)


def test_admin_routes_require_token(client):
    routes = [
        ("get", "/routes/"),
        ("get", "/stops/"),
        ("get", "/pricelists/"),
        ("get", "/prices/"),
        ("get", "/available/"),
        ("post", "/report/"),
        ("get", "/tours/"),
        ("get", "/admin/tickets/"),
    ]
    for method, path in routes:
        resp = getattr(client, method)(path)
        assert resp.status_code == 401

    resp = client.put(
        "/seat/block",
        params={"tour_id": 1, "seat_num": 1, "block": True},
    )
    assert resp.status_code == 401
