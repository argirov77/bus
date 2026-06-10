"""Tests for the LiqPay refund helper."""

from __future__ import annotations

import os
import sys
from typing import Any, Mapping

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services import liqpay


class _FakeResponse:
    def __init__(self, body: Mapping[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Mapping[str, Any]:
        return self._body


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("LIQPAY_PUBLIC_KEY", "pub")
    monkeypatch.setenv("LIQPAY_PRIVATE_KEY", "priv")
    yield


def test_refund_payment_partial_amount_posts_action_refund(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "status": "success",
                "payment_id": "999",
                "refund_amount": 250.0,
            }
        )

    monkeypatch.setattr("backend.services.liqpay.httpx.post", fake_post)

    result = liqpay.refund_payment("purchase-42", 250.0, "Partial refund")

    assert result["status"] == "success"
    assert result["payment_id"] == "999"
    assert result["refund_amount"] == 250.0
    assert isinstance(result["raw"], dict)

    assert captured["url"] == liqpay.LIQPAY_API_URL
    assert "data" in captured["data"] and "signature" in captured["data"]


def test_refund_payment_full_amount_decodes_payload(monkeypatch):
    decoded_payloads = []

    def fake_post(url, data=None, timeout=None):
        decoded_payloads.append(liqpay.decode_payload(data["data"]))
        return _FakeResponse({"status": "success", "payment_id": "1", "amount": 1500.0})

    monkeypatch.setattr("backend.services.liqpay.httpx.post", fake_post)

    liqpay.refund_payment("purchase-7", 1500.00)

    assert decoded_payloads[0]["action"] == "refund"
    assert decoded_payloads[0]["amount"] == 1500.0
    assert decoded_payloads[0]["order_id"] == "purchase-7"


def test_refund_payment_rejects_invalid_amount():
    with pytest.raises(ValueError):
        liqpay.refund_payment("purchase-1", 0)
    with pytest.raises(ValueError):
        liqpay.refund_payment("", 50.0)


def test_is_refund_success_recognizes_known_statuses():
    assert liqpay.is_refund_success("success")
    assert liqpay.is_refund_success("ok")
    assert liqpay.is_refund_success("sandbox")
    assert not liqpay.is_refund_success("failure")
    assert not liqpay.is_refund_success(None)
