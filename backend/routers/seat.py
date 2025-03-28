from fastapi import APIRouter, HTTPException, Query
from database import get_connection

router = APIRouter(prefix="/seat", tags=["seat"])

@router.get("/")
def get_seat_layout(
    tour_id: int = Query(...),
    departure_stop_id: int = Query(...),
    arrival_stop_id: int = Query(...)
):
    """
    Возвращает схему мест для заданного рейса и сегмента маршрута:
    - Все места (seat_num) из таблицы seat
    - Проверяем, какие уже заняты (ticket + JOIN seat)
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) Получаем все seat_num для данного tour_id
        cur.execute("""
            SELECT seat_num
            FROM seat
            WHERE tour_id = %s
            ORDER BY seat_num
        """, (tour_id,))
        all_seats = [row[0] for row in cur.fetchall()]

        # 2) Получаем занятые seat_num через JOIN
        cur.execute("""
            SELECT s.seat_num
            FROM ticket t
            JOIN seat s ON s.id = t.seat_id
            WHERE t.tour_id = %s
              AND t.departure_stop_id <= %s
              AND t.arrival_stop_id >= %s
        """, (tour_id, departure_stop_id, arrival_stop_id))
        booked_rows = cur.fetchall()
        booked_seats = {row[0] for row in booked_rows}

        # 3) Формируем схему: место доступно, если его нет в booked_seats
        layout = [
            {"seat_num": seat, "available": seat not in booked_seats}
            for seat in all_seats
        ]
        return layout
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
