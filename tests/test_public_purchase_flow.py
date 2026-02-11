import importlib
import os
import sys
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def public_client(monkeypatch):
    monkeypatch.setenv("APP_PUBLIC_URL", "https://example.test")
    monkeypatch.setenv("CLIENT_APP_BASE", "https://example.test")

    state = {
        "sessions": {},
        "redeem_calls": [],
        "get_calls": [],
        "touch_calls": [],
        "dto_calls": [],
        "render_calls": [],
        "verify_calls": [],
        "ticket_access": {},
        "view_session_calls": [],
    }

    class _DummyCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return None

        def fetchall(self):
            return []

        def close(self):
            return None

    class _DummyConnection:
        def __init__(self):
            self.autocommit = False

        def cursor(self):
            return _DummyCursor()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    def fake_connect(*_args, **_kwargs):
        return _DummyConnection()

    monkeypatch.setattr("psycopg2.connect", fake_connect)

    from backend.routers import public as public_module

    def fake_redeem_session(opaque, *, scope=None, conn=None):
        state["redeem_calls"].append((opaque, scope))
        return state["sessions"].get(opaque)

    def fake_get_session(opaque, *, scope=None, require_redeemed=False, conn=None):
        state["get_calls"].append((opaque, scope, require_redeemed))
        session = state["sessions"].get(opaque)
        if not session:
            return None
        if scope and session.scope != scope:
            return None
        if require_redeemed and session.redeemed is None:
            return None
        return session

    def fake_touch_session_usage(opaque, *, scope=None, conn=None):
        state["touch_calls"].append((opaque, scope))
        return state["sessions"].get(opaque)

    def fake_load_ticket_dto(ticket_id, lang, conn=None):
        state["dto_calls"].append((ticket_id, lang))
        return {"ticket": {"id": ticket_id}, "i18n": {"lang": lang}}

    def fake_render_ticket_pdf(dto, deep_link):
        state["render_calls"].append((dto, deep_link))
        return b"%PDF%"

    def fake_verify_ticket_purchase_access(ticket_id, purchase_id, email):
        state["verify_calls"].append((ticket_id, purchase_id, email))
        record = state["ticket_access"].get(ticket_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if record["purchase_id"] != purchase_id:
            raise HTTPException(status_code=403, detail="Ticket does not belong to purchase")
        if record["email"].strip().lower() != email.strip().lower():
            raise HTTPException(status_code=403, detail="Email does not match purchase")

    monkeypatch.setattr(
        public_module.link_sessions,
        "redeem_session",
        fake_redeem_session,
    )
    monkeypatch.setattr(
        public_module.link_sessions,
        "get_session",
        fake_get_session,
    )
    monkeypatch.setattr(
        public_module.link_sessions,
        "touch_session_usage",
        fake_touch_session_usage,
    )
    monkeypatch.setattr(
        public_module,
        "_load_ticket_dto",
        fake_load_ticket_dto,
    )
    monkeypatch.setattr(
        public_module,
        "render_ticket_pdf",
        fake_render_ticket_pdf,
    )
    
    def fake_get_or_create_view_session(
        ticket_id,
        *,
        purchase_id,
        lang,
        departure_dt,
        scopes=None,
        conn=None,
    ):
        state["view_session_calls"].append(
            (ticket_id, purchase_id, lang, departure_dt, tuple(scopes) if scopes else None)
        )
        return "opaque123", datetime.now(timezone.utc)

    monkeypatch.setattr(
        public_module,
        "get_or_create_view_session",
        fake_get_or_create_view_session,
    )
    monkeypatch.setattr(
        public_module,
        "_verify_ticket_purchase_access",
        fake_verify_ticket_purchase_access,
    )

    if "backend.main" in sys.modules:
        importlib.reload(sys.modules["backend.main"])
    else:
        importlib.import_module("backend.main")

    app = sys.modules["backend.main"].app
    return TestClient(app), state


def test_public_ticket_pdf_accepts_purchase_credentials(public_client):
    client, state = public_client

    ticket_id = 7
    purchase_id = 42
    email = "customer@example.com"
    state["ticket_access"][ticket_id] = {"purchase_id": purchase_id, "email": email}

    response = client.get(
        f"/public/tickets/{ticket_id}/pdf",
        params={"purchase_id": purchase_id, "email": email},
    )

    assert response.status_code == 200
    assert response.content == b"%PDF%"
    assert state["verify_calls"] == [(ticket_id, purchase_id, email)]
    assert state["dto_calls"][-1] == (ticket_id, "bg")
    assert state["view_session_calls"][-1][:4] == (ticket_id, purchase_id, "bg", None)
    assert state["render_calls"][-1][1].endswith("/q/opaque123")


def test_public_ticket_pdf_rejects_mismatched_purchase(public_client):
    client, state = public_client

    ticket_id = 11
    purchase_id = 77
    email = "customer@example.com"
    state["ticket_access"][ticket_id] = {"purchase_id": purchase_id, "email": email}

    response = client.get(
        f"/public/tickets/{ticket_id}/pdf",
        params={"purchase_id": purchase_id + 1, "email": email},
    )

    assert response.status_code == 403
    assert state["verify_calls"][-1] == (ticket_id, purchase_id + 1, email)


def test_public_ticket_pdf_rejects_wrong_email(public_client):
    client, state = public_client

    ticket_id = 19
    purchase_id = 105
    email = "customer@example.com"
    state["ticket_access"][ticket_id] = {"purchase_id": purchase_id, "email": email}

    response = client.get(
        f"/public/tickets/{ticket_id}/pdf",
        params={"purchase_id": purchase_id, "email": "other@example.com"},
    )

    assert response.status_code == 403
    assert state["verify_calls"][-1] == (ticket_id, purchase_id, "other@example.com")


def test_public_cancel_preview_returns_expected_amounts(public_client, monkeypatch):
    client, _state = public_client
    public_module = sys.modules["backend.routers.public"]

    class _DummySession:
        jti = "preview-jti"

    call_state: dict[str, Any] = {}

    def fake_require_purchase_context(request, purchase_id, scope):
        call_state["require_scope"] = scope
        call_state["require_purchase_id"] = purchase_id
        return _DummySession(), None, purchase_id, "cookie"

    class _DummyCursor:
        def close(self):
            call_state["cursor_closed"] = True

    class _DummyConnection:
        def cursor(self):
            call_state["cursor_requested"] = True
            return _DummyCursor()

        def close(self):
            call_state["connection_closed"] = True

    def fake_load_purchase_state(cur, purchase_id, *, for_update=False):
        call_state["load_state_args"] = (purchase_id, for_update)
        return 30.0, "reserved"

    def fake_plan_cancel(cur, purchase_id, ticket_ids, *, lock_tickets=False):
        call_state["plan_args"] = {
            "purchase_id": purchase_id,
            "ticket_ids": tuple(ticket_ids),
            "lock_tickets": lock_tickets,
        }
        return (
            [
                {"ticket_id": 101, "value": 10.0, "tour_id": 7, "extra_baggage": 0},
                {"ticket_id": 102, "value": 12.5, "tour_id": 7, "extra_baggage": 1},
            ],
            -22.5,
        )

    free_called: list[tuple[Any, ...]] = []

    def fake_free_ticket(*args, **kwargs):
        free_called.append(args)

    monkeypatch.setattr(public_module, "_require_purchase_context", fake_require_purchase_context)
    monkeypatch.setattr(public_module, "get_connection", lambda: _DummyConnection())
    monkeypatch.setattr(public_module, "_load_purchase_state", fake_load_purchase_state)
    monkeypatch.setattr(public_module, "_plan_cancel", fake_plan_cancel)
    monkeypatch.setattr(public_module, "free_ticket", fake_free_ticket)

    response = client.post(
        "/public/purchase/5/cancel/preview",
        json={"ticket_ids": [101, 102]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ticket_ids": [101, 102],
        "amount_delta": -22.5,
        "current_amount_due": 30.0,
        "new_amount_due": 7.5,
        "need_payment": True,
    }

    assert call_state["require_scope"] == "cancel_preview"
    assert call_state["require_purchase_id"] == 5
    assert call_state["cursor_closed"] is True
    assert call_state["connection_closed"] is True
    assert call_state["load_state_args"] == (5, False)
    assert call_state["plan_args"] == {
        "purchase_id": 5,
        "ticket_ids": (101, 102),
        "lock_tickets": False,
    }
    assert free_called == []
