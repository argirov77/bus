import json
import os
import sys
from datetime import datetime, timedelta, timezone

import jwt
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services import ticket_links


class FakeCursor:
    def __init__(self, store):
        self.store = store
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(query.split()).lower()
        if "insert into ticket_link_tokens" in normalized:
            jti, ticket_id, purchase_id, scopes_json, lang, expires_at = params
            self.store[jti] = {
                "ticket_id": ticket_id,
                "purchase_id": purchase_id,
                "scopes": json.loads(scopes_json),
                "lang": lang,
                "expires_at": expires_at,
                "revoked_at": None,
            }
            self._result = None
        elif "update ticket_link_tokens" in normalized and "set revoked_at" in normalized:
            now = datetime.now(timezone.utc)
            if "where ticket_id" in normalized:
                ticket_id = params[0]
                for entry in self.store.values():
                    if entry["ticket_id"] == ticket_id and entry["revoked_at"] is None:
                        entry["revoked_at"] = now
            elif "where jti" in normalized:
                jti = params[0]
                entry = self.store.get(jti)
                if entry and entry["revoked_at"] is None:
                    entry["revoked_at"] = now
            self._result = None
        elif "select revoked_at, expires_at from ticket_link_tokens" in normalized:
            jti = params[0]
            row = self.store.get(jti)
            if row:
                self._result = (row["revoked_at"], row["expires_at"])
            else:
                self._result = None
        elif "select jti from ticket_link_tokens" in normalized:
            if "where ticket_id" in normalized:
                ticket_id = params[0]
                rows = [
                    (jti,)
                    for jti, entry in self.store.items()
                    if entry["ticket_id"] == ticket_id and entry["revoked_at"] is None
                ]
                self._result = rows
            else:
                self._result = []
        else:
            raise AssertionError(f"Unexpected query: {query}")

    def fetchone(self):
        return self._result

    def fetchall(self):
        if isinstance(self._result, list):
            return list(self._result)
        return []


class FakeConnection:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return FakeCursor(self.store)

    def commit(self):
        pass

    def close(self):
        pass


class FakeDatabase:
    def __init__(self):
        self.tokens = {}

    def get_connection(self):
        return FakeConnection(self.tokens)


@pytest.fixture(autouse=True)
def configure_secret(monkeypatch):
    monkeypatch.setenv("TICKET_LINK_SECRET", "test-secret")
    monkeypatch.setenv("TICKET_LINK_TTL_DAYS", "3")


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDatabase()
    monkeypatch.setattr(ticket_links, "_get_connection", db.get_connection)
    return db


def test_issue_and_verify_roundtrip(monkeypatch, fake_db):
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(ticket_links, "_utcnow", lambda: now)

    token = ticket_links.issue(
        ticket_id=1,
        purchase_id=2,
        scopes=["download"],
        lang="en",
        departure_dt=now + timedelta(hours=2),
    )

    payload = ticket_links.verify(token)

    assert payload["ticket_id"] == 1
    assert payload["purchase_id"] == 2
    assert payload["scopes"] == ["download"]
    assert payload["lang"] == "en"
    assert "jti" in payload
    assert payload["exp"] > int(now.timestamp())


def test_issue_respects_ttl(monkeypatch, fake_db):
    now = datetime(2024, 5, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(ticket_links, "_utcnow", lambda: now)
    monkeypatch.setenv("TICKET_LINK_TTL_DAYS", "2")

    token = ticket_links.issue(
        ticket_id=10,
        purchase_id=None,
        scopes=["view"],
        lang="bg",
        departure_dt=now + timedelta(days=10),
    )

    payload = jwt.decode(
        token,
        "test-secret",
        algorithms=["HS256"],
        options={"verify_exp": False},
    )
    expected_exp = int((now + timedelta(days=2)).timestamp())
    assert payload["exp"] == expected_exp


def test_verify_blocks_revoked_tokens(monkeypatch, fake_db):
    now = datetime(2024, 6, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(ticket_links, "_utcnow", lambda: now)

    token = ticket_links.issue(
        ticket_id=11,
        purchase_id=22,
        scopes=["download"],
        lang="ru",
        departure_dt=now + timedelta(hours=6),
    )
    payload = jwt.decode(
        token,
        "test-secret",
        algorithms=["HS256"],
        options={"verify_exp": False},
    )
    jti = payload["jti"]
    fake_db.tokens[jti]["revoked_at"] = now

    with pytest.raises(ticket_links.TokenRevoked):
        ticket_links.verify(token)


def test_revoke_marks_token(monkeypatch, fake_db):
    now = datetime(2024, 7, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(ticket_links, "_utcnow", lambda: now)

    token = ticket_links.issue(
        ticket_id=100,
        purchase_id=200,
        scopes=["view"],
        lang="en",
        departure_dt=now + timedelta(hours=3),
    )
    payload = jwt.decode(
        token,
        "test-secret",
        algorithms=["HS256"],
        options={"verify_exp": False},
    )
    jti = payload["jti"]

    assert ticket_links.revoke(jti) is True
    assert fake_db.tokens[jti]["revoked_at"] is not None

    with pytest.raises(ticket_links.TokenRevoked):
        ticket_links.verify(token)


def test_issue_revokes_previous_tokens(monkeypatch, fake_db):
    now = datetime(2024, 8, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(ticket_links, "_utcnow", lambda: now)

    first_token = ticket_links.issue(
        ticket_id=300,
        purchase_id=None,
        scopes=["download"],
        lang="bg",
        departure_dt=now + timedelta(hours=4),
    )
    first_payload = jwt.decode(
        first_token,
        "test-secret",
        algorithms=["HS256"],
        options={"verify_exp": False},
    )
    first_jti = first_payload["jti"]

    # Issue a second token for the same ticket, which should revoke the first
    second_token = ticket_links.issue(
        ticket_id=300,
        purchase_id=None,
        scopes=["download"],
        lang="bg",
        departure_dt=now + timedelta(hours=5),
    )

    with pytest.raises(ticket_links.TokenRevoked):
        ticket_links.verify(first_token)

    second_payload = ticket_links.verify(second_token)
    assert second_payload["jti"] != first_jti
