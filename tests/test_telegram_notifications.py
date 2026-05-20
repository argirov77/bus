"""Tests for the Telegram staff notification integration."""

from __future__ import annotations

import sys

import pytest

sys.path.append(".")

from backend.services import telegram


class _DummyCursor:
    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class _DummyPsycopgConn:
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
def _clean_telegram_env(monkeypatch):
    for var in ("TELEGRAM_ENABLED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_API_URL"):
        monkeypatch.delenv(var, raising=False)
    # Ensure that importing backend.database does not try to hit a real DB.
    monkeypatch.setattr("psycopg2.connect", lambda *a, **k: _DummyPsycopgConn())
    yield


def _import_purchase_module():
    import importlib

    return importlib.import_module("backend.routers.purchase")


def _enable_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")


def test_is_enabled_requires_all_vars(monkeypatch):
    assert telegram.is_enabled() is False

    monkeypatch.setenv("TELEGRAM_ENABLED", "true")
    assert telegram.is_enabled() is False

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    assert telegram.is_enabled() is False

    monkeypatch.setenv("TELEGRAM_CHAT_ID", "y")
    assert telegram.is_enabled() is True

    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    assert telegram.is_enabled() is False


def test_send_message_skips_when_disabled(monkeypatch):
    calls: list = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("httpx.post must not be called when telegram is disabled")

    monkeypatch.setattr("backend.services.telegram.httpx.post", fake_post)
    assert telegram.send_message("hello") is False
    assert calls == []


def test_send_message_posts_to_telegram_api(monkeypatch):
    _enable_telegram(monkeypatch)
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    def fake_post(url, data=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("backend.services.telegram.httpx.post", fake_post)

    assert telegram.send_message("hi <b>there</b>") is True
    assert captured["url"] == "https://api.telegram.org/bottest-token/sendMessage"
    assert captured["data"]["chat_id"] == "-100123"
    assert captured["data"]["text"] == "hi <b>there</b>"
    assert captured["data"]["parse_mode"] == "HTML"
    assert captured["data"]["disable_web_page_preview"] is True


def test_send_message_swallows_exceptions(monkeypatch):
    _enable_telegram(monkeypatch)

    def fake_post(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("backend.services.telegram.httpx.post", fake_post)
    assert telegram.send_message("hi") is False


def test_send_message_returns_false_on_http_error(monkeypatch):
    _enable_telegram(monkeypatch)

    class FakeResponse:
        status_code = 401
        text = "Unauthorized"

    monkeypatch.setattr(
        "backend.services.telegram.httpx.post",
        lambda *a, **k: FakeResponse(),
    )
    assert telegram.send_message("hi") is False


def test_build_telegram_message_uses_snapshot(monkeypatch):
    purchase = _import_purchase_module()

    snapshot = {
        "passenger_name": "Иван Иванов",
        "passenger_phone": "+380501234567",
        "route_name": "Киев — Варна",
        "from_stop": "Киев",
        "to_stop": "Варна",
        "tour_date": "2026-06-01",
        "departure_time": "08:00",
        "arrival_time": "20:00",
        "seats": "12, 13",
        "amount_due": 1500.0,
        "currency": "UAH",
    }

    msg = purchase._build_telegram_message(
        conn=object(),  # not used because snapshot is provided
        purchase_id=42,
        event_type="refunded",
        snapshot=snapshot,
    )

    assert msg is not None
    assert "Возврат #42" in msg
    assert "Иван Иванов" in msg
    assert "+380501234567" in msg
    assert "Киев — Варна" in msg
    assert "Киев → Варна" in msg
    assert "2026-06-01" in msg
    assert "08:00 → 20:00" in msg
    assert "12, 13" in msg
    assert "1500" in msg and "UAH" in msg


def test_build_telegram_message_html_escapes(monkeypatch):
    purchase = _import_purchase_module()

    snapshot = {
        "passenger_name": "<script>alert(1)</script>",
        "route_name": "A & B",
    }
    msg = purchase._build_telegram_message(
        conn=object(), purchase_id=1, event_type="reserved", snapshot=snapshot
    )
    assert "<script>" not in msg
    assert "&lt;script&gt;" in msg
    assert "A &amp; B" in msg


def test_queue_telegram_event_is_noop_when_disabled(monkeypatch):
    purchase = _import_purchase_module()

    class FakeBG:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn, *args, **kwargs):
            self.tasks.append((fn, args, kwargs))

    bg = FakeBG()
    purchase._queue_telegram_event(bg, 1, "paid")
    assert bg.tasks == []


def test_queue_telegram_event_schedules_when_enabled(monkeypatch):
    _enable_telegram(monkeypatch)
    purchase = _import_purchase_module()

    class FakeBG:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn, *args, **kwargs):
            self.tasks.append((fn, args, kwargs))

    bg = FakeBG()
    purchase._queue_telegram_event(bg, 7, "paid", {"passenger_name": "Test"})
    assert len(bg.tasks) == 1
    fn, args, _ = bg.tasks[0]
    assert fn is purchase._send_telegram_event_task
    assert args == (7, "paid", {"passenger_name": "Test"})


def test_send_telegram_event_task_uses_snapshot_without_db(monkeypatch):
    _enable_telegram(monkeypatch)
    purchase = _import_purchase_module()

    sent_messages: list = []

    def fake_send(text, parse_mode="HTML"):
        sent_messages.append(text)
        return True

    monkeypatch.setattr(purchase.telegram, "send_message", fake_send)

    class DummyConn:
        def close(self):
            pass

    monkeypatch.setattr(purchase, "get_connection", lambda: DummyConn())

    snapshot = {
        "passenger_name": "Alice",
        "route_name": "Sofia - Plovdiv",
        "from_stop": "Sofia",
        "to_stop": "Plovdiv",
        "tour_date": "2026-07-15",
        "amount_due": 25.0,
        "currency": "BGN",
    }
    purchase._send_telegram_event_task(99, "cancelled", snapshot)

    assert len(sent_messages) == 1
    assert "Отмена #99" in sent_messages[0]
    assert "Alice" in sent_messages[0]
    assert "Sofia → Plovdiv" in sent_messages[0]
