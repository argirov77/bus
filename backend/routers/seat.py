# src/routers/seat.py

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional
from database import get_connection

router = APIRouter(prefix="/seat", tags=["seat"])


@router.get("/", response_model=Dict[str, List[Dict]])
def get_seat_layout(
    tour_id: int = Query(..., description="ID рейса"),
    departure_stop_id: Optional[int] = Query(None, description="ID отправной остановки"),
    arrival_stop_id:   Optional[int] = Query(None, description="ID конечной остановки"),
    adminMode:         bool = Query(False, description="true — вернуть все места без фильтра по сегменту"),
):
    """
    Возвращает схему мест для рейса.
    adminMode=true — возвращает все места (status: blocked/occupied/available).
    Иначе — фильтрует по сегменту departure_stop_id→arrival_stop_id.
    """
    if not adminMode and (departure_stop_id is None or arrival_stop_id is None):
        raise HTTPException(422, "departure_stop_id и arrival_stop_id обязательны для клиентского режима")

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Построим CTE booked — номера занятых кресел в нужном режиме
        if adminMode:
            booked_cte = """
                booked AS (
                  SELECT s.seat_num
                  FROM ticket t
                  JOIN seat s ON s.id = t.seat_id
                  WHERE t.tour_id = %s
                  GROUP BY s.seat_num
                )
            """
            params = [tour_id, tour_id]
        else:
            booked_cte = """
                booked AS (
                  SELECT s.seat_num
                  FROM ticket t
                  JOIN seat s ON s.id = t.seat_id
                  WHERE t.tour_id = %s
                    AND t.departure_stop_id <= %s
                    AND t.arrival_stop_id   >= %s
                  GROUP BY s.seat_num
                )
            """
            params = [tour_id, departure_stop_id, arrival_stop_id, tour_id]

        # Основной запрос: все кресла + LEFT JOIN на booked + вычисление статуса
        query = f"""
            WITH {booked_cte}
            SELECT
              s.id       AS seat_id,
              s.seat_num AS seat_num,
              CASE
                WHEN b.seat_num IS NOT NULL THEN 'occupied'
                WHEN s.available = '0'      THEN 'blocked'
                ELSE 'available'
              END AS status
            FROM seat s
            LEFT JOIN booked b
              ON b.seat_num = s.seat_num
            WHERE s.tour_id = %s
            ORDER BY s.seat_num;
        """

        cur.execute(query, params)
        rows = cur.fetchall()

        layout = [
            {"seat_id": r[0], "seat_num": r[1], "status": r[2]}
            for r in rows
        ]
        return {"seats": layout}

    except HTTPException:
        raise  # проброс наших ошибок
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@router.put("/block", response_model=Dict[str, str])
def block_seat(
    tour_id: int   = Query(..., description="ID рейса"),
    seat_num: int  = Query(..., description="Номер места"),
    block:    bool = Query(..., description="true — блокировать, false — разблокировать"),
):
    """
    Меняет состояние места:
      - block=true  → available = "0"
      - block=false → восстанавливает доступность (например, "1234…")
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        new_value = "0" if block else "1234"  # TODO: заменить на реальный расчёт доступных сегментов
        cur.execute(
            """
            UPDATE seat
            SET available = %s
            WHERE tour_id = %s AND seat_num = %s
            RETURNING seat_num, available;
            """,
            (new_value, tour_id, seat_num)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Seat not found")

        conn.commit()
        return {"seat_num": str(row[0]), "available": row[1]}

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()
