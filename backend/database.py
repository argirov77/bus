import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/test")


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn
