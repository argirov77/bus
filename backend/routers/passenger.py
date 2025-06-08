from fastapi import APIRouter
from ..database import get_connection
from ..models import Passenger, PassengerCreate

router = APIRouter(prefix="/passengers", tags=["passengers"])

@router.get("/")
def get_passengers():
    """
    Пример GET-запроса, который возвращает статический список или
    делает SELECT в таблице passengers.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример запроса:
    # cur.execute("SELECT id, stop_name FROM stop ORDER BY id ASC;")
    # rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": 1, "name": "Test Passenger"}]

@router.post("/")
def create_passengers(item: PassengerCreate):
    """
    Пример POST-запроса, который вставляет запись в таблицу passengers.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример INSERT:
    # cur.execute("INSERT INTO stop (stop_name) VALUES (%s) RETURNING id;", (item.stop_name,))
    # new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": 999, "name": f"Created Passenger"}
