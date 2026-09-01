"""Idempotency tests for the admin refund processing flow.

Covers the double-charge scenario observed on refund_request id=1 /
purchase 64: LiqPay refunded the money but the CheckBox fiscal receipt
failed, the request went to ``failed``, and a retry must NOT trigger a
second LiqPay refund.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

import pytest
from fastapi import HTTPException

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg2


class _BootstrapCursor:
    """No-op cursor so importing backend.database needs no live Postgres."""

    def execute(self, *args: Any, **kwargs: Any) -> None:
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


class _BootstrapConn:
    autocommit = False

    def cursor(self) -> _BootstrapCursor:
        return _BootstrapCursor()

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


_original_connect = psycopg2.connect
psycopg2.connect = lambda *a, **k: _BootstrapConn()
try:
    from backend.routers import refund_admin
    from backend.services import liqpay as real_liqpay
finally:
    psycopg2.connect = _original_connect


class FakeDB:
    def __init__(self) -> None:
        self.purchases: dict[int, dict[str, Any]] = {}
        self.tickets: dict[int, list[int]] = {}
        self.sales: list[dict[str, Any]] = []
        self.refunds: list[dict[str, Any]] = []

    def seed(
        self,
        purchase_id: int,
        *,
        paid_amount: float,
        ticket_ids: list[int],
        request_amount: float,
    ) -> dict[str, Any]:
        self.purchases[purchase_id] = {
            "id": purchase_id,
            "status": "paid",
            "customer_name": "Test User",
            "customer_email": "test@example.com",
            "payment_method": "online",
            "liqpay_order_id": f"ORDER-{purchase_id}",
        }
        self.tickets[purchase_id] = list(ticket_ids)
        self.sales.append({
            "purchase_id": purchase_id,
            "category": "paid",
            "amount": paid_amount,
        })
        row = {
            "id": len(self.refunds) + 1,
            "purchase_id": purchase_id,
            "ticket_ids": [],
            "amount_requested": request_amount,
            "amount_refunded": None,
            "currency": "UAH",
            "status": "pending",
            "requested_at": datetime.utcnow(),
            "requested_by": "customer",
            "reason": None,
            "admin_actor": None,
            "processed_at": None,
            "liqpay_refund_id": None,
            "liqpay_response": None,
            "fiscal_receipt_id": None,
            "fiscal_receipt_number": None,
            "fiscal_status": None,
            "failure_reason": None,
        }
        self.refunds.append(row)
        return row


def _request_tuple(r: dict[str, Any]) -> tuple:
    return (
        r["id"], r["purchase_id"], r["ticket_ids"], r["amount_requested"],
        r["amount_refunded"], r["currency"], r["status"], r["requested_at"],
        r["requested_by"], r["reason"], r["admin_actor"], r["processed_at"],
        r["liqpay_refund_id"], r["liqpay_response"], r["fiscal_receipt_id"],
        r["fiscal_receipt_number"], r["fiscal_status"], r["failure_reason"],
    )


class FakeCursor:
    def __init__(self, db: FakeDB) -> None:
        self.db = db
        self._results: list[Any] = []

    def _refund(self, request_id: int) -> dict[str, Any]:
        return next(r for r in self.db.refunds if r["id"] == request_id)

    def execute(self, query: str, params: Any = None) -> None:
        q = " ".join(query.split()).lower()
        p = params or ()
        self._results = []

        if q.startswith(("create table", "create index", "alter table")):
            return

        if q.startswith("select id, purchase_id, ticket_ids"):
            self._results = [
                _request_tuple(r) for r in self.db.refunds if r["id"] == p[0]
            ]
            return

        if q.startswith("select id, status, customer_name"):
            purchase = self.db.purchases.get(p[0])
            if purchase:
                self._results = [(
                    purchase["id"], purchase["status"], purchase["customer_name"],
                    purchase["customer_email"], purchase["payment_method"],
                    purchase["liqpay_order_id"],
                )]
            return

        if q.startswith("select id from ticket"):
            self._results = [(tid,) for tid in self.db.tickets.get(p[0], [])]
            return

        if q.startswith("select count(*) from ticket"):
            self._results = [(len(self.db.tickets.get(p[0], [])),)]
            return

        if q.startswith("select coalesce(sum(amount), 0) from sales"):
            total = sum(
                float(s["amount"])
                for s in self.db.sales
                if s["purchase_id"] == p[0] and s["category"] == "paid"
            )
            self._results = [(total,)]
            return

        if q.startswith("select coalesce(sum(amount_refunded), 0) from refund_request"):
            total = sum(
                float(r["amount_refunded"] or 0)
                for r in self.db.refunds
                if r["purchase_id"] == p[0] and r["status"] == "completed"
            )
            self._results = [(total,)]
            return

        if q.startswith("update refund_request set status='processing'"):
            self._refund(p[0])["status"] = "processing"
            return

        if "set liqpay_refund_id = coalesce" in q:
            lp_id, lp_resp, request_id = p
            row = self._refund(request_id)
            if lp_id:
                row["liqpay_refund_id"] = lp_id
            if lp_resp is not None:
                # jsonb round-trip: stored payload comes back as a dict
                row["liqpay_response"] = json.loads(lp_resp)
            return

        if "set liqpay_refund_id = %s" in q:
            lp_id, lp_resp, request_id = p
            row = self._refund(request_id)
            row["liqpay_refund_id"] = lp_id
            row["liqpay_response"] = json.loads(lp_resp) if lp_resp else None
            return

        if q.startswith("update refund_request set status = 'completed'"):
            (
                amount_refunded, lp_id, lp_resp,
                f_id, f_num, f_status, request_id,
            ) = p
            row = self._refund(request_id)
            row.update(
                status="completed",
                amount_refunded=amount_refunded,
                liqpay_refund_id=lp_id,
                liqpay_response=json.loads(lp_resp) if lp_resp else None,
                fiscal_receipt_id=f_id,
                fiscal_receipt_number=f_num,
                fiscal_status=f_status,
                processed_at=datetime.utcnow(),
                failure_reason=None,
            )
            return

        if q.startswith("update refund_request set status = 'failed'"):
            failure_reason, request_id = p
            row = self._refund(request_id)
            row.update(
                status="failed",
                failure_reason=failure_reason,
                processed_at=datetime.utcnow(),
            )
            return

        if q.startswith("insert into sales"):
            purchase_id, category, amount, _actor, _method = p
            self.db.sales.append({
                "purchase_id": purchase_id,
                "category": category,
                "amount": amount,
            })
            return

        # purchase/open_ticket status flips are irrelevant to these tests
        return

    def fetchone(self):
        return self._results[0] if self._results else None

    def fetchall(self):
        return list(self._results)

    def close(self) -> None:
        pass


class FakeConn:
    def __init__(self, db: FakeDB) -> None:
        self.db = db

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.db)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


class LiqPayStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []
        self.verify_calls: list[str] = []
        self.result: dict[str, Any] = {
            "status": "success",
            "payment_id": "2870201631",
            "refund_amount": 3500.0,
            "raw": {"status": "success"},
        }
        self.verify_result: dict[str, Any] | Exception = {
            "status": "success",
            "amount": 3500.0,
            "currency": "UAH",
        }

    def refund_payment(self, order_id, amount, comment=None):
        self.calls.append((order_id, amount))
        return dict(self.result)

    def verify_order(self, order_id):
        self.verify_calls.append(order_id)
        if isinstance(self.verify_result, Exception):
            raise self.verify_result
        return dict(self.verify_result)

    @staticmethod
    def is_refund_success(status):
        return (status or "").lower() in {"success", "ok", "sandbox", "reversed"}

    # Pure formatting helpers: reuse the real implementations.
    extract_error = staticmethod(real_liqpay.extract_error)
    describe_refund_result = staticmethod(real_liqpay.describe_refund_result)


class CheckboxStub:
    def __init__(self) -> None:
        self.calls: list[tuple[int, Any, float]] = []
        self.result: dict[str, Any] = {
            "receipt_id": "RFND-NEW",
            "fiscal_number": "FN-NEW",
            "status": "done",
        }
        self.error: Exception | None = None

    def is_enabled(self) -> bool:
        return True

    def create_refund_receipt(self, purchase_id, ticket_ids, amount):
        self.calls.append((purchase_id, ticket_ids, amount))
        if self.error:
            raise self.error
        return dict(self.result)


@pytest.fixture
def env(monkeypatch):
    db = FakeDB()
    liqpay_stub = LiqPayStub()
    checkbox_stub = CheckboxStub()
    monkeypatch.setattr(refund_admin, "get_connection", lambda: FakeConn(db))
    monkeypatch.setattr(refund_admin, "liqpay", liqpay_stub)
    monkeypatch.setattr(refund_admin, "checkbox_service", checkbox_stub)
    monkeypatch.setattr(refund_admin, "free_ticket", lambda cur, tid: None)
    monkeypatch.setattr(
        refund_admin.link_sessions,
        "revoke_ticket_sessions",
        lambda tid, conn=None: None,
    )
    return db, liqpay_stub, checkbox_stub


def _process(request_id: int, amount: float):
    return refund_admin._execute_refund(
        request_id,
        actor="admin",
        ticket_ids=[],
        refund_amount=amount,
        void_fiscal=True,
        comment=None,
        background_tasks=None,
    )


def test_retry_after_checkbox_failure_skips_liqpay(env, caplog):
    db, liqpay_stub, checkbox_stub = env
    req = db.seed(64, paid_amount=3500.0, ticket_ids=[1, 2], request_amount=3500.0)

    # First attempt: LiqPay succeeds, CheckBox returns 422 → request fails
    # with 502, but the LiqPay refund id must already be persisted.
    checkbox_stub.error = RuntimeError("422 Unprocessable Entity")
    with pytest.raises(HTTPException) as exc_info:
        _process(req["id"], 3500.0)
    assert exc_info.value.status_code == 502

    row = db.refunds[0]
    assert row["status"] == "failed"
    assert row["liqpay_refund_id"] == "2870201631"
    assert len(liqpay_stub.calls) == 1

    # Manual recovery (runbook step 1): reset the request to pending while
    # keeping liqpay_refund_id.
    row["status"] = "pending"
    row["processed_at"] = None
    row["failure_reason"] = None

    # Retry: LiqPay must be skipped, CheckBox now succeeds.
    checkbox_stub.error = None
    with caplog.at_level(logging.INFO, logger="backend.routers.refund_admin"):
        result = _process(req["id"], 3500.0)

    assert result["status"] == "completed"
    assert len(liqpay_stub.calls) == 1  # no second LiqPay refund
    assert len(checkbox_stub.calls) == 2
    assert row["liqpay_refund_id"] == "2870201631"
    assert row["fiscal_receipt_id"] == "RFND-NEW"
    assert row["fiscal_status"] == "done"
    assert any(
        "already done for request" in message for message in caplog.messages
    )


def test_refund_without_original_receipt_is_not_applicable(env):
    db, liqpay_stub, checkbox_stub = env
    req = db.seed(70, paid_amount=500.0, ticket_ids=[5], request_amount=500.0)

    # checkbox.create_refund_receipt skips the API when the purchase has no
    # checkbox_receipt_id and reports not_applicable (covered separately in
    # test_checkbox_refund.py); the admin flow must treat that as success.
    checkbox_stub.result = {
        "receipt_id": None,
        "fiscal_number": None,
        "status": "not_applicable",
    }

    result = _process(req["id"], 500.0)

    assert result["status"] == "completed"
    row = db.refunds[0]
    assert row["fiscal_status"] == "not_applicable"
    assert row["fiscal_receipt_id"] is None
    assert row["failure_reason"] is None
    assert len(liqpay_stub.calls) == 1


def test_rejected_liqpay_refund_records_code_description_and_order_state(env):
    """``status=error`` alone is untriageable — the row must carry the reason.

    Reproduces the production report: a partial refund (1350 of 1500) came
    back rejected and the admin UI could only show "status=error".
    """
    db, liqpay_stub, checkbox_stub = env
    req = db.seed(114, paid_amount=1500.0, ticket_ids=[161], request_amount=1500.0)

    liqpay_stub.result = {
        "status": "error",
        "err_code": "payment_not_found",
        "err_description": "Платіж не знайдено",
        "payment_id": None,
        "refund_amount": 1350.0,
        "raw": {
            "result": "error",
            "status": "error",
            "err_code": "payment_not_found",
            "err_description": "Платіж не знайдено",
        },
    }
    liqpay_stub.verify_result = {
        "status": "wait_accept",
        "amount": 1500.0,
        "currency": "UAH",
    }

    with pytest.raises(HTTPException) as exc_info:
        _process(req["id"], 1350.0)

    assert exc_info.value.status_code == 502
    detail = str(exc_info.value.detail)
    assert "code=payment_not_found" in detail
    assert "Платіж не знайдено" in detail
    # The order snapshot explains *why* LiqPay refused it.
    assert "order ORDER-114" in detail
    assert "status=wait_accept" in detail
    assert liqpay_stub.verify_calls == ["ORDER-114"]

    row = db.refunds[0]
    assert row["status"] == "failed"
    assert "payment_not_found" in row["failure_reason"]
    assert row["liqpay_refund_id"] is None  # no money moved
    assert row["liqpay_response"]["err_code"] == "payment_not_found"
    # A refused refund must never reach the fiscal step.
    assert checkbox_stub.calls == []


def test_liqpay_status_lookup_failure_still_reports_the_refusal(env):
    """The diagnostic lookup is best-effort and must not mask the error."""
    db, liqpay_stub, checkbox_stub = env
    req = db.seed(115, paid_amount=800.0, ticket_ids=[170], request_amount=800.0)

    liqpay_stub.result = {
        "status": "error",
        "err_code": "err_amount_limit",
        "err_description": None,
        "payment_id": None,
        "refund_amount": 800.0,
        "raw": {"status": "error", "err_code": "err_amount_limit"},
    }
    liqpay_stub.verify_result = RuntimeError("connection reset")

    with pytest.raises(HTTPException) as exc_info:
        _process(req["id"], 800.0)

    detail = str(exc_info.value.detail)
    assert "status=error" in detail
    assert "code=err_amount_limit" in detail
    assert db.refunds[0]["status"] == "failed"
