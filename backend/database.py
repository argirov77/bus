import os
import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Read the URL from the environment; if it's not set (e.g. in Docker),
# fall back to pointing at the "db" service on port 5433.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5433/test1"
)

# --- SQLAlchemy setup (if you use it elsewhere) ---
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- psycopg2 helper for your existing routers ---
def get_connection():
    """
    Returns a new psycopg2 connection using DATABASE_URL.
    All routers that do `get_connection()` will continue to work.
    """
    return psycopg2.connect(DATABASE_URL)
