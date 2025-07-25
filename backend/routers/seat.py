# src/routers/seat.py

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Optional
from pydantic import BaseModel
from ..database import get_connection
from ..auth import get_current_admin

router = APIRouter(prefix="/seat", tags=["seat"])


class SeatInfo(BaseModel):
    seat_id: int
    seat_num: int
    status: str  # "available", "blocked" или "occupied"


class SeatLayout(BaseModel):
    seats: List[SeatInfo]


@router.get("/", response_model=SeatLayout)
def get_seat_layout(
    tour_id: int = Query(..., description="ID рейса"),
    departure_stop_id: Optional[int] = Query(None, description="ID отправной остановки"),
    arrival_stop_id:   Optional[int] = Query(None, description="ID конечной остановки"),
    adminMode:         bool = Query(False, description="true — вернуть все места без фильтра по сегменту"),
):
    """
    Возвращает схему мест для рейса.
    - adminMode=true — возвращает все места (status: occupied/blocked/available).
    - Иначе — возвращает только места, свободные на ВСЕХ сегментах departure→arrival (иначе blocked).
    """
    if not adminMode and (departure_stop_id is None or arrival_stop_id is None):
        raise HTTPException(422, "departure_stop_id и arrival_stop_id обязательны для клиентского режима")

    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) получаем route_id, проверяем тур
        cur.execute("SELECT route_id FROM tour WHERE id = %s", (tour_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Tour not found")
        route_id = row[0]

        # 2) получаем упорядоченный список остановок
        cur.execute(
            'SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY "order"',
            (route_id,)
        )
        stops = [r[0] for r in cur.fetchall()]

        # 3) если клиентский режим — вычисляем нужные сегменты
        segments: List[str] = []
        if not adminMode:
            if departure_stop_id not in stops or arrival_stop_id not in stops:
                raise HTTPException(400, "Invalid stops for this route")
            idx_from = stops.index(departure_stop_id)
            idx_to   = stops.index(arrival_stop_id)
            if idx_from >= idx_to:
                raise HTTPException(400, "Arrival must come after departure")
            # сегмент i соответствует промежутку stops[i]→stops[i+1], нумеруем с 1
            segments = [str(i+1) for i in range(idx_from, idx_to)]

        # 4) забираем все места рейса
        cur.execute(
            "SELECT id, seat_num, available FROM seat WHERE tour_id = %s ORDER BY seat_num",
            (tour_id,)
        )
        seats = cur.fetchall()

        # 5) в режиме админа — узнаём, какие места реально проданы
        sold: set[int] = set()
        if adminMode:
            cur.execute(
                "SELECT DISTINCT s.seat_num "
                "FROM ticket t JOIN seat s ON s.id=t.seat_id "
                "WHERE t.tour_id = %s",
                (tour_id,)
            )
            sold = {r[0] for r in cur.fetchall()}

        result: List[Dict] = []
        for seat_id, seat_num, avail_str in seats:
            status: str
            if adminMode:
                if seat_num in sold:
                    status = "occupied"
                else:
                    # если строка "0" — полностью заблокировано, иначе — available
                    status = "blocked" if avail_str == "0" else "available"
            else:
                # клиент: проверяем, что все нужные сегменты есть в available
                ok = all(seg in (avail_str or "") for seg in segments)
                status = "available" if ok else "blocked"

            result.append({
                "seat_id": seat_id,
                "seat_num": seat_num,
                "status": status
            })

        return {"seats": result}

    finally:
        cur.close()
        conn.close()


@router.put("/block", response_model=Dict[str, str])
def block_seat(
    tour_id: int   = Query(..., description="ID рейса"),
    seat_num: int  = Query(..., description="Номер места"),
    block:    bool = Query(..., description="true — блокировать, false — разблокировать"),
    current_admin: dict = Depends(get_current_admin),
):
    """
    Меняет состояние места:
      - block=true  → available = "0"
      - block=false → восстанавливает доступность (например, "1234…")
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        new_value = "0" if block else "1234"  # TODO: здесь можно вычислять полный перечень сегментов
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
