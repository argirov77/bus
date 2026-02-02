import os
import sys
import importlib

import pytest
from fastapi.testclient import TestClient


class DummyCursor:
    def __init__(self):
        self.query = ""
        self.params = None

    def execute(self, query, params=None):
        self.query = query.lower()
        self.params = params

    def fetchall(self):
        if "select distinct departure_stop_id" in self.query:
            return [(1,), (2,)]
        if "select distinct arrival_stop_id" in self.query:
            return [(1,), (2,)]
        if "coalesce(stop_en" in self.query:
            return [(1, "Stop1_en"), (2, "Stop2_en")]
        if "coalesce(stop_name" in self.query:
            return [(1, "Stop1_ru"), (2, "Stop2_ru")]
        return []

    def fetchone(self):
        return None

    def close(self):
        pass


class DummyConn:
    def cursor(self):
        return DummyCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def fake_get_connection():
    return DummyConn()


@pytest.fixture
def client(monkeypatch):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    monkeypatch.setattr("psycopg2.connect", lambda *a, **kw: DummyConn())
    import backend.database
    monkeypatch.setattr("backend.database.get_connection", fake_get_connection)
    if "backend.main" in sys.modules:
        importlib.reload(sys.modules["backend.main"])
    else:
        importlib.import_module("backend.main")
    app = sys.modules["backend.main"].app
    monkeypatch.setattr("backend.routers.search.get_connection", fake_get_connection)
    return TestClient(app)


def test_departures_lang(client):
    resp = client.post("/search/departures", json={"lang": "en", "seats": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["stop_name"] == "Stop1_en"


def test_arrivals_lang(client):
    resp = client.post(
        "/search/arrivals",
        json={"lang": "en", "departure_stop_id": 1, "seats": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["stop_name"] == "Stop1_en"


def test_departures_options(client):
    resp = client.options(
        "/search/departures",
        headers={
            "Origin": "http://localhost:4000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:4000"


def test_arrivals_options(client):
    resp = client.options(
        "/search/arrivals",
        headers={
            "Origin": "http://localhost:4000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:4000"
