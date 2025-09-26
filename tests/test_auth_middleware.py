import os
import sys
from typing import List
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import backend.auth as auth
from backend import jwt_utils


@pytest.fixture(autouse=True)
def configure_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def build_request(*, headers: dict[str, str] | None = None, query: dict[str, str] | None = None) -> Request:
    header_list = []
    if headers:
        header_list = [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in headers.items()
        ]
    query_string = b""
    if query:
        query_string = urlencode(query, doseq=True).encode()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "root_path": "",
        "query_string": query_string,
        "headers": header_list,
        "client": ("test", 1234),
        "server": ("testserver", 80),
    }

    async def receive():  # pragma: no cover - FastAPI request requires awaitable
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_request_without_token_denied():
    request = build_request()

    with pytest.raises(HTTPException) as exc_info:
        auth.get_request_context(request, credentials=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or missing ticket token"


@pytest.mark.anyio("asyncio")
async def test_request_with_link_token_sets_request_state(monkeypatch):
    expected_scopes: List[str] = ["download", "view"]
    payload = {
        "ticket_id": 42,
        "purchase_id": 7,
        "scopes": expected_scopes,
        "lang": "en",
        "jti": "test-jti",
        "exp": 1234567890,
    }

    def fake_verify(token: str):
        assert token == "good-token"
        return payload

    monkeypatch.setattr(auth.ticket_links, "verify", fake_verify)

    request = build_request(headers={"X-Ticket-Token": "good-token"})

    context = auth.get_request_context(request, credentials=None)

    assert context.is_admin is False
    assert context.link == payload
    assert context.scopes == expected_scopes
    assert context.ticket_id == payload["ticket_id"]
    assert context.purchase_id == payload["purchase_id"]
    assert context.lang == payload["lang"]
    assert context.jti == payload["jti"]
    assert getattr(request.state, "is_admin") is False
    assert getattr(request.state, "link_scopes") == expected_scopes
    assert getattr(request.state, "ticket_id") == payload["ticket_id"]
    assert getattr(request.state, "purchase_id") == payload["purchase_id"]
    assert getattr(request.state, "lang") == payload["lang"]
    assert getattr(request.state, "jti") == payload["jti"]
    assert getattr(request.state, "request_context") is context

    dependency = auth.require_scope("download")
    result = await dependency(request, context)
    assert result is context


@pytest.mark.anyio("asyncio")
async def test_request_with_admin_token(monkeypatch):
    verify_called = False

    def fake_verify(token: str):
        nonlocal verify_called
        verify_called = True
        raise AssertionError("link verify should not be called for admin token")

    monkeypatch.setattr(auth.ticket_links, "verify", fake_verify)

    token = jwt_utils.create_token({"role": "admin"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    request = build_request(headers={"authorization": f"Bearer {token}"})

    context = auth.get_request_context(request, credentials=credentials)

    assert context.is_admin is True
    assert context.admin["role"] == "admin"
    assert context.link is None
    assert context.scopes == []
    assert context.ticket_id is None
    assert context.purchase_id is None
    assert context.lang is None
    assert context.jti is None
    assert getattr(request.state, "is_admin") is True
    assert getattr(request.state, "link_scopes") == []
    assert getattr(request.state, "ticket_id") is None
    assert getattr(request.state, "purchase_id") is None
    assert getattr(request.state, "lang") is None
    assert getattr(request.state, "jti") is None
    assert getattr(request.state, "request_context") is context
    assert verify_called is False

    dependency = auth.require_scope("download")
    result = await dependency(request, context)
    assert result is context
