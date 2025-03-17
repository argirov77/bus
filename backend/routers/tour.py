from fastapi import APIRouter
from database import get_connection
from models import Tour, TourCreate

router = APIRouter(prefix="/tours", tags=["tours"])

@router.get("/")
def get_tours():
    """
    Пример GET-запроса, который возвращает статический список или
    делает SELECT в таблице tours.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример запроса:
    # cur.execute("SELECT id, stop_name FROM stop ORDER BY id ASC;")
    # rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": 1, "placeholder_field": "Test Tour"}]

@router.post("/")
def create_tours(item: TourCreate):
    """
    Пример POST-запроса, который вставляет запись в таблицу tours.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример INSERT:
    # cur.execute("INSERT INTO stop (stop_name) VALUES (%s) RETURNING id;", (item.stop_name,))
    # new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": 999, "placeholder_field": f"Created Tour"}
