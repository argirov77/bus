"""Tests for automatic fiscal-receipt email delivery."""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services.email import render_receipt_email


@pytest.fixture(autouse=True)
def _block_real_db(monkeypatch):
    """Prevent backend.database import from touching a real PostgreSQL server."""

    class _NullConn:
        autocommit = False

        def cursor(self):
            class _NullCursor:
                def execute(self, *a, **k):
                    return None

                def fetchone(self):
                    return None

                def fetchall(self):
                    return []

                def close(self):
                    pass

            return _NullCursor()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("psycopg2.connect", lambda *a, **k: _NullConn())
    yield


@pytest.mark.parametrize(
    "lang, expected_subject, marker",
    [
        ("bg", "Фискален чек за поръчка №77", "Отворете фискалния чек онлайн"),
        ("en", "Fiscal receipt for order #77", "Open the fiscal receipt online"),
        ("ua", "Фіскальний чек для замовлення №77", "Відкрити фіскальний чек онлайн"),
    ],
)
def test_render_receipt_email_localization(lang, expected_subject, marker):
    subject, html = render_receipt_email(
        purchase_id=77,
        fiscal_code="FC-123",
        receipt_url="https://receipts.example/77.png",
        customer_name="Ivan",
        amount_text="150.00 UAH",
        lang=lang,
    )

    assert subject == expected_subject
    assert "FC-123" in html
    assert "https://receipts.example/77.png" in html
    assert "150.00 UAH" in html
    assert marker in html


def test_render_receipt_email_defaults_to_bg_for_unknown_lang():
    subject, html = render_receipt_email(
        purchase_id=5,
        fiscal_code="FC-5",
        receipt_url=None,
        lang="zz",
    )

    assert "поръчка №5" in subject
    # No receipt_url -> the online link block is omitted.
    assert "http" not in html


class _DummyCursor:
    def __init__(self, row):
        self._row = row

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return self._row

    def close(self):
        pass


class _DummyConn:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _DummyCursor(self._row)

    def close(self):
        pass


def _patch_checkbox_common(monkeypatch, checkbox, row):
    import importlib

    db_module = importlib.import_module("backend.database")
    monkeypatch.setattr(db_module, "get_connection", lambda: _DummyConn(row))
    monkeypatch.setattr(checkbox, "get_receipt_png_bytes", lambda receipt_id: b"PNG")


def test_deliver_receipt_email_sends_message(monkeypatch):
    from backend.services import checkbox

    monkeypatch.setenv("FISCAL_RECEIPT_EMAIL_ENABLED", "true")
    _patch_checkbox_common(
        monkeypatch, checkbox, ("customer@example.com", "Alice", 150.0)
    )

    sent: list[dict[str, Any]] = []

    def fake_send(to, subject, html_body, png_bytes):
        sent.append(
            {"to": to, "subject": subject, "html": html_body, "png": png_bytes}
        )

    monkeypatch.setattr(
        "backend.services.email.send_receipt_email", fake_send
    )

    checkbox._deliver_receipt_email(77, "RCPT-1", "FC-77")

    assert len(sent) == 1
    message = sent[0]
    assert message["to"] == "customer@example.com"
    assert "77" in message["subject"]
    assert message["png"] == b"PNG"
    assert "FC-77" in message["html"]


def test_deliver_receipt_email_disabled_skips(monkeypatch):
    from backend.services import checkbox

    monkeypatch.setenv("FISCAL_RECEIPT_EMAIL_ENABLED", "false")

    sent: list[Any] = []
    monkeypatch.setattr(
        "backend.services.email.send_receipt_email",
        lambda *a, **k: sent.append(a),
    )

    checkbox._deliver_receipt_email(77, "RCPT-1", "FC-77")

    assert sent == []


def test_deliver_receipt_email_without_email_skips(monkeypatch):
    from backend.services import checkbox

    monkeypatch.setenv("FISCAL_RECEIPT_EMAIL_ENABLED", "true")
    _patch_checkbox_common(monkeypatch, checkbox, (None, "Alice", 150.0))

    sent: list[Any] = []
    monkeypatch.setattr(
        "backend.services.email.send_receipt_email",
        lambda *a, **k: sent.append(a),
    )

    checkbox._deliver_receipt_email(77, "RCPT-1", "FC-77")

    assert sent == []
