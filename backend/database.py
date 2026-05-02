import os
import time
import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Determine database host from environment. When running under docker-compose
# a DB_HOST variable is typically provided and points to the "db" service.
# For local development we fall back to "localhost" so the application can run
# against a local PostgreSQL instance without extra configuration.
DEFAULT_DB_HOST = os.getenv("DB_HOST", "localhost")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://busapp:busapp@{DEFAULT_DB_HOST}:5432/bustickets",
)

# Derive admin connection string to the default "postgres" database
DEFAULT_ADMIN_URL = DATABASE_URL.rsplit("/", 1)[0] + "/postgres"


def _ensure_database_exists() -> None:
    """Create the configured database if it doesn't exist."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.close()
    except psycopg2.OperationalError as exc:
        if "does not exist" not in str(exc):
            raise

        db_name = DATABASE_URL.rsplit("/", 1)[-1]
        admin = psycopg2.connect(DEFAULT_ADMIN_URL)
        admin.autocommit = True
        cur = admin.cursor()
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        cur.close()
        admin.close()

        # give the server a moment to register the new database
        time.sleep(1)


_ensure_database_exists()

# --- SQLAlchemy setup (if you use it elsewhere) ---
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- psycopg2 helper for your existing routers ---

def get_connection():
    """Returns a new psycopg2 connection using DATABASE_URL.

    The connection's timezone is explicitly set to Bulgarian local time so that
    any timestamps produced by PostgreSQL (e.g. via ``NOW()``) reflect
    the desired ``UTC+3`` offset.
    """
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Europe/Sofia'")
    return conn

from pathlib import Path


def _ensure_purchase_schema_compatibility(cur) -> None:
    """Backfill critical purchase columns when historical migrations were marked but not applied."""
    cur.execute("ALTER TYPE public.payment_method_type ADD VALUE IF NOT EXISTS 'liqpay'")
    cur.execute(
        """
        ALTER TABLE public.purchase
            ADD COLUMN IF NOT EXISTS liqpay_order_id TEXT,
            ADD COLUMN IF NOT EXISTS liqpay_status TEXT,
            ADD COLUMN IF NOT EXISTS liqpay_payment_id TEXT,
            ADD COLUMN IF NOT EXISTS liqpay_payload JSONB,
            ADD COLUMN IF NOT EXISTS fiscal_status TEXT DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS checkbox_receipt_id TEXT,
            ADD COLUMN IF NOT EXISTS checkbox_fiscal_code TEXT,
            ADD COLUMN IF NOT EXISTS fiscal_last_error TEXT,
            ADD COLUMN IF NOT EXISTS fiscal_attempts INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS fiscalized_at TIMESTAMP
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS purchase_liqpay_order_id_uidx
            ON public.purchase (liqpay_order_id)
            WHERE liqpay_order_id IS NOT NULL
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS purchase_fiscal_status_pending_idx
            ON public.purchase (id)
            WHERE fiscal_status IN ('pending', 'failed')
        """
    )


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

    _ensure_purchase_schema_compatibility(cur)
    conn.commit()
    cur.close()
    conn.close()


run_migrations()
