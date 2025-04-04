from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List
from datetime import date
from database import get_connection

router = APIRouter(prefix="/tours", tags=["tours"])

class TourCreate(BaseModel):
    route_id: int
    pricelist_id: int
    date: date
    layout_variant: int
    active_seats: List[int]

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
        seats_layout = {1: 46, 2: 48}
        total_seats = seats_layout.get(tour.layout_variant)
        if not total_seats:
            raise HTTPException(status_code=400, detail="Invalid layout_variant")

        cur.execute("""
            INSERT INTO tour (route_id, pricelist_id, date, seats, layout_variant)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """, (tour.route_id, tour.pricelist_id, tour.date, total_seats, tour.layout_variant))
        tour_id = cur.fetchone()[0]

        cur.execute("SELECT stop_id FROM routestop WHERE route_id=%s ORDER BY \"order\";", (tour.route_id,))
        stops = [row[0] for row in cur.fetchall()]
        if len(stops) < 2:
            raise HTTPException(status_code=400, detail="Route must have at least 2 stops.")

        segments = [(stops[i], stops[j]) for i in range(len(stops)-1) for j in range(i+1, len(stops))]
        cur.execute("SELECT departure_stop_id, arrival_stop_id FROM prices WHERE pricelist_id=%s;", (tour.pricelist_id,))
        valid_segments = set(cur.fetchall())

        active_count = len(tour.active_seats)

        for dep_stop, arr_stop in segments:
            if (dep_stop, arr_stop) in valid_segments:
                cur.execute("""
                    INSERT INTO available (tour_id, departure_stop_id, arrival_stop_id, seats)
                    VALUES (%s, %s, %s, %s);
                """, (tour_id, dep_stop, arr_stop, active_count))

        segment_str = "".join(str(i+1) for i in range(len(stops)-1))
        for seat_num in range(1, total_seats+1):
            available = segment_str if seat_num in tour.active_seats else "0"
            cur.execute("""
                INSERT INTO seat (tour_id, seat_num, available) VALUES (%s, %s, %s);
            """, (tour_id, seat_num, available))

        conn.commit()
        return {"id": tour_id, **tour.dict(exclude={"active_seats"})}

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

@router.get("/search")
def search_tours(
    departure_stop_id: int, 
    arrival_stop_id: int, 
    date: date
):
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Находим туры на указанную дату с доступными местами между остановками
        cur.execute("""
            SELECT t.id, t.date, a.seats, t.layout_variant
            FROM tour t
            JOIN available a ON t.id = a.tour_id
            WHERE a.departure_stop_id = %s
              AND a.arrival_stop_id = %s
              AND t.date = %s
              AND a.seats > 0;
        """, (departure_stop_id, arrival_stop_id, date))

        rows = cur.fetchall()
        tours = [
            {"id": row[0], "date": row[1], "seats": row[2], "layout_variant": row[3]}
            for row in rows
        ]

        return tours

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cur.close()
        conn.close()
