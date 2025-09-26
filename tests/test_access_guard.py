import os
import sys
from types import SimpleNamespace

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException

from backend.auth import RequestContext
from backend.services import access_guard


class DummyRequest:
    def __init__(self, ip: str = "127.0.0.1", token: str | None = None):
        self.headers: dict[str, str] = {}
        if token:
            self.headers["X-Ticket-Token"] = token
        self.client = SimpleNamespace(host=ip)


@pytest.fixture(autouse=True)
def reset_state():
    access_guard.reset_rate_limit_state()
    yield
    access_guard.reset_rate_limit_state()


def test_guard_public_request_enforces_rate_limit(monkeypatch):
    monkeypatch.setattr(access_guard, "RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(access_guard, "RATE_LIMIT_BURST", 1)
    monkeypatch.setattr(access_guard, "RATE_LIMIT_DELAY_SECONDS", 0.1)

    current = {"value": 0.0}

    def fake_time():
        return current["value"]

    sleeps: list[float] = []

    def fake_sleep(duration: float) -> None:
        sleeps.append(duration)

    monkeypatch.setattr(access_guard, "_time_fn", fake_time)
    monkeypatch.setattr(access_guard, "_sleep_fn", fake_sleep)

    context = RequestContext(
        is_admin=False,
        link=None,
        scopes=["view"],
        ticket_id=55,
        purchase_id=None,
        lang="bg",
        jti="rate-jti",
    )
    request = DummyRequest(ip="10.0.0.1")

    access_guard.guard_public_request(request, "view", ticket_id=55, context=context)
    access_guard.guard_public_request(request, "view", ticket_id=55, context=context)

    with pytest.raises(HTTPException) as exc:
        access_guard.guard_public_request(request, "view", ticket_id=55, context=context)

    assert exc.value.status_code == 429
    assert sleeps and sleeps[-1] == pytest.approx(0.1)

    current["value"] = 100.0
    access_guard.guard_public_request(request, "view", ticket_id=55, context=context)
