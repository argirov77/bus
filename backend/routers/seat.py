from fastapi import APIRouter
from database import get_connection
from models import Seat, SeatCreate

router = APIRouter(prefix="/seats", tags=["seats"])

@router.get("/")
def get_seats():
    """
    Пример GET-запроса, который возвращает статический список или
    делает SELECT в таблице seats.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример запроса:
    # cur.execute("SELECT id, stop_name FROM stop ORDER BY id ASC;")
    # rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": 1, "placeholder_field": "Test Seat"}]

@router.post("/")
def create_seats(item: SeatCreate):
    """
    Пример POST-запроса, который вставляет запись в таблицу seats.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример INSERT:
    # cur.execute("INSERT INTO stop (stop_name) VALUES (%s) RETURNING id;", (item.stop_name,))
    # new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": 999, "placeholder_field": f"Created Seat"}
