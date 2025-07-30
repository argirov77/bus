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
    f"postgresql://postgres:postgres@{DEFAULT_DB_HOST}:5432/test1",
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
    """Returns a new psycopg2 connection using DATABASE_URL."""
    return psycopg2.connect(DATABASE_URL)

from pathlib import Path


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


run_migrations()
