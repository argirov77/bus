import os
import sys
from fastapi.testclient import TestClient
import pytest
from datetime import datetime

class DummyCursor:
    def __init__(self):
        self.queries = []
        self.query = ""
    def execute(self, query, params=None):
        self.query = query
        self.queries.append((query, params))
    def fetchone(self):
        return None
    def fetchall(self):
        if "FROM purchase" in self.query:
            # The admin purchase list now returns one row per purchase without
            # joining ticket data. The dummy row mimics the new column order.
            return [(
                1,
                datetime(2025, 8, 10, 10, 0, 0),
                "Ivan",
                "ivan@example.com",
                "+123",
                52.0,
                "reserved",
                datetime(2025, 8, 9, 12, 0, 0),
                "online",
            )]
        if "FROM ticket" in self.query:
            return [(
                1,
                10,
                datetime(2025, 8, 10).date(),
                5,
                12,
                2,
                "Ivan",
                1,
                "Stop1",
                2,
                "Stop4",
                1,
                0,
            )]
        if "FROM sales" in self.query:
            return [
                (
                    1,
                    datetime(2025, 8, 9, 12, 0, 0),
                    "reserved",
                    0.0,
                    1,
                    "system",
                    None,
                ),
                (
                    2,
                    datetime(2025, 8, 9, 13, 0, 0),
                    "paid",
                    52.0,
                    1,
                    "cashier1",
                    "offline",
                ),
            ]
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

@pytest.fixture
def client(monkeypatch):
    def fake_get_connection():
        return DummyConn()
    monkeypatch.setenv("CLIENT_FRONTEND_ORIGIN", "https://example.test")
    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: DummyConn())
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import importlib
    import backend.database
    monkeypatch.setattr('backend.database.get_connection', fake_get_connection)
    if 'backend.main' in sys.modules:
        importlib.reload(sys.modules['backend.main'])
    else:
        importlib.import_module('backend.main')
    app = sys.modules['backend.main'].app
    import backend.auth
    app.dependency_overrides[backend.auth.require_admin_token] = lambda: None
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(backend.auth.require_admin_token, None)


def test_admin_purchase_list(client):
    resp = client.get('/admin/purchases')
    assert resp.status_code == 200
    data = resp.json()
    assert data and data[0]['id'] == 1


def test_admin_purchase_info(client):
    resp = client.get('/admin/purchases/1')
    assert resp.status_code == 200
    data = resp.json()
    assert len(data['tickets']) == 1
    assert data['tickets'][0]['id'] == 1
    assert data['tickets'][0]['seat_num'] == 12
    assert data['tickets'][0]['passenger_name'] == 'Ivan'
    assert data['tickets'][0]['from_stop_name'] == 'Stop1'
    assert data['tickets'][0]['to_stop_name'] == 'Stop4'
    assert len(data['logs']) == 2
    assert data['logs'][0]['action'] == 'reserved'
