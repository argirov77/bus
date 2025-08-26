import os
import sys
import importlib
from datetime import time

import pytest
from fastapi.testclient import TestClient
from psycopg2.errors import UndefinedColumn

class DummyCursor:
    def __init__(self):
        self.query = ""
        self.params = None
    def execute(self, query, params=None):
        q_lower = query.lower()
        # Simulate a database error when an unsupported language column is
        # requested.  Prior to the fix in ``selected_pricelist`` the code would
        # attempt to access a column such as ``stop_ru`` which doesn't exist in
        # the schema, resulting in a 500 error.  Raising here allows the test to
        # verify that we correctly fall back to ``stop_name`` instead of
        # constructing invalid column names.
        if "select" in q_lower and ("stop_ru" in q_lower or "stop_bg" in q_lower):
            col = "stop_ru" if "stop_ru" in q_lower else "stop_bg"
            raise Exception(f"column does not exist: {col}")
        self.query = q_lower
        self.params = params
    def fetchone(self):
        if "select id from pricelist where is_demo" in self.query:
            return [5]
        if "select name from route" in self.query and "where id" in self.query:
            rid = self.params[0]
            return [f"Route{rid}"]
        return None
    def fetchall(self):
        if "select id from route where is_demo" in self.query:
            return [(1,), (2,)]
        if "from routestop" in self.query:
            rid = self.params[0]
            stops = [
                (10, "A_en", "DescA", "LocA", time(10, 0), time(10, 5)),
                (20, "B_en", "DescB", "LocB", time(11, 0), time(11, 5)),
            ]
            if rid == 1:
                return stops
            else:
                return list(reversed(stops))
        if "from prices" in self.query:
            return [(10, "A_en", 20, "B_en", 9.9)]
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
    monkeypatch.setattr("backend.routers.bundle.get_connection", fake_get_connection)
    return TestClient(app)

def test_routes_bundle(client):
    resp = client.post("/selected_route", json={"lang": "en"})
    assert resp.status_code == 200
    data = resp.json()
    stop = data["forward"]["stops"][0]
    assert stop["name"] == "A_en"
    assert stop["description"] == "DescA"
    assert stop["location"] == "LocA"
    assert stop["arrival_time"] == "10:00"
    assert stop["departure_time"] == "10:05"

def test_pricelist_bundle(client):
    resp = client.post("/selected_pricelist", json={"lang": "en"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["prices"][0]["departure_name"] == "A_en"


def test_pricelist_bundle_unsupported_language(client):
    """Unsupported languages should gracefully fall back to the default column
    rather than causing a 500 error."""
    resp = client.post("/selected_pricelist", json={"lang": "ru"})
    assert resp.status_code == 200
    data = resp.json()
    # Our dummy cursor returns "A_en" for the departure stop regardless of
    # language; the key point is that the request succeeds instead of failing
    # with a server error.
    assert data["prices"][0]["departure_name"] == "A_en"


def test_pricelist_bundle_missing_column(client):
    """If a mapped language column is missing in the database we should
    gracefully fall back to the default column instead of returning a 500
    error."""
    resp = client.post("/selected_pricelist", json={"lang": "bg"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["prices"][0]["departure_name"] == "A_en"


def test_pricelist_bundle_missing_is_demo(client, monkeypatch):
    """If the ``is_demo`` column is absent in the ``pricelist`` table the
    endpoint should fall back to selecting the first available pricelist
    instead of returning a server error."""

    class NoDemoCursor(DummyCursor):
        def execute(self, query, params=None):
            q_lower = query.lower()
            if "select id from pricelist where is_demo" in q_lower:
                raise UndefinedColumn("column does not exist: is_demo")
            super().execute(query, params)

        def fetchone(self):
            if "select id from pricelist" in self.query and "where" not in self.query:
                return [5]
            return super().fetchone()

    class NoDemoConn(DummyConn):
        def __init__(self):
            self.cursor_obj = NoDemoCursor()

    monkeypatch.setattr("backend.routers.bundle.get_connection", lambda: NoDemoConn())
    resp = client.post("/selected_pricelist", json={"lang": "en"})
    assert resp.status_code == 200

def test_selected_route_options(client):
    resp = client.options(
        "/selected_route",
        headers={
            "Origin": "http://localhost:4000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    # The CORS middleware should echo back the requesting origin.
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:4000"

