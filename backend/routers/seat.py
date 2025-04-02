from fastapi import APIRouter, HTTPException, Query
from database import get_connection

router = APIRouter(prefix="/seat", tags=["seat"])

@router.get("/")
def get_seat_layout(
    tour_id: int = Query(..., description="ID рейса"),
    departure_stop_id: int = Query(..., description="ID отправной остановки"),
    arrival_stop_id: int = Query(..., description="ID конечной остановки")
):
    """
    Возвращает схему мест для заданного рейса и сегмента маршрута.
    
    Логика:
      1. Получаем все места (seat_num, available) для данного tour_id.
      2. Если поле available = "0", то место закрыто для продажи.
      3. Получаем номера мест, которые заняты (через ticket JOIN seat).
      4. Формируем схему: для каждого места, если оно активно (available ≠ "0")
         и не занято — available, иначе occupied или closed.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) Получаем все места для данного рейса
        cur.execute("""
            SELECT seat_num, available
            FROM seat
            WHERE tour_id = %s
            ORDER BY seat_num
        """, (tour_id,))
        seats_data = cur.fetchall()  # [(seat_num, available_str), ...]

        # 2) Получаем занятые места по билетам для заданного сегмента
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

        # 3) Формируем ответ
        layout = []
        for seat_num, available_str in seats_data:
            if available_str == "0":
                status = "closed"   # место деактивировано
            else:
                status = "available" if seat_num not in booked_seats else "occupied"
            layout.append({
                "seat_num": seat_num,
                "available": status,
                "raw_available": available_str  # можно убрать, если не нужно
            })
        return layout

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
