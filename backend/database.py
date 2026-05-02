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


def _ensure_schema_migrations_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    conn.commit()


def run_migrations() -> None:
    """Apply SQL migrations found in db/migrations."""
    migrations_dir = Path(__file__).resolve().parents[1] / "db" / "migrations"
    conn = psycopg2.connect(DATABASE_URL)
    _ensure_schema_migrations_table(conn)

    if not migrations_dir.exists():
        conn.close()
        return

    cur = conn.cursor()
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


REQUIRED_MIGRATIONS = (
    "018_add_liqpay_tracking.sql",
    "019_liqpay_payment_method_and_tracking.sql",
    "021_guard_liqpay_tracking_columns.sql",
)


def validate_required_migrations() -> None:
    """Fail fast when critical schema revisions are missing."""
    conn = psycopg2.connect(DATABASE_URL)
    _ensure_schema_migrations_table(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT filename
        FROM schema_migrations
        WHERE filename = ANY(%s)
        """,
        (list(REQUIRED_MIGRATIONS),),
    )
    applied = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()

    missing = [name for name in REQUIRED_MIGRATIONS if name not in applied]
    if missing:
        required_revision = REQUIRED_MIGRATIONS[-1]
        raise RuntimeError(
            "Database schema is outdated: required migration revision "
            f"{required_revision} is missing dependencies {missing}. "
            "Run project migrations in the backend runtime environment."
        )


run_migrations()
validate_required_migrations()
