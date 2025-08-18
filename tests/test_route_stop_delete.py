import importlib
import pytest


def test_delete_route_stop_uses_id(monkeypatch):
    record = {}

    class DummyCursor:
        def execute(self, query, params=None):
            record['query'] = query
            record['params'] = params
        def fetchone(self):
            return (123,)
        def close(self):
            pass

    class DummyConn:
        def cursor(self):
            return DummyCursor()
        def commit(self):
            pass
        def close(self):
            pass

    # Patch psycopg2.connect before importing router module
    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: DummyConn())
    route = importlib.reload(importlib.import_module('backend.routers.route'))
    # Ensure router uses our dummy connection
    monkeypatch.setattr(route, 'get_connection', lambda: DummyConn())

    response = route.delete_route_stop(1, 2)
    assert response['deleted_id'] == 123
    assert record['params'] == (1, 2)
    query = record['query'].lower()
    assert 'stop_id' not in query
    assert 'and id=%s' in query
