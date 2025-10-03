from __future__ import annotations

import os
import sys
from typing import Any, List, Tuple

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.ticket_utils import free_ticket
from backend.services import ticket_links


class StubCursor:
    def __init__(self):
        self._result: Any = None
        self.available = "12"
        self.jtis = ["jti-1", "jti-2"]
        self.queries: List[Tuple[str, Tuple[Any, ...]]] = []

    def execute(self, query, params=None):
        normalized = " ".join(query.split()).lower()
        self.queries.append((normalized, params or tuple()))
        if normalized.startswith("select tour_id"):
            self._result = (5, 7, 1, 3)
        elif "select jti from ticket_link_tokens" in normalized:
            self._result = [(jti,) for jti in self.jtis]
        elif normalized.startswith("select route_id"):
            self._result = (11,)
        elif "select stop_id from routestop" in normalized:
            self._result = [(1,), (2,), (3,)]
        elif normalized.startswith("select available from seat"):
            self._result = (self.available,)
        elif normalized.startswith("update seat set available"):
            self.available = params[0]
            self._result = None
        elif normalized.startswith("update available"):
            self._result = None
        elif normalized.startswith("delete from ticket"):
            self._result = None
        else:
            raise AssertionError(f"Unexpected query: {query}")

    def fetchone(self):
        if isinstance(self._result, list):
            if self._result:
                return self._result.pop(0)
            return None
        result = self._result
        self._result = None
        return result

    def fetchall(self):
        if isinstance(self._result, list):
            result = self._result
            self._result = None
            return result
        if self._result is None:
            return []
        result = [self._result]
        self._result = None
        return result


def test_free_ticket_revokes_tokens(monkeypatch):
    revoked: List[str] = []

    def fake_revoke(jti: str) -> bool:
        revoked.append(jti)
        return True

    monkeypatch.setattr(ticket_links, "revoke", fake_revoke)

    cursor = StubCursor()
    free_ticket(cursor, ticket_id=42)

    assert revoked == ["jti-1", "jti-2"]


def test_free_ticket_updates_available_like_booking(monkeypatch):
    monkeypatch.setattr(ticket_links, "revoke", lambda *_: True)

    cursor = StubCursor()
    free_ticket(cursor, ticket_id=99)

    updates = [
        params
        for query, params in cursor.queries
        if query.startswith("update available set seats = seats + 1")
    ]
    assert updates, "Expected available update query to be executed"
    assert updates[-1] == (5, 11, 11, 3, 11, 11, 1)
