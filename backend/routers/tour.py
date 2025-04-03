from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List
from datetime import date, datetime
from database import get_connection

router = APIRouter(prefix="/tours", tags=["tours"])

class TourCreate(BaseModel):
    route_id: int
    pricelist_id: int
    date: date
    layout_variant: int  # избран layout (напр. 1 - Neoplan, 2 - Travego)
    active_seats: List[int]  # номера на активните места за продажба

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
        # 1) Определяме общия брой места според layout_variant
        seats_per_layout = {
            1: 46,  # Neoplan
            2: 48   # Travego
        }
        total_seats = seats_per_layout.get(tour.layout_variant)
        if not total_seats:
            raise HTTPException(status_code=400, detail="Неизвестен layout_variant")

        # 2) Създаваме запис в таблицата tour, като полето seats се задава автоматично
        cur.execute(
            """
            INSERT INTO tour (route_id, pricelist_id, date, seats, layout_variant)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (tour.route_id, tour.pricelist_id, tour.date, total_seats, tour.layout_variant)
        )
        tour_id = cur.fetchone()[0]

        # 3) Получаваме спирките за маршрута (от таблицата routestop) – подредени по "order"
        cur.execute(
            "SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY \"order\";",
            (tour.route_id,)
        )
        stops = [r[0] for r in cur.fetchall()]
        if len(stops) < 2:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Маршрутът трябва да съдържа минимум 2 спирки.")

        # Броят на сегментите е равен на (броя спирки - 1)
        num_segments = len(stops) - 1
        # Строка с номера на сегментите, напр. "1234" при 4 сегмента
        available_str = "".join(str(i) for i in range(1, num_segments + 1))

        # 4) Генерираме записи в таблицата seat
        # За всяко място от 1 до total_seats: ако мястото е активирано (в active_seats) – available = available_str, иначе "0"
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

        # 5) Запълваме таблицата available – за всеки валиден сегмент между две последователни спирки
        # Записваме броя свободни места равен на броя активирани места (active_count)
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
        # Проверяваме дали има продадени билети
        cur.execute("SELECT COUNT(*) FROM ticket WHERE tour_id = %s", (tour_id,))
        if cur.fetchone()[0] > 0 and not force:
            raise HTTPException(status_code=400, detail="Има продадени билети. Използвайте force=true за каскадно изтриване.")

        # Изтриваме свързаните записи
        cur.execute("DELETE FROM ticket WHERE tour_id = %s", (tour_id,))
        cur.execute("DELETE FROM seat WHERE tour_id = %s", (tour_id,))
        cur.execute("DELETE FROM available WHERE tour_id = %s", (tour_id,))
        cur.execute("DELETE FROM tour WHERE id = %s RETURNING id", (tour_id,))
        
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Tour not found")
        
        conn.commit()
        return {"detail": "Рейс изтрит", "deleted_id": deleted[0]}
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
        # Актуализираме основната информация за тура (без поле seats, което се пресмята автоматично)
        cur.execute(
            """
            UPDATE tour
            SET route_id = %s, pricelist_id = %s, date = %s, layout_variant = %s
            WHERE id = %s
            RETURNING id;
            """,
            (tour_data.route_id, tour_data.pricelist_id, tour_data.date, tour_data.layout_variant, tour_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Tour not found")

        # Обновяваме списъка със спирки за маршрута
        cur.execute("SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY \"order\"", (tour_data.route_id,))
        stops = [r[0] for r in cur.fetchall()]
        num_segments = len(stops) - 1
        available_str = "".join(str(i) for i in range(1, num_segments + 1))

        seats_per_layout = {1: 46, 2: 48}
        total_seats = seats_per_layout.get(tour_data.layout_variant)
        if not total_seats:
            raise HTTPException(status_code=400, detail="Неизвестен layout_variant")

        # Обновяваме записите в таблицата seat
        for seat_num in range(1, total_seats + 1):
            is_active = seat_num in tour_data.active_seats
            seat_available = available_str if is_active else "0"
            cur.execute(
                """
                UPDATE seat SET available = %s
                WHERE tour_id = %s AND seat_num = %s;
                """,
                (seat_available, tour_id, seat_num)
            )

        # Обновяваме таблицата available – задаваме броя свободни места за всеки сегмент
        active_count = len(tour_data.active_seats)
        for i in range(num_segments):
            dep_stop = stops[i]
            arr_stop = stops[i+1]
            cur.execute(
                """
                UPDATE available
                SET seats = %s
                WHERE tour_id = %s AND departure_stop_id = %s AND arrival_stop_id = %s;
                """,
                (active_count, tour_id, dep_stop, arr_stop)
            )

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
