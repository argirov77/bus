from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime
from database import get_connection

router = APIRouter(prefix="/tours", tags=["tours"])

class TourCreate(BaseModel):
    route_id: int
    pricelist_id: int
    date: date
    layout_variant: int  # выбранный layout автобуса
    active_seats: List[int]  # активированные места для продажи

class Tour(BaseModel):
    id: int
    route_id: int
    pricelist_id: int
    date: date
    layout_variant: int
    class Config:
        orm_mode = True

@router.get("/", response_model=List[Tour])
def get_tours():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, route_id, pricelist_id, date, layout_variant FROM tour ORDER BY date;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "route_id": r[1], "pricelist_id": r[2], "date": r[3], "layout_variant": r[4]}
        for r in rows
    ]

@router.post("/", response_model=Tour)
def create_tour(tour: TourCreate):
    conn = get_connection()
    cur = conn.cursor()

    try:
        # 1) Определяем количество мест по layout_variant
        seats_per_layout = {
            1: 46,  # Neoplan
            2: 48   # Travego
        }
        total_seats = seats_per_layout.get(tour.layout_variant)
        if not total_seats:
            raise HTTPException(status_code=400, detail="Неизвестный layout_variant")

        # 2) Создаём запись в таблице tour
        #    Поле seats = total_seats, чтобы в таблице tour хранилось общее число мест
        cur.execute(
            """
            INSERT INTO tour (route_id, pricelist_id, date, seats, layout_variant)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (tour.route_id, tour.pricelist_id, tour.date, total_seats, tour.layout_variant)
        )
        tour_id = cur.fetchone()[0]

        # 3) Получаем остановки для маршрута
        cur.execute("SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY \"order\";", (tour.route_id,))
        stops = [r[0] for r in cur.fetchall()]
        if len(stops) < 2:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Маршрут должен содержать минимум 2 остановки.")

        num_segments = len(stops) - 1
        available_str = "".join(str(i) for i in range(1, num_segments + 1))

        # 4) Генерируем записи в таблице seat
        #    Если место в active_seats, available = "123...n-1", иначе "0"
        for seat_num in range(1, total_seats + 1):
            is_active = (seat_num in tour.active_seats)
            seat_available = available_str if is_active else "0"

            cur.execute(
                """
                INSERT INTO seat (tour_id, seat_num, available)
                VALUES (%s, %s, %s);
                """,
                (tour_id, seat_num, seat_available)
            )

        # 5) Заполняем таблицу available (по сегментам маршрута)
        #    seats = количество активных мест
        active_count = len([s for s in tour.active_seats if s <= total_seats])
        for i in range(num_segments):
            dep_stop = stops[i]
            arr_stop = stops[i+1]
            cur.execute(
                """
                INSERT INTO available (tour_id, departure_stop_id, arrival_stop_id, seats)
                VALUES (%s, %s, %s, %s);
                """,
                (tour_id, dep_stop, arr_stop, active_count)
            )

        conn.commit()

        # 6) Формируем ответ
        return {
            "id": tour_id,
            "route_id": tour.route_id,
            "pricelist_id": tour.pricelist_id,
            "date": tour.date,
            "layout_variant": tour.layout_variant
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.delete("/{tour_id}")
def delete_tour(tour_id: int, force: bool = Query(False)):
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT COUNT(*) FROM ticket WHERE tour_id = %s", (tour_id,))
        if cur.fetchone()[0] > 0 and not force:
            raise HTTPException(status_code=400, detail="Есть проданные билеты. Используйте force=true для удаления.")

        cur.execute("DELETE FROM ticket WHERE tour_id = %s", (tour_id,))
        cur.execute("DELETE FROM seat WHERE tour_id = %s", (tour_id,))
        cur.execute("DELETE FROM available WHERE tour_id = %s", (tour_id,))
        cur.execute("DELETE FROM tour WHERE id = %s RETURNING id", (tour_id,))
        
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Tour not found")
        
        conn.commit()
        return {"detail": "Рейс удалён", "deleted_id": deleted[0]}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.put("/{tour_id}", response_model=Tour)
def update_tour(tour_id: int, tour_data: TourCreate):
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "UPDATE tour SET route_id=%s, pricelist_id=%s, date=%s, layout_variant=%s WHERE id=%s RETURNING id",
            (tour_data.route_id, tour_data.pricelist_id, tour_data.date, tour_data.layout_variant, tour_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Tour not found")

        cur.execute("SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY \"order\"", (tour_data.route_id,))
        stops = [r[0] for r in cur.fetchall()]
        num_segments = len(stops) - 1
        available_str = "".join(str(i) for i in range(1, num_segments + 1))

        seats_per_layout = {1: 46, 2: 48}
        total_seats = seats_per_layout.get(tour_data.layout_variant)

        if not total_seats:
            raise HTTPException(status_code=400, detail="Неизвестный layout_variant")

        for seat_num in range(1, total_seats + 1):
            is_active = seat_num in tour_data.active_seats
            seat_available = available_str if is_active else "0"

            cur.execute("""
                UPDATE seat SET available=%s WHERE tour_id=%s AND seat_num=%s
            """, (seat_available, tour_id, seat_num))

        # Update available table seats counts
        seats_available = len(tour_data.active_seats)
        for i in range(num_segments):
            dep_stop = stops[i]
            arr_stop = stops[i+1]
            cur.execute("""
                UPDATE available SET seats=%s WHERE tour_id=%s AND departure_stop_id=%s AND arrival_stop_id=%s
            """, (seats_available, tour_id, dep_stop, arr_stop))

        conn.commit()

        return {
            "id": tour_id,
            "route_id": tour_data.route_id,
            "pricelist_id": tour_data.pricelist_id,
            "date": tour_data.date,
            "layout_variant": tour_data.layout_variant
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
