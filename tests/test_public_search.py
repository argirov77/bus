import os
import sys
import importlib
from datetime import date, time

import pytest
from fastapi.testclient import TestClient


class DummyCursor:
    def __init__(self):
        self.query = ""

    def execute(self, query, params=None):
        self.query = query

    def fetchall(self):
        # Return one dummy tour row with times and price
        return [(1, date(2024, 1, 1), 5, 1, time(8, 0), time(10, 0), 200.0)]

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
    def fake_conn(*args, **kwargs):
        return DummyConn()

    monkeypatch.setattr('psycopg2.connect', fake_conn)
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import backend.database
    monkeypatch.setattr('backend.database.get_connection', fake_conn)
    if 'backend.main' in sys.modules:
        importlib.reload(sys.modules['backend.main'])
    else:
        importlib.import_module('backend.main')
    app = sys.modules['backend.main'].app
    monkeypatch.setattr('backend.routers.tour.get_connection', fake_conn)
    return TestClient(app)


def test_tours_search_public(client):
    resp = client.get('/tours/search', params={
        'departure_stop_id': 1,
        'arrival_stop_id': 2,
        'date': '2024-01-01',
        'seats': 1
    })
    assert resp.status_code == 200
    assert resp.json() == [{
        'id': 1,
        'date': '2024-01-01',
        'seats': 5,
        'layout_variant': 1,
        'departure_time': '08:00',
        'arrival_time': '10:00',
        'price': 200.0
    }]
