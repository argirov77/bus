from fastapi import APIRouter
from database import get_connection
from models import Pricelist, PricelistCreate

router = APIRouter(prefix="/pricelists", tags=["pricelists"])

@router.get("/")
def get_pricelists():
    """
    Пример GET-запроса, который возвращает статический список или
    делает SELECT в таблице pricelists.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример запроса:
    # cur.execute("SELECT id, stop_name FROM stop ORDER BY id ASC;")
    # rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": 1, "name": "Test Pricelist"}]

@router.post("/")
def create_pricelists(item: PricelistCreate):
    """
    Пример POST-запроса, который вставляет запись в таблицу pricelists.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример INSERT:
    # cur.execute("INSERT INTO stop (stop_name) VALUES (%s) RETURNING id;", (item.stop_name,))
    # new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": 999, "name": f"Created Pricelist"}
