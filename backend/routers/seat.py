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
    Состояния:
      - "blocked": если место заблокировано (available = "0")
      - "occupied": если место занято (есть билет)
      - "available": если место активно и свободно
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Получаем все места для данного рейса
        cur.execute("""
            SELECT seat_num, available
            FROM seat
            WHERE tour_id = %s
            ORDER BY seat_num
        """, (tour_id,))
        seats_data = cur.fetchall()

        # 2. Получаем занятые места (из таблицы ticket) для выбранного сегмента
        cur.execute("""
            SELECT s.seat_num
            FROM ticket t
            JOIN seat s ON s.id = t.seat_id
            WHERE t.tour_id = %s
              AND t.departure_stop_id <= %s
              AND t.arrival_stop_id >= %s
        """, (tour_id, departure_stop_id, arrival_stop_id))
        booked_seats = {row[0] for row in cur.fetchall()}

        # 3. Формируем ответ для каждого места:
        #    Если available == "0" -> "blocked"
        #    Если seat_num в booked_seats -> "occupied"
        #    Иначе -> "available"
        layout = []
        for seat_num, available_str in seats_data:
            if available_str == "0":
                status = "blocked"
            elif seat_num in booked_seats:
                status = "occupied"
            else:
                status = "available"
            layout.append({
                "seat_num": seat_num,
                "status": status
            })

        return {"seats": layout}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.put("/block")
def block_seat(
    tour_id: int,
    seat_num: int,
    block: bool = Query(..., description="true для блокировки, false для разблокировки")
):
    """
    Меняет состояние места: блокирует (available = "0") или разблокирует (восстанавливает full available string).
    Для примера при разблокировке восстанавливается значение "1234" – в реальном применении оно должно вычисляться на основе маршрута.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        if block:
            new_value = "0"
        else:
            # Восстанавливаем значение, например, "1234". (Это значение нужно вычислить в зависимости от маршрута)
            new_value = "1234"
        cur.execute("""
            UPDATE seat
            SET available = %s
            WHERE tour_id = %s AND seat_num = %s
            RETURNING seat_num, available;
        """, (new_value, tour_id, seat_num))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Место не найдено")
        conn.commit()
        return {"seat_num": row[0], "available": row[1]}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
