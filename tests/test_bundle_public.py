import os
import sys
import importlib
from datetime import time

import pytest
from fastapi.testclient import TestClient

class DummyCursor:
    def __init__(self):
        self.query = ""
        self.params = None
    def execute(self, query, params=None):
        self.query = query.lower()
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

