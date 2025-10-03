import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def public_client(monkeypatch):
    state = {
        "sessions": {},
        "redeem_calls": [],
        "get_calls": [],
        "touch_calls": [],
        "dto_calls": [],
        "render_calls": [],
    }

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

    if "backend.main" in sys.modules:
        importlib.reload(sys.modules["backend.main"])
    else:
        importlib.import_module("backend.main")

    app = sys.modules["backend.main"].app
    return TestClient(app), state


def test_qr_redirect_sets_purchase_cookie_and_allows_ticket_pdf(public_client):
    from backend.services.link_sessions import LinkSession

    client, state = public_client

    now = datetime.now(timezone.utc)
    session = LinkSession(
        jti="opaque-test",
        ticket_id=7,
        purchase_id=42,
        scope="view",
        exp=now + timedelta(hours=1),
        redeemed=now,
        used=None,
        revoked=None,
        created_at=now,
    )
    state["sessions"][session.jti] = session

    response = client.get(f"/q/{session.jti}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3001/purchase/42"
    assert response.cookies.get("minicab_purchase_42") == session.jti
    assert state["redeem_calls"] == [(session.jti, "view")]

    pdf_response = client.get(f"/public/tickets/{session.ticket_id}/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.content == b"%PDF%"

    assert state["get_calls"][-1] == (session.jti, "view", True)
    assert state["touch_calls"][-1] == (session.jti, "view")
    assert state["dto_calls"][-1] == (session.ticket_id, "bg")
    assert state["render_calls"][-1][1] == f"http://localhost:8000/q/{session.jti}"
