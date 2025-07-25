import os
import time
import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Read the URL from the environment; if it's not set (e.g. in Docker),
# fall back to pointing at the "db" service on port 5432.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/test1",
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
