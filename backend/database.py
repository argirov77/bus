import os
import time
from pathlib import Path
from threading import Lock
from typing import Iterator, Optional

import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.orm import sessionmaker

# Determine database host from environment. When running under docker-compose
# a DB_HOST variable is typically provided and points to the "db" service.
# For local development we fall back to "localhost" so the application can run
# against a local PostgreSQL instance without extra configuration.
DEFAULT_DB_HOST = os.getenv("DB_HOST", "localhost")


def _default_database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        f"postgresql://postgres:postgres@{DEFAULT_DB_HOST}:5432/test1",
    )


DATABASE_URL = _default_database_url()


def _admin_url(db_url: str) -> str:
    url = make_url(db_url)
    return str(url.set(database="postgres"))


DEFAULT_ADMIN_URL = _admin_url(DATABASE_URL)


def _candidate_urls(base_url: str) -> Iterator[str]:
    """Generate potential database URLs trying sensible host fallbacks.

    We start with the configured URL and progressively fall back to
    DB_HOST and localhost to support running outside docker-compose where the
    ``db`` hostname is unavailable.
    """

    seen: set[str] = set()
    url: URL = make_url(base_url)

    # Always try the exact URL first.
    original = str(url)
    if original not in seen:
        seen.add(original)
        yield original

    hosts: list[Optional[str]] = [url.host]
    for fallback in (DEFAULT_DB_HOST, "localhost"):
        if fallback not in hosts:
            hosts.append(fallback)

    ports: list[int] = []
    if url.port is not None:
        ports.append(url.port)
    # Honour optional overrides commonly used in docker-compose setups.
    for env_var in ("POSTGRES_HOST_PORT", "POSTGRES_PORT"):
        value = os.getenv(env_var)
        if value:
            try:
                port = int(value)
            except ValueError:
                continue
            if port not in ports:
                ports.append(port)
    # Fallback to the default docker-compose host mapping.
    if 5433 not in ports:
        ports.append(5433)
    if 5432 not in ports:
        ports.append(5432)

    for host in hosts:
        if host is None:
            continue
        for port in ports:
            candidate = str(url.set(host=host, port=port))
            if candidate not in seen:
                seen.add(candidate)
                yield candidate


def _create_database(db_url: str) -> None:
    admin_url = _admin_url(db_url)
    admin = psycopg2.connect(admin_url)
    admin.autocommit = True
    cur = admin.cursor()
    try:
        cur.execute(
            sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(make_url(db_url).database)
            )
        )
    finally:
        cur.close()
        admin.close()

    # give the server a moment to register the new database
    time.sleep(1)


def _ensure_database_exists() -> None:
    """Create the configured database if it doesn't exist.

    The function also gracefully falls back to localhost when the docker
    hostname (e.g. ``db``) is unavailable so the API can run in isolation
    during tests.
    """

    global DATABASE_URL, DEFAULT_ADMIN_URL

    last_exc: Optional[Exception] = None
    for candidate in _candidate_urls(DATABASE_URL):
        try:
            conn = psycopg2.connect(candidate)
            conn.close()
        except psycopg2.OperationalError as exc:
            message = str(exc)
            last_exc = exc
            if "does not exist" in message:
                _create_database(candidate)
                DATABASE_URL = candidate
                DEFAULT_ADMIN_URL = _admin_url(candidate)
                return
            # try next candidate host
            continue
        else:
            DATABASE_URL = candidate
            DEFAULT_ADMIN_URL = _admin_url(candidate)
            return

    if last_exc is not None:
        raise last_exc


def run_migrations() -> None:
    """Apply SQL migrations found in db/migrations."""
    migrations_dir = Path(__file__).resolve().parents[1] / "db" / "migrations"
    if not migrations_dir.exists():
        return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    for path in sorted(migrations_dir.glob("*.sql")):
        cur.execute("SELECT 1 FROM schema_migrations WHERE filename=%s", (path.name,))
        if cur.fetchone():
            continue
        with open(path, "r") as f:
            sql_statements = f.read()
        cur.execute(sql_statements)
        cur.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
        )
        conn.commit()
    cur.close()
    conn.close()


# --- SQLAlchemy setup (if you use it elsewhere) ---
engine = None  # Will be initialised lazily by _refresh_sqlalchemy_bindings().
SessionLocal = sessionmaker(autocommit=False, autoflush=False)

_database_ready = False
_ready_lock = Lock()


def _refresh_sqlalchemy_bindings() -> None:
    global engine
    engine = create_engine(DATABASE_URL, echo=True)
    SessionLocal.configure(bind=engine)


def _ensure_database_ready() -> None:
    """Ensure the database exists, migrations are applied and SQLAlchemy is configured."""

    global _database_ready
    if _database_ready:
        return

    with _ready_lock:
        if _database_ready:
            return
        _ensure_database_exists()
        run_migrations()
        _refresh_sqlalchemy_bindings()
        _database_ready = True


# --- psycopg2 helper for your existing routers ---

def get_connection():
    """Returns a new psycopg2 connection using DATABASE_URL.

    The connection's timezone is explicitly set to Bulgarian local time so that
    any timestamps produced by PostgreSQL (e.g. via ``NOW()``) reflect
    the desired ``UTC+3`` offset.
    """

    _ensure_database_ready()
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Europe/Sofia'")
    return conn
