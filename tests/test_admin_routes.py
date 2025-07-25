import importlib
import sys
import os

import pytest
from fastapi.testclient import TestClient


class DummyCursor:
    def execute(self, *args, **kwargs):
        self.query = args[0] if args else ""

    def fetchone(self):
        if "FROM users" in self.query:
            # hashed 'admin'
            return ["8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918", "admin"]
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

    def commit(self):
        pass

    def rollback(self):
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


def test_admin_routes_with_and_without_token(client):
    login = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
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
        resp = getattr(client, method)(path, headers=headers)
        assert resp.status_code != 401

    bad_headers = {"Authorization": "Bearer wrong"}
    for method, path in routes:
        resp = getattr(client, method)(path, headers=bad_headers)
        assert resp.status_code == 401

    resp = client.put(
        "/seat/block",
        params={"tour_id": 1, "seat_num": 1, "block": True},
        headers=headers,
    )
    assert resp.status_code != 401

    resp = client.put(
        "/seat/block",
        params={"tour_id": 1, "seat_num": 1, "block": True},
        headers=bad_headers,
    )
    assert resp.status_code == 401
