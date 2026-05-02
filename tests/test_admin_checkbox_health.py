import importlib
import os
import sys

import httpx
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
    def commit(self):
        pass
    def rollback(self):
        pass


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr('psycopg2.connect', lambda *a, **kw: DummyConn())
    os.environ['CHECKBOX_ENABLED'] = 'true'
    os.environ['CHECKBOX_CASHIER_LOGIN'] = 'login'
    os.environ['CHECKBOX_CASHIER_PASSWORD'] = 'pwd'

    if 'backend.main' in sys.modules:
        importlib.reload(sys.modules['backend.main'])
    else:
        importlib.import_module('backend.main')

    from backend.main import app
    import backend.auth
    app.dependency_overrides[backend.auth.require_admin_token] = lambda: {'role': 'admin'}
    return TestClient(app)


def test_checkbox_health_success(client, monkeypatch):
    import backend.routers.integrations_admin as mod
    monkeypatch.setattr(mod.checkbox, 'get_token_for_healthcheck', lambda: 'token')
    monkeypatch.setattr(mod.checkbox, 'get_cashier_shift_status', lambda token: (200, {'status': 'OPENED'}))
    r = client.get('/admin/integrations/checkbox/health')
    assert r.status_code == 200
    assert r.json()['status'] in ('ok', 'warning')


def test_checkbox_health_disabled(client, monkeypatch):
    import backend.routers.integrations_admin as mod
    monkeypatch.setattr(mod.checkbox, 'is_enabled', lambda: False)
    r = client.get('/admin/integrations/checkbox/health')
    assert r.json()['status'] == 'disabled'


def test_checkbox_health_missing_env(client, monkeypatch):
    import backend.routers.integrations_admin as mod
    monkeypatch.setattr(mod.checkbox, '_env', lambda k, d='': 'true' if k == 'CHECKBOX_ENABLED' else ('' if k == 'CHECKBOX_CASHIER_LOGIN' else 'x'))
    r = client.get('/admin/integrations/checkbox/health')
    assert r.json()['status'] == 'error'


def test_checkbox_health_403(client, monkeypatch):
    import backend.routers.integrations_admin as mod

    req = httpx.Request('GET', 'https://api.checkbox.ua/api/v1/cashier/signin')
    resp = httpx.Response(403, request=req)

    def raise_403():
        raise httpx.HTTPStatusError('forbidden', request=req, response=resp)

    monkeypatch.setattr(mod.checkbox, 'get_token_for_healthcheck', raise_403)
    r = client.get('/admin/integrations/checkbox/health')
    assert r.json()['http_status'] == 403


def test_checkbox_health_network_error(client, monkeypatch):
    import backend.routers.integrations_admin as mod
    monkeypatch.setattr(mod.checkbox, 'get_token_for_healthcheck', lambda: (_ for _ in ()).throw(httpx.ConnectTimeout('timeout')))
    r = client.get('/admin/integrations/checkbox/health')
    assert 'network' in r.json()['message'].lower()
