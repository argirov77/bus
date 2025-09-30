from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import psycopg2


class _DummyPsycopgCursor:
    def __enter__(self):  # pragma: no cover - context helper
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - context helper
        return None

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        return None


class _DummyPsycopgConnection:
    def __init__(self):
        self.autocommit = False

    def cursor(self):
        return _DummyPsycopgCursor()

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


psycopg2.connect = lambda *args, **kwargs: _DummyPsycopgConnection()  # type: ignore

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services import link_sessions


def _normalize(sql: str) -> str:
    return " ".join(sql.split())


@dataclass
class DummyConnection:
    columns: dict[str, str]
    primary_key: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        self.queries: list[tuple[str, object]] = []

    def cursor(self) -> "DummyCursor":
        return DummyCursor(self)


class DummyCursor:
    def __init__(self, connection: DummyConnection) -> None:
        self.connection = connection
        self._result: list[tuple[str, str]] = []

    def __enter__(self) -> "DummyCursor":  # pragma: no cover - context helper
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - context helper
        return None

    def execute(self, query: str, params=None) -> None:
        normalized = _normalize(query)
        self.connection.queries.append((normalized, params))

        if "information_schema.columns" in normalized:
            self._result = list(self.connection.columns.items())
            return
        if "information_schema.table_constraints" in normalized:
            pk = self.connection.primary_key
            self._result = [pk] if pk else []
            return

        # adjust simple in-memory state when schema-changing commands are executed
        if "DROP CONSTRAINT" in normalized:
            self.connection.primary_key = None
        if "DROP COLUMN IF EXISTS id" in normalized:
            self.connection.columns.pop("id", None)
        if "DROP COLUMN IF EXISTS opaque" in normalized:
            self.connection.columns.pop("opaque", None)
        if "DROP COLUMN IF EXISTS token" in normalized:
            self.connection.columns.pop("token", None)

        self._result = []

    def fetchall(self):
        return list(self._result)

    def fetchone(self):
        return self._result[0] if self._result else None


def reset_schema_flag() -> None:
    link_sessions._SCHEMA_READY = False


def test_ensure_schema_creates_table_when_missing():
    reset_schema_flag()
    conn = DummyConnection(columns={})

    link_sessions._ensure_schema(conn)

    commands = [sql for sql, _ in conn.queries]
    assert any("CREATE TABLE IF NOT EXISTS link_sessions" in sql for sql in commands)
    assert any("CREATE INDEX IF NOT EXISTS idx_link_sessions_ticket_scope" in sql for sql in commands)
    assert any("CREATE INDEX IF NOT EXISTS idx_link_sessions_purchase_scope" in sql for sql in commands)


def test_ensure_schema_upgrades_legacy_layout():
    reset_schema_flag()
    conn = DummyConnection(
        columns={
            "id": "integer",
            "ticket_id": "integer",
            "scope": "character varying",
            "opaque": "character varying",
            "token": "text",
            "jti": "uuid",
            "expires_at": "timestamp with time zone",
            "created_at": "timestamp with time zone",
            "revoked_at": "timestamp with time zone",
        },
        primary_key=("link_sessions_pkey", "id"),
    )

    link_sessions._ensure_schema(conn)

    commands = [sql for sql, _ in conn.queries]
    assert any("ALTER TABLE link_sessions RENAME COLUMN expires_at TO exp" in sql for sql in commands)
    assert any("ALTER TABLE link_sessions RENAME COLUMN revoked_at TO revoked" in sql for sql in commands)
    assert any(
        "ALTER TABLE link_sessions ALTER COLUMN jti TYPE VARCHAR(255) USING jti::text"
        in sql
        for sql in commands
    )
    assert any("DROP COLUMN IF EXISTS opaque" in sql for sql in commands)
    assert any("DROP COLUMN IF EXISTS token" in sql for sql in commands)
    assert any("ADD COLUMN purchase_id INTEGER" in sql for sql in commands)
    assert any("ADD COLUMN redeemed TIMESTAMPTZ" in sql for sql in commands)
    assert any("ADD COLUMN used TIMESTAMPTZ" in sql for sql in commands)
    assert any("DROP COLUMN IF EXISTS id" in sql for sql in commands)
    assert any("ADD CONSTRAINT link_sessions_pkey PRIMARY KEY (jti)" in sql for sql in commands)
