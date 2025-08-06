# backend/app/routers/tour.py

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
from ..database import get_connection
from ..auth import require_admin_token
from ..models import BookingTermsEnum

router = APIRouter(
    prefix="/tours",
    tags=["tours"],
    dependencies=[Depends(require_admin_token)],
)


class TourCreate(BaseModel):
    route_id: int
    pricelist_id: int
    date: date
    layout_variant: int
    active_seats: List[int]
    booking_terms: BookingTermsEnum = BookingTermsEnum.EXPIRE_AFTER_48H


class TourOut(BaseModel):
    id: int
    route_id: int
    pricelist_id: int
    date: date
    layout_variant: int
    booking_terms: BookingTermsEnum

    class Config:
        from_attributes = True


class TourListOut(BaseModel):
    items: List[TourOut]
    total: int


@router.get("/", response_model=List[TourOut])
def get_tours():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, route_id, pricelist_id, date, layout_variant, booking_terms FROM tour ORDER BY date;"
        )
        return [
            {
                "id": r[0],
                "route_id": r[1],
                "pricelist_id": r[2],
                "date": r[3],
                "layout_variant": r[4],
                "booking_terms": r[5],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


@router.get("/list", response_model=TourListOut)
def list_tours(
    show_past: bool = Query(False, description="Show past tours instead of upcoming"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1),
    date: Optional[date] = None,
    route_id: Optional[int] = None,
    booking_terms: Optional[BookingTermsEnum] = None,
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        conditions = []
        params: List = []

        if show_past:
            conditions.append("date < CURRENT_DATE")
        else:
            conditions.append("date >= CURRENT_DATE")

        if date:
            conditions.append("date = %s")
            params.append(date)
        if route_id is not None:
            conditions.append("route_id = %s")
            params.append(route_id)
        if booking_terms is not None:
            conditions.append("booking_terms = %s")
            params.append(booking_terms)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        cur.execute(f"SELECT COUNT(*) FROM tour{where_clause}", tuple(params))
        total = cur.fetchone()[0]

        query = (
            "SELECT id, route_id, pricelist_id, date, layout_variant, booking_terms FROM tour"
            f"{where_clause} ORDER BY date"
        )
        query_params = list(params)
        query += " LIMIT %s OFFSET %s"
        query_params.extend([page_size, (page - 1) * page_size])

        cur.execute(query, tuple(query_params))
        items = [
            {
                "id": r[0],
                "route_id": r[1],
                "pricelist_id": r[2],
                "date": r[3],
                "layout_variant": r[4],
                "booking_terms": r[5],
            }
            for r in cur.fetchall()
        ]

        return {"items": items, "total": total}
    finally:
        cur.close()
        conn.close()


@router.post("/", response_model=TourOut)
def create_tour(tour: TourCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        seats_layout = {1: 46, 2: 48}
        total_seats = seats_layout.get(tour.layout_variant)
        if total_seats is None:
            raise HTTPException(400, "Invalid layout_variant")

        # Вставляем запись рейса
        cur.execute(
            """
            INSERT INTO tour (route_id, pricelist_id, date, seats, layout_variant, booking_terms)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                tour.route_id,
                tour.pricelist_id,
                tour.date,
                total_seats,
                tour.layout_variant,
                tour.booking_terms,
            ),
        )
        tour_id = cur.fetchone()[0]

        # Собираем все остановки и все возможные сегменты (i<j)
        cur.execute(
            "SELECT stop_id FROM routestop WHERE route_id=%s ORDER BY \"order\"",
            (tour.route_id,),
        )
        stops = [r[0] for r in cur.fetchall()]
        if len(stops) < 2:
            raise HTTPException(400, "Route must have at least 2 stops")

        # Формируем все возможные сегменты маршрута (i < j)
        all_segments = [
            (stops[i], stops[j])
            for i in range(len(stops) - 1)
            for j in range(i + 1, len(stops))
        ]

        # Выбираем только те сегменты, что есть в данном прайслисте
        cur.execute(
            "SELECT departure_stop_id, arrival_stop_id FROM prices WHERE pricelist_id=%s",
            (tour.pricelist_id,),
        )
        valid_segments = set(cur.fetchall())

        active_count = len(tour.active_seats)

        # Заполняем таблицу available
        for dep, arr in all_segments:
            if (dep, arr) in valid_segments:
                cur.execute(
                    """
                    INSERT INTO available (tour_id, departure_stop_id, arrival_stop_id, seats)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (tour_id, dep, arr, active_count),
                )

        # Создаём записи мест
        seg_str = "".join(str(i + 1) for i in range(len(stops) - 1))
        for num in range(1, total_seats + 1):
            avail = seg_str if num in tour.active_seats else "0"
            cur.execute(
                "INSERT INTO seat (tour_id, seat_num, available) VALUES (%s, %s, %s)",
                (tour_id, num, avail),
            )

        conn.commit()
        return {"id": tour_id, **tour.dict(exclude={"active_seats"})}

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/{tour_id}")
def delete_tour(tour_id: int, force: bool = Query(False)):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Проверка проданных билетов
        cur.execute("SELECT COUNT(*) FROM ticket WHERE tour_id=%s", (tour_id,))
        if cur.fetchone()[0] > 0 and not force:
            raise HTTPException(
                400, "Есть проданные билеты. Используйте force=true для каскадного удаления"
            )

        # Каскадное удаление
        cur.execute("DELETE FROM ticket WHERE tour_id=%s", (tour_id,))
        cur.execute("DELETE FROM seat WHERE tour_id=%s", (tour_id,))
        cur.execute("DELETE FROM available WHERE tour_id=%s", (tour_id,))
        cur.execute("DELETE FROM tour WHERE id=%s RETURNING id", (tour_id,))
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(404, "Tour not found")

        conn.commit()
        return {"deleted_id": deleted[0], "detail": "Рейс удалён"}

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@router.put("/{tour_id}", response_model=TourOut)
def update_tour(tour_id: int, tour_data: TourCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) Обновляем основные поля рейса
        cur.execute(
            """
            UPDATE tour
               SET route_id=%s, pricelist_id=%s, date=%s, layout_variant=%s, booking_terms=%s
             WHERE id=%s
             RETURNING id
            """,
            (
                tour_data.route_id,
                tour_data.pricelist_id,
                tour_data.date,
                tour_data.layout_variant,
                tour_data.booking_terms,
                tour_id,
            ),
        )
        if not cur.fetchone():
            raise HTTPException(404, "Tour not found")

        # 2) Снова собираем список остановок
        cur.execute(
            "SELECT stop_id FROM routestop WHERE route_id=%s ORDER BY \"order\"",
            (tour_data.route_id,),
        )
        stops = [r[0] for r in cur.fetchall()]
        if len(stops) < 2:
            raise HTTPException(400, "Route must have at least 2 stops")
        # список сегментов больше не используется

        # 3) Проверяем, что занятые места остаются активными
        cur.execute(
            """
            SELECT DISTINCT s.seat_num
              FROM ticket t JOIN seat s ON s.id=t.seat_id
             WHERE t.tour_id=%s
            """,
            (tour_id,),
        )
        taken_seats = {r[0] for r in cur.fetchall()}
        inactive_with_tickets = taken_seats - set(tour_data.active_seats)
        if inactive_with_tickets:
            raise HTTPException(400, "Cannot deactivate seats with sold tickets")

        # 4) Формируем базовые строки доступности
        seg_str = "".join(str(i + 1) for i in range(len(stops) - 1))
        total_seats = {1: 46, 2: 48}[tour_data.layout_variant]
        seat_avail = {
            num: (seg_str if num in tour_data.active_seats else "0")
            for num in range(1, total_seats + 1)
        }

        # 5) Учитываем уже проданные билеты, убирая их сегменты
        cur.execute(
            """
            SELECT s.seat_num, t.departure_stop_id, t.arrival_stop_id
              FROM ticket t JOIN seat s ON s.id=t.seat_id
             WHERE t.tour_id=%s
            """,
            (tour_id,),
        )
        for seat_num, dep, arr in cur.fetchall():
            idx_from = stops.index(dep)
            idx_to = stops.index(arr)
            segs = [str(i + 1) for i in range(idx_from, idx_to)]
            avail = seat_avail.get(seat_num, "")
            seat_avail[seat_num] = "".join(ch for ch in avail if ch not in segs) or "0"

        for num, avail in seat_avail.items():
            cur.execute(
                "UPDATE seat SET available=%s WHERE tour_id=%s AND seat_num=%s",
                (avail, tour_id, num),
            )

        # 6) Пересчитываем таблицу available заново
        recalc_available(cur, tour_id)

        conn.commit()
        return {
            "id": tour_id,
            "route_id": tour_data.route_id,
            "pricelist_id": tour_data.pricelist_id,
            "date": tour_data.date,
            "layout_variant": tour_data.layout_variant,
            "booking_terms": tour_data.booking_terms,
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/search")
def search_tours(
    departure_stop_id: int,
    arrival_stop_id: int,
    date: date,
    seats: int = 1,
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT t.id, t.date, a.seats, t.layout_variant
              FROM tour t
              JOIN available a ON a.tour_id = t.id
             WHERE a.departure_stop_id=%s
               AND a.arrival_stop_id=%s
               AND t.date=%s
               AND a.seats>=%s
            """,
            (departure_stop_id, arrival_stop_id, date, seats),
        )
        return [
            {"id": r[0], "date": r[1], "seats": r[2], "layout_variant": r[3]}
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()
