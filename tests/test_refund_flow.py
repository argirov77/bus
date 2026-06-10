"""Integration-style tests for the refund-request workflow.

These exercise the helper layer in ``backend.services.refund`` with a small
in-memory cursor that emulates just enough SQL behaviour to drive the
state machine: paid amount → multiple partial refunds → completion.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any, Sequence

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services import refund


class FakeDB:
    """Minimal in-memory store keyed by purchase_id, sales rows, refund rows."""

    def __init__(self) -> None:
        self.purchases: dict[int, dict[str, Any]] = {}
        self.sales: list[dict[str, Any]] = []
        self.refunds: list[dict[str, Any]] = []
        self._next_refund_id = 1

    def seed_purchase(self, purchase_id: int, *, paid_amount: float) -> None:
        self.purchases[purchase_id] = {
            "id": purchase_id,
            "status": "paid",
            "customer_name": "Test User",
            "customer_email": "test@example.com",
            "amount_due": 0.0,
        }
        self.sales.append({
            "purchase_id": purchase_id,
            "category": "paid",
            "amount": paid_amount,
        })


class FakeCursor:
    def __init__(self, db: FakeDB) -> None:
        self.db = db
        self._last_query = ""
        self._last_params: Any = None
        self._results: list[Any] = []

    def execute(self, query: str, params: Any = None) -> None:
        self._last_query = " ".join(query.split())
        self._last_params = params or ()
        q = self._last_query.lower()
        self._results = []

        if q.startswith("create table") or q.startswith("create index") or q.startswith("alter table"):
            return

        if q.startswith("select coalesce(sum(amount), 0) from sales"):
            purchase_id = params[0]
            total = sum(
                float(s["amount"])
                for s in self.db.sales
                if s["purchase_id"] == purchase_id and s["category"] == "paid"
            )
            self._results = [(total,)]
            return

        if q.startswith("select coalesce(sum(amount_refunded), 0) from refund_request"):
            purchase_id = params[0]
            total = sum(
                float(r.get("amount_refunded") or 0)
                for r in self.db.refunds
                if r["purchase_id"] == purchase_id and r["status"] == "completed"
            )
            self._results = [(total,)]
            return

        if q.startswith("insert into refund_request"):
            (
                purchase_id,
                ticket_ids,
                amount_requested,
                currency,
                requested_by,
                reason,
                admin_actor,
            ) = params
            row = {
                "id": self.db._next_refund_id,
                "purchase_id": purchase_id,
                "ticket_ids": list(ticket_ids),
                "amount_requested": amount_requested,
                "amount_refunded": None,
                "currency": currency,
                "status": "pending",
                "requested_at": datetime.utcnow(),
                "requested_by": requested_by,
                "reason": reason,
                "admin_actor": admin_actor,
                "processed_at": None,
                "liqpay_refund_id": None,
                "liqpay_response": None,
                "fiscal_receipt_id": None,
                "fiscal_receipt_number": None,
                "fiscal_status": None,
                "failure_reason": None,
            }
            self.db.refunds.append(row)
            self.db._next_refund_id += 1
            self._results = [(row["id"], row["requested_at"])]
            return

        if q.startswith("update purchase set refund_requested_at"):
            return

        if q.startswith("select id, purchase_id, ticket_ids") and "where purchase_id" in q and "status in" in q:
            purchase_id = params[0]
            candidates = [
                r for r in self.db.refunds
                if r["purchase_id"] == purchase_id and r["status"] in {"pending", "processing"}
            ]
            self._results = [_row_tuple(c) for c in candidates]
            return

        if q.startswith("select id, purchase_id, ticket_ids") and "where id =" in q:
            request_id = params[0]
            matches = [r for r in self.db.refunds if r["id"] == request_id]
            self._results = [_row_tuple(m) for m in matches]
            return

        if q.startswith("update refund_request set status='processing'"):
            request_id = params[0]
            for r in self.db.refunds:
                if r["id"] == request_id:
                    r["status"] = "processing"
            return

        if q.startswith("update refund_request set status = 'completed'"):
            (
                amount_refunded,
                liqpay_refund_id,
                liqpay_response,
                fiscal_receipt_id,
                fiscal_receipt_number,
                fiscal_status,
                request_id,
            ) = params
            for r in self.db.refunds:
                if r["id"] == request_id:
                    r["status"] = "completed"
                    r["amount_refunded"] = amount_refunded
                    r["liqpay_refund_id"] = liqpay_refund_id
                    r["liqpay_response"] = liqpay_response
                    r["fiscal_receipt_id"] = fiscal_receipt_id
                    r["fiscal_receipt_number"] = fiscal_receipt_number
                    r["fiscal_status"] = fiscal_status
                    r["processed_at"] = datetime.utcnow()
                    r["failure_reason"] = None
            return

        if q.startswith("update refund_request set status = 'failed'"):
            failure_reason, request_id = params
            for r in self.db.refunds:
                if r["id"] == request_id:
                    r["status"] = "failed"
                    r["failure_reason"] = failure_reason
                    r["processed_at"] = datetime.utcnow()
            return

        if q.startswith("update refund_request set status = 'rejected'"):
            admin_actor, reason, request_id = params
            for r in self.db.refunds:
                if r["id"] == request_id:
                    r["status"] = "rejected"
                    if admin_actor:
                        r["admin_actor"] = admin_actor
                    r["failure_reason"] = reason
                    r["processed_at"] = datetime.utcnow()
            return

        # Anything else: noop, no results.
        return

    def fetchone(self):
        return self._results[0] if self._results else None

    def fetchall(self):
        return list(self._results)

    def close(self) -> None:
        pass


def _row_tuple(r: dict[str, Any]) -> tuple:
    return (
        r["id"], r["purchase_id"], r["ticket_ids"], r["amount_requested"],
        r["amount_refunded"], r["currency"], r["status"], r["requested_at"],
        r["requested_by"], r["reason"], r["admin_actor"], r["processed_at"],
        r["liqpay_refund_id"], r["liqpay_response"], r["fiscal_receipt_id"],
        r["fiscal_receipt_number"], r["fiscal_status"], r["failure_reason"],
    )


def test_remaining_after_partial_refund_then_completion():
    db = FakeDB()
    db.seed_purchase(42, paid_amount=1500.0)
    cur = FakeCursor(db)

    assert refund.compute_paid_amount(cur, 42) == 1500.0
    assert refund.compute_remaining(cur, 42) == 1500.0

    # Customer creates a request for 1 ticket worth 500
    req1 = refund.create_request(
        cur,
        purchase_id=42,
        ticket_ids=[101],
        amount_requested=500.0,
        currency="UAH",
        requested_by="customer",
        reason="want refund",
    )
    assert req1["id"] >= 1
    assert refund.find_active_request(cur, 42)["id"] == req1["id"]

    # Admin processes it — mark completed
    refund.mark_processing(cur, req1["id"])
    refund.mark_completed(
        cur,
        req1["id"],
        amount_refunded=500.0,
        liqpay_refund_id="LIQP-1",
        liqpay_response={"status": "success"},
        fiscal_receipt_id="R-1",
        fiscal_receipt_number="FN-1",
        fiscal_status="done",
    )
    assert refund.compute_completed_refunds(cur, 42) == 500.0
    assert refund.compute_remaining(cur, 42) == 1000.0
    assert refund.find_active_request(cur, 42) is None

    # Second refund for remaining 1000
    req2 = refund.create_request(
        cur,
        purchase_id=42,
        ticket_ids=[102, 103],
        amount_requested=1000.0,
        currency="UAH",
        requested_by="admin",
        reason=None,
        admin_actor="alice",
    )
    refund.mark_processing(cur, req2["id"])
    refund.mark_completed(
        cur,
        req2["id"],
        amount_refunded=1000.0,
        liqpay_refund_id="LIQP-2",
        liqpay_response={"status": "success"},
        fiscal_receipt_id="R-2",
        fiscal_receipt_number="FN-2",
        fiscal_status="done",
    )
    assert refund.compute_remaining(cur, 42) == 0.0


def test_rejected_request_does_not_count_towards_refunds():
    db = FakeDB()
    db.seed_purchase(7, paid_amount=200.0)
    cur = FakeCursor(db)

    req = refund.create_request(
        cur,
        purchase_id=7,
        ticket_ids=[1],
        amount_requested=200.0,
        currency="UAH",
        requested_by="customer",
        reason=None,
    )
    refund.mark_rejected(cur, req["id"], admin_actor="bob", reason="duplicate")

    assert refund.compute_completed_refunds(cur, 7) == 0.0
    assert refund.compute_remaining(cur, 7) == 200.0
    assert refund.find_active_request(cur, 7) is None


def test_failed_request_keeps_remaining_intact():
    db = FakeDB()
    db.seed_purchase(8, paid_amount=300.0)
    cur = FakeCursor(db)

    req = refund.create_request(
        cur,
        purchase_id=8,
        ticket_ids=[],
        amount_requested=100.0,
        currency="UAH",
        requested_by="admin",
        reason=None,
        admin_actor="ops",
    )
    refund.mark_processing(cur, req["id"])
    refund.mark_failed(cur, req["id"], "LiqPay timeout")

    assert refund.compute_completed_refunds(cur, 8) == 0.0
    assert refund.compute_remaining(cur, 8) == 300.0
