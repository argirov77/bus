"""Tests for CheckBox refund-receipt creation."""

from __future__ import annotations

import os
import sys
from typing import Any, Mapping

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services import checkbox


class _FakeResponse:
    def __init__(self, body: Mapping[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Mapping[str, Any]:
        return self._body


class _DummyCursor:
    def __init__(self) -> None:
        self.last_query: str = ""
        self.last_params: Any = None

    def execute(self, query: str, params: Any = None) -> None:
        self.last_query = query
        self.last_params = params

    def fetchone(self):
        if "checkbox_receipt_id" in self.last_query:
            return ("RECEIPT-PREV",)
        if "information_schema" in self.last_query:
            return (1,)
        return None

    def fetchall(self):
        return []

    def close(self) -> None:
        pass


class _DummyConn:
    autocommit = False

    def cursor(self):
        return _DummyCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CHECKBOX_ENABLED", "true")
    monkeypatch.setenv("CHECKBOX_CASHIER_PIN", "1234")
    # Block the real DB driver before backend.database is first imported.
    monkeypatch.setattr("psycopg2.connect", lambda *a, **k: _DummyConn())

    # The refund function does ``from ..database import get_connection`` lazily,
    # so once that module is loaded we can swap the helper itself.
    import importlib
    db_module = importlib.import_module("backend.database")
    monkeypatch.setattr(db_module, "get_connection", lambda: _DummyConn())

    # Bypass token/shift orchestration so we can focus on the refund call.
    monkeypatch.setattr(
        "backend.services.checkbox._auth_headers", lambda: {"Authorization": "Bearer test"}
    )
    monkeypatch.setattr("backend.services.checkbox._ensure_shift", lambda: "SHIFT-1")
    yield


def _install_post(monkeypatch, body):
    calls: list[dict[str, Any]] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(body)

    monkeypatch.setattr("backend.services.checkbox.httpx.post", fake_post)
    return calls


def _install_get(monkeypatch, body):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(body)

    monkeypatch.setattr("backend.services.checkbox.httpx.get", fake_get)


def test_create_refund_receipt_for_flat_amount(monkeypatch):
    calls = _install_post(monkeypatch, {"id": "RFND-1"})
    _install_get(monkeypatch, {"status": "DONE", "fiscal_code": "FC-RFND-1"})

    result = checkbox.create_refund_receipt(100, None, 150.0)

    assert result == {
        "receipt_id": "RFND-1",
        "fiscal_number": "FC-RFND-1",
        "status": "done",
    }
    assert calls and calls[0]["url"].endswith("/receipts/service")
    body = calls[0]["json"]
    assert body["payments"][0]["value"] == 15000  # 150.00 -> kopecks
    # Single flat refund position
    assert len(body["goods"]) == 1
    assert "Повернення" in body["goods"][0]["good"]["name"]
    # Should reference the original purchase receipt when one is on file.
    assert body.get("related_receipt_id") == "RECEIPT-PREV"


def test_create_refund_receipt_rejects_disabled(monkeypatch):
    monkeypatch.setenv("CHECKBOX_ENABLED", "false")
    with pytest.raises(RuntimeError):
        checkbox.create_refund_receipt(1, None, 10.0)


def test_create_refund_receipt_rejects_zero_amount():
    with pytest.raises(ValueError):
        checkbox.create_refund_receipt(1, None, 0)
