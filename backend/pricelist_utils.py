"""Utility helpers for working with pricelist metadata."""

from __future__ import annotations

from typing import Any

from psycopg2.errors import UndefinedColumn

DEFAULT_CURRENCY = "UAH"


def ensure_pricelist_currency_column(conn: Any) -> None:
    """Ensure the ``currency`` column exists on the ``pricelist`` table.

    When running against an older database the ``currency`` column may be
    missing.  We create it on-the-fly so that newer features can rely on the
    column without breaking backwards compatibility.  The statement uses
    ``IF NOT EXISTS`` so it is safe to call repeatedly.
    """

    cur = conn.cursor()
    try:
        cur.execute(
            "ALTER TABLE pricelist "
            "ADD COLUMN IF NOT EXISTS currency character varying(16) "
            "NOT NULL DEFAULT 'UAH'"
        )
        if hasattr(conn, "commit"):
            conn.commit()
    finally:
        if hasattr(cur, "close"):
            cur.close()


def fetch_pricelist_currency(conn: Any, pricelist_id: int, default: str = DEFAULT_CURRENCY) -> str:
    """Fetch the currency for ``pricelist_id`` with graceful fallbacks."""

    for _ in range(2):
        cur = conn.cursor()
        try:
            cur.execute("SELECT currency FROM pricelist WHERE id = %s", (pricelist_id,))
            row = cur.fetchone()
            if not row:
                return default
            currency = row[0] or default
            return currency
        except UndefinedColumn:
            if hasattr(conn, "rollback"):
                conn.rollback()
            ensure_pricelist_currency_column(conn)
        except Exception:
            if hasattr(conn, "rollback"):
                conn.rollback()
            return default
        finally:
            if hasattr(cur, "close"):
                cur.close()
    return default
