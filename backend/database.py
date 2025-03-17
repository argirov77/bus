import psycopg2

DATABASE_URL = "postgresql://postgres@localhost:5432/test"


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn
