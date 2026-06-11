"""Tests for the CheckBox shift state machine in ``_ensure_shift``.

The production failure mode: ``POST /api/v1/shifts`` returned 400 because the
cashier already had a shift that the old code did not recognise (only the
OPENED status was handled, and the initial check swallowed all errors).
``_ensure_shift`` must now cover every shift status: null, CREATED, OPENING,
OPENED, CLOSING, CLOSED.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services import checkbox


class _FakeResponse:
    def __init__(self, body: Any, status_code: int = 200, *, url: str = "", method: str = "GET") -> None:
        self._body = body
        self.status_code = status_code
        self.text = str(body)
        self.request = SimpleNamespace(method=method, url=url)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._body


class FakeHTTP:
    """URL-suffix-routed fake for httpx.get/post.

    Each GET route holds a queue of bodies; the queue is consumed one body per
    call and the last body repeats once the queue is down to a single entry.
    """

    def __init__(self) -> None:
        self.get_routes: dict[str, list[Any]] = {}
        self.post_responses: list[_FakeResponse] = []
        self.get_calls: list[str] = []
        self.post_calls: list[str] = []

    def get(self, url: str, headers=None, timeout=None) -> _FakeResponse:
        self.get_calls.append(url)
        for suffix, queue in self.get_routes.items():
            if url.endswith(suffix):
                body = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(body, _FakeResponse):
                    return body
                return _FakeResponse(body, url=url)
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, json=None, headers=None, timeout=None) -> _FakeResponse:
        self.post_calls.append(url)
        if not self.post_responses:
            raise AssertionError(f"unexpected POST {url}")
        return self.post_responses.pop(0)


@pytest.fixture
def http(monkeypatch):
    fake = FakeHTTP()
    monkeypatch.setattr("backend.services.checkbox.httpx.get", fake.get)
    monkeypatch.setattr("backend.services.checkbox.httpx.post", fake.post)
    monkeypatch.setattr(
        "backend.services.checkbox._auth_headers",
        lambda: {"Authorization": "Bearer test"},
    )
    monkeypatch.setattr("backend.services.checkbox.time.sleep", lambda s: None)
    monkeypatch.setattr(checkbox, "_active_shift_id", None)
    return fake


def test_opened_shift_is_reused(http):
    http.get_routes["/cashier/shift"] = [{"id": "S1", "status": "OPENED"}]

    assert checkbox._ensure_shift() == "S1"
    assert http.post_calls == []


def test_created_shift_is_awaited(http):
    http.get_routes["/cashier/shift"] = [{"id": "S2", "status": "CREATED"}]
    http.get_routes["/shifts/S2"] = [
        {"id": "S2", "status": "CREATED"},
        {"id": "S2", "status": "OPENED"},
    ]

    assert checkbox._ensure_shift() == "S2"
    assert http.post_calls == []


def test_no_shift_opens_new_one(http):
    http.get_routes["/cashier/shift"] = [None]  # JSON null body
    http.post_responses = [_FakeResponse({"id": "S3", "status": "CREATED"}, method="POST")]
    http.get_routes["/shifts/S3"] = [{"id": "S3", "status": "OPENED"}]

    assert checkbox._ensure_shift() == "S3"
    assert len(http.post_calls) == 1


def test_closed_shift_opens_new_one(http):
    http.get_routes["/cashier/shift"] = [{"id": "S0", "status": "CLOSED"}]
    http.post_responses = [_FakeResponse({"id": "S4", "status": "CREATED"}, method="POST")]
    http.get_routes["/shifts/S4"] = [{"id": "S4", "status": "OPENED"}]

    assert checkbox._ensure_shift() == "S4"
    assert len(http.post_calls) == 1


def test_closing_shift_waits_then_opens_new_one(http):
    http.get_routes["/cashier/shift"] = [{"id": "S5", "status": "CLOSING"}]
    http.get_routes["/shifts/S5"] = [
        {"id": "S5", "status": "CLOSING"},
        {"id": "S5", "status": "CLOSED"},
    ]
    http.post_responses = [_FakeResponse({"id": "S6", "status": "CREATED"}, method="POST")]
    http.get_routes["/shifts/S6"] = [{"id": "S6", "status": "OPENED"}]

    assert checkbox._ensure_shift() == "S6"
    assert len(http.post_calls) == 1


def test_post_400_falls_back_to_existing_shift(http):
    """The production failure: POST /shifts 400 because a shift already exists."""
    http.get_routes["/cashier/shift"] = [
        None,  # initial check sees nothing (stale/race)
        {"id": "S7", "status": "OPENING"},  # re-check after the 400
    ]
    http.post_responses = [
        _FakeResponse(
            {"message": "Зміна вже відкрита", "code": "shift_already_opened"},
            status_code=400,
            method="POST",
        )
    ]
    http.get_routes["/shifts/S7"] = [{"id": "S7", "status": "OPENED"}]

    assert checkbox._ensure_shift() == "S7"


def test_shift_closing_while_waiting_for_open_raises(http):
    http.get_routes["/cashier/shift"] = [{"id": "S8", "status": "CREATED"}]
    http.get_routes["/shifts/S8"] = [{"id": "S8", "status": "CLOSED"}]

    with pytest.raises(RuntimeError, match="moved to CLOSED"):
        checkbox._ensure_shift()
