from fastapi import APIRouter
from database import get_connection
from models import Ticket, TicketCreate

router = APIRouter(prefix="/tickets", tags=["tickets"])

@router.get("/")
def get_tickets():
    """
    Пример GET-запроса, возвращающего тестовый список билетов.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Здесь можно реализовать SELECT из таблицы ticket.
    cur.close()
    conn.close()
    return [{"id": 1, "placeholder_field": "Test Ticket"}]

@router.post("/")
def create_ticket(item: TicketCreate):
    """
    Пример POST-запроса, создающего билет.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Здесь можно реализовать INSERT в таблицу ticket.
    conn.commit()
    cur.close()
    conn.close()
    return {"id": 999, "placeholder_field": "Created Ticket"}
