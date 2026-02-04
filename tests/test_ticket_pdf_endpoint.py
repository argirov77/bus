import importlib
import os
import sys
import types
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services import access_guard, ticket_links


@pytest.fixture(autouse=True)
def reset_rate_limit():
    access_guard.reset_rate_limit_state()
    yield
    access_guard.reset_rate_limit_state()


@pytest.fixture
def client(monkeypatch):

    state: Dict[str, Any] = {
        "link_payload": None,
    }

    class FakePsycopgCursor:
        def execute(self, *args, **kwargs) -> None:  # pragma: no cover - no-op
            pass

        def fetchone(self):  # pragma: no cover - default empty
            return None

        def fetchall(self):  # pragma: no cover - default empty
            return []

        def close(self) -> None:  # pragma: no cover - no-op
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakePsycopgConn:
        def __init__(self) -> None:
            self.closed = False
            self.autocommit = False

        def cursor(self) -> FakePsycopgCursor:
            return FakePsycopgCursor()

        def close(self) -> None:  # pragma: no cover - no-op
            self.closed = True

        def commit(self) -> None:  # pragma: no cover - no-op
            pass

    def fake_psycopg_connect(*args, **kwargs):  # pragma: no cover - deterministic stub
        return FakePsycopgConn()

    monkeypatch.setattr("psycopg2.connect", fake_psycopg_connect)

    class FakeImage:
        def save(self, buffer, format="PNG") -> None:  # pragma: no cover - no-op
            buffer.write(b"")

    class FakeQRCode:
        def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - no-op
            pass

        def add_data(self, data) -> None:  # pragma: no cover - no-op
            pass

        def make(self, fit=True) -> None:  # pragma: no cover - no-op
            pass

        def make_image(self, fill_color="black", back_color="white") -> FakeImage:
            return FakeImage()

    class FakeHTML:
        def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - no-op
            pass

        def write_pdf(self) -> bytes:  # pragma: no cover - default empty
            return b""

    class FakeTemplate:
        def render(self, **kwargs) -> str:  # pragma: no cover - default
            return ""

    class FakeEnvironment:
        def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - no-op
            pass

        def get_template(self, name: str) -> FakeTemplate:  # pragma: no cover - default
            return FakeTemplate()

    def fake_file_system_loader(*args, **kwargs):  # pragma: no cover - default
        return None

    def fake_select_autoescape(*args, **kwargs):  # pragma: no cover - default
        return None

    sys.modules.setdefault("qrcode", types.SimpleNamespace(QRCode=FakeQRCode))
    sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=FakeHTML))
    sys.modules.setdefault(
        "jinja2",
        types.SimpleNamespace(
            Environment=FakeEnvironment,
            FileSystemLoader=fake_file_system_loader,
            select_autoescape=fake_select_autoescape,
        ),
    )

    class DummyConn:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True
            state["connection_closed"] = True

    def fake_get_connection() -> DummyConn:
        conn = DummyConn()
        state["connection"] = conn
        state["connection_closed"] = False
        return conn

    def fake_get_ticket_dto(ticket_id: int, lang: str, conn: DummyConn) -> Dict[str, Any]:
        state["dto_call"] = {
            "ticket_id": ticket_id,
            "lang": lang,
            "conn": conn,
        }
        return {"ticket": {"id": ticket_id}, "i18n": {"lang": lang}}

    def fake_render_ticket_pdf(dto: Dict[str, Any], deep_link: Optional[str]) -> bytes:
        state["render_call"] = {
            "dto": dto,
            "deep_link": deep_link,
        }
        return b"%PDF-FAKE%"

    def fake_get_or_create_view_session(
        ticket_id: int,
        *,
        purchase_id: Optional[int],
        lang: str,
        departure_dt,
        scopes,
        conn=None,
    ) -> Tuple[str, datetime]:
        state["session_args"] = {
            "ticket_id": ticket_id,
            "purchase_id": purchase_id,
            "lang": lang,
            "departure_dt": departure_dt,
            "scopes": tuple(sorted(scopes)) if scopes else (),
        }
        counter = state.setdefault("session_counter", 0) + 1
        state["session_counter"] = counter
        return f"opaque-{counter}", datetime(2030, 1, 1, tzinfo=timezone.utc)

    def fake_build_deep_link(opaque: str, base_url: Optional[str] = None) -> str:
        state["built_link_args"] = (opaque, base_url)
        base = base_url or "https://example.test"
        return f"{base.rstrip('/')}/q/{opaque}"

    def fake_verify(token: str) -> Dict[str, Any]:
        state["verify_called_with"] = token
        payload = state.get("link_payload")
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            raise AssertionError("link_payload must be configured before verifying tokens")
        return payload

    if "backend.main" in sys.modules:
        importlib.reload(sys.modules["backend.main"])
    else:
        importlib.import_module("backend.main")

    app = sys.modules["backend.main"].app

    monkeypatch.setattr("backend.routers.ticket.get_connection", fake_get_connection)
    monkeypatch.setattr("backend.routers.ticket.get_ticket_dto", fake_get_ticket_dto)
    monkeypatch.setattr("backend.routers.ticket.render_ticket_pdf", fake_render_ticket_pdf)
    monkeypatch.setenv("TICKET_LINK_BASE_URL", "https://example.test")
    monkeypatch.setattr("backend.routers.ticket.get_or_create_view_session", fake_get_or_create_view_session)
    monkeypatch.setattr("backend.routers.ticket.build_deep_link", fake_build_deep_link)
    monkeypatch.setattr("backend.auth.ticket_links.verify", fake_verify)

    return TestClient(app), state


def test_ticket_pdf_allows_anonymous_access(client):
    cli, state = client

    response = cli.get("/tickets/55/pdf")

    assert response.status_code == 200
    assert response.content == b"%PDF-FAKE%"
    assert state["dto_call"]["ticket_id"] == 55
    assert state["dto_call"]["lang"] == "bg"
    assert state["session_args"]["scopes"] == ("view",)


def test_ticket_pdf_returns_pdf_for_valid_link_token(client):
    cli, state = client

    state["link_payload"] = {
        "ticket_id": 55,
        "purchase_id": None,
        "scopes": ["view"],
        "lang": "en",
        "jti": "test-jti",
        "exp": 1234567890,
    }

    response = cli.get("/tickets/55/pdf", params={"token": "good-token"})

    assert response.status_code == 200
    assert response.content == b"%PDF-FAKE%"
    assert response.headers["content-type"].startswith("application/pdf")
    assert "Content-Disposition" in response.headers
    assert "ticket-55.pdf" in response.headers["Content-Disposition"]

    assert state["dto_call"]["ticket_id"] == 55
    assert state["dto_call"]["lang"] == "en"
    deep_link = state["render_call"]["deep_link"]
    assert deep_link == "https://example.test/q/opaque-1"
    assert state["built_link_args"] == ("opaque-1", "https://example.test")
    assert state["verify_called_with"] == "good-token"
    assert state["connection_closed"] is True


def test_ticket_pdf_rejected_for_revoked_token(client):
    cli, state = client

    state["link_payload"] = ticket_links.TokenRevoked("revoked")

    response = cli.get("/tickets/55/pdf", params={"token": "revoked"})

    assert response.status_code == 401


def test_ticket_pdf_rate_limit(client, monkeypatch):
    cli, state = client

    monkeypatch.setattr(access_guard, "RATE_LIMIT_MAX_REQUESTS", 1)
    monkeypatch.setattr(access_guard, "RATE_LIMIT_BURST", 0)
    monkeypatch.setattr(access_guard, "RATE_LIMIT_DELAY_SECONDS", 0.0)

    state["link_payload"] = {
        "ticket_id": 55,
        "purchase_id": None,
        "scopes": ["view"],
        "lang": "en",
        "jti": "rate-limit-jti",
        "exp": 1234567890,
    }

    first = cli.get("/tickets/55/pdf", params={"token": "limit"})
    assert first.status_code == 200

    second = cli.get("/tickets/55/pdf", params={"token": "limit"})
    assert second.status_code == 429
def test_ticket_pdf_uses_query_lang_override(client):
    cli, state = client

    state["link_payload"] = {
        "ticket_id": 60,
        "purchase_id": None,
        "scopes": ["view"],
        "lang": "en",
        "jti": "lang-jti",
        "exp": 1234567890,
    }

    response = cli.get(
        "/tickets/60/pdf",
        params={"token": "good-token", "lang": "ua"},
    )

    assert response.status_code == 200
    assert state["dto_call"]["lang"] == "ua"

    state["link_payload"] = {
        "ticket_id": 61,
        "purchase_id": None,
        "scopes": ["view"],
        "lang": "bg",
        "jti": "lang-jti-2",
        "exp": 1234567890,
    }

    response = cli.get("/tickets/61/pdf", params={"token": "another-token"})

    assert response.status_code == 200
    assert state["dto_call"]["lang"] == "bg"
