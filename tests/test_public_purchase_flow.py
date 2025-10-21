import importlib
import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def public_client(monkeypatch):
    state: dict[str, object] = {
        "ticket_rows": {},
        "dto_calls": [],
        "render_calls": [],
        "view_session_calls": [],
        "current_purchase_id": None,
    }

    class DummyPsycopgCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            return None

        def fetchone(self):
            return None

        def fetchall(self):
            return []

        def close(self):
            return None

    class DummyPsycopgConnection:
        def __init__(self):
            self.autocommit = False

        def cursor(self):
            return DummyPsycopgCursor()

        def close(self):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    monkeypatch.setattr("psycopg2.connect", lambda *args, **kwargs: DummyPsycopgConnection())

    from backend.routers import public as public_module

    class DummyCursor:
        def __init__(self, data_state: dict[str, object]):
            self._state = data_state
            self._params = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            self._params = params

        def fetchone(self):
            ticket_id = self._params[-1] if self._params else None
            rows = self._state.get("ticket_rows", {})
            return rows.get(ticket_id)

    class DummyConn:
        def __init__(self, data_state: dict[str, object]):
            self._state = data_state

        def cursor(self):
            return DummyCursor(self._state)

        def close(self):
            self._state["connection_closed"] = True

    def fake_get_connection():
        return DummyConn(state)

    def fake_load_ticket_dto(ticket_id, lang, conn=None):
        state["dto_calls"].append((ticket_id, lang))
        return {
            "ticket": {"id": ticket_id},
            "tour": {"date": "2024-01-02"},
            "segment": {"departure": {"time": "08:30"}},
            "purchase": {"id": state.get("current_purchase_id")},
        }

    def fake_render_ticket_pdf(dto, deep_link):
        state["render_calls"].append((dto, deep_link))
        return b"%PDF%"

    def fake_get_or_create_view_session(
        ticket_id,
        *,
        purchase_id,
        lang,
        departure_dt,
        scopes,
        conn=None,
    ):
        state["view_session_calls"].append(
            {
                "ticket_id": ticket_id,
                "purchase_id": purchase_id,
                "lang": lang,
                "departure_dt": departure_dt,
                "scopes": set(scopes) if scopes else set(),
            }
        )
        return "opaque-test", datetime.now(timezone.utc)

    monkeypatch.setattr(public_module, "get_connection", fake_get_connection)
    monkeypatch.setattr(public_module, "_load_ticket_dto", fake_load_ticket_dto)
    monkeypatch.setattr(public_module, "render_ticket_pdf", fake_render_ticket_pdf)
    monkeypatch.setattr(
        public_module, "get_or_create_view_session", fake_get_or_create_view_session
    )

    if "backend.main" in sys.modules:
        importlib.reload(sys.modules["backend.main"])
    else:
        importlib.import_module("backend.main")

    app = sys.modules["backend.main"].app
    return TestClient(app), state


def _prepare_ticket(state, *, ticket_id: int, purchase_id: int, email: str, lang: str = "bg"):
    rows = state.setdefault("ticket_rows", {})
    rows[ticket_id] = (purchase_id, email, lang)
    state["current_purchase_id"] = purchase_id


def test_public_ticket_pdf_renders_with_matching_details(public_client):
    client, state = public_client
    _prepare_ticket(state, ticket_id=7, purchase_id=42, email="Customer@example.com", lang="BG")

    response = client.post(
        "/public/tickets/pdf",
        json={
            "ticket_id": 7,
            "purchase_id": 42,
            "purchaser_email": "customer@example.com",
        },
    )

    assert response.status_code == 200
    assert response.content == b"%PDF%"
    assert state["dto_calls"][-1] == (7, "bg")
    view_call = state["view_session_calls"][-1]
    assert view_call["ticket_id"] == 7
    assert view_call["purchase_id"] == 42
    assert view_call["lang"] == "bg"
    assert view_call["scopes"] == {"view"}
    assert view_call["departure_dt"] is not None
    assert state["render_calls"][-1][1] == "http://localhost:8000/q/opaque-test"


def test_public_ticket_pdf_rejects_mismatched_email(public_client):
    client, state = public_client
    _prepare_ticket(state, ticket_id=5, purchase_id=99, email="owner@example.com")

    response = client.post(
        "/public/tickets/pdf",
        json={
            "ticket_id": 5,
            "purchase_id": 99,
            "purchaser_email": "other@example.com",
        },
    )

    assert response.status_code == 403
    assert state["view_session_calls"] == []


def test_public_ticket_pdf_rejects_wrong_purchase(public_client):
    client, state = public_client
    _prepare_ticket(state, ticket_id=3, purchase_id=77, email="owner@example.com")

    response = client.post(
        "/public/tickets/pdf",
        json={
            "ticket_id": 3,
            "purchase_id": 100,
            "purchaser_email": "owner@example.com",
        },
    )

    assert response.status_code == 404
    assert state["view_session_calls"] == []
