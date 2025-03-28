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
    seats: int

class Tour(BaseModel):
    id: int
    route_id: int
    pricelist_id: int
    date: date
    seats: int
    class Config:
        orm_mode = True

@router.get("/", response_model=List[Tour])
def get_tours():
    """
    Возвращает список рейсов, отсортированных по дате.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, route_id, pricelist_id, date, seats FROM tour ORDER BY date;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "route_id": r[1], "pricelist_id": r[2], "date": r[3], "seats": r[4]}
        for r in rows
    ]

@router.post("/", response_model=Tour)
def create_tour(tour: TourCreate):
    """
    Создает новый рейс (tour) и автоматически генерирует записи в таблицах:
    - seat: для каждого места (1..seats) строка available = "1234..." (по числу сегментов)
    - available: для каждого сегмента (из routeStop) создается запись с seats = tour.seats
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Создаем запись в таблице tour
        cur.execute(
            "INSERT INTO tour (route_id, pricelist_id, date, seats) VALUES (%s, %s, %s, %s) RETURNING id;",
            (tour.route_id, tour.pricelist_id, tour.date, tour.seats)
        )
        tour_id = cur.fetchone()[0]

        # 2. Определяем список остановок из routeStop для данного route_id
        cur.execute("""
            SELECT stop_id 
            FROM routestop
            WHERE route_id = %s
            ORDER BY "order"
        """, (tour.route_id,))
        stops = [row[0] for row in cur.fetchall()]
        if len(stops) < 2:
            conn.rollback()
            raise HTTPException(status_code=400, detail="Маршрут должен содержать как минимум 2 остановки.")

        # Количество сегментов
        num_segments = len(stops) - 1
        # Строка вида "1234" (если 4 сегмента)
        available_str = "".join(str(i) for i in range(1, num_segments+1))

        # 3. Заполняем таблицу seat
        # Для каждого места от 1 до tour.seats -> INSERT
        for seat_num in range(1, tour.seats + 1):
            cur.execute("""
                INSERT INTO seat (tour_id, seat_num, available)
                VALUES (%s, %s, %s);
            """, (tour_id, seat_num, available_str))

        # 4. Заполняем таблицу available
        # Для каждого сегмента (пара соседних остановок) создаем запись:
        # departure_stop_id = stops[i], arrival_stop_id = stops[i+1], seats = tour.seats
        for i in range(num_segments):
            dep_stop = stops[i]
            arr_stop = stops[i+1]
            cur.execute("""
                INSERT INTO available (tour_id, departure_stop_id, arrival_stop_id, seats)
                VALUES (%s, %s, %s, %s);
            """, (tour_id, dep_stop, arr_stop, tour.seats))

        conn.commit()

        return {
            "id": tour_id,
            "route_id": tour.route_id,
            "pricelist_id": tour.pricelist_id,
            "date": tour.date,
            "seats": tour.seats
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.delete("/{tour_id}")
def delete_tour(tour_id: int, force: bool = Query(False, description="Подтверждение каскадного удаления, если есть проданные билеты")):
    conn = get_connection()
    cur = conn.cursor()
    
    # Проверяем наличие проданных билетов
    cur.execute("SELECT COUNT(*) FROM ticket WHERE tour_id = %s", (tour_id,))
    ticket_count = cur.fetchone()[0]
    if ticket_count > 0 and not force:
        cur.close()
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="На этом туре есть проданные билеты. Удаление приведет к удалению связанных билетов. "
                   "Если вы уверены, добавьте параметр force=true в запрос."
        )
    
    try:
        # Получаем все билеты для этого тура
        cur.execute("SELECT departure_stop_id, arrival_stop_id FROM ticket WHERE tour_id = %s", (tour_id,))
        tickets = cur.fetchall()
        
        # Обновляем таблицу available: для каждого билета увеличиваем количество мест (если логика такая нужна)
        for dep_stop, arr_stop in tickets:
            cur.execute("""
                UPDATE available
                SET seats = seats + 1
                WHERE tour_id = %s 
                  AND departure_stop_id = %s 
                  AND arrival_stop_id = %s
            """, (tour_id, dep_stop, arr_stop))
        
        # Удаляем билеты, связанные с туром
        cur.execute("DELETE FROM ticket WHERE tour_id = %s", (tour_id,))
        
        # Удаляем записи из таблицы seat, связанные с туром
        cur.execute("DELETE FROM seat WHERE tour_id = %s", (tour_id,))
        
        # Удаляем записи из таблицы available для данного тура
        cur.execute("DELETE FROM available WHERE tour_id = %s", (tour_id,))
        
        # Наконец, удаляем сам тур
        cur.execute("DELETE FROM tour WHERE id = %s RETURNING id;", (tour_id,))
        deleted = cur.fetchone()
        if not deleted:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Tour not found")
        
        conn.commit()
        return {"deleted_id": deleted[0], "detail": "Tour and all related records deleted successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.put("/{tour_id}", response_model=Tour)
def update_tour(tour_id: int, tour_data: TourCreate):
    """
    Обновляет данные тура (route_id, pricelist_id, date, seats).
    Здесь можно тоже пересоздать/обновить seat и available, 
    но нужно осторожно, если уже есть билеты.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tour
        SET route_id = %s, pricelist_id = %s, date = %s, seats = %s
        WHERE id = %s
        RETURNING id, route_id, pricelist_id, date, seats;
        """,
        (tour_data.route_id, tour_data.pricelist_id, tour_data.date, tour_data.seats, tour_id)
    )
    row = cur.fetchone()
    if not row:
        conn.rollback()
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Tour not found")

    # При желании здесь можно добавить логику пересоздания seat/available, 
    # но если уже проданы билеты — это будет конфликт.
    # Для простоты оставим без изменения seat/available.

    conn.commit()
    cur.close()
    conn.close()
    return {
        "id": row[0],
        "route_id": row[1],
        "pricelist_id": row[2],
        "date": row[3],
        "seats": row[4]
    }

@router.get("/search")
def search_tours(
    departure_stop_id: int = Query(..., description="ID остановки отправления"),
    arrival_stop_id: int = Query(..., description="ID остановки прибытия"),
    date: str = Query(..., description="Дата в формате YYYY-MM-DD")
):
    """
    Ищет туры по заданным параметрам:
      - Отправная остановка (departure_stop_id)
      - Конечная остановка (arrival_stop_id)
      - Дата (date)
      
    Возвращает список туров, для которых для выбранного сегмента маршрута (в таблице available) есть свободные места.
    """
    try:
        search_date = datetime.strptime(date, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="Неверный формат даты. Ожидается YYYY-MM-DD.")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT t.id, t.route_id, t.pricelist_id, t.date, t.seats
            FROM tour t
            JOIN available a ON a.tour_id = t.id
            WHERE t.date = %s 
              AND a.departure_stop_id = %s 
              AND a.arrival_stop_id = %s 
              AND a.seats > 0
            ORDER BY t.id;
        """, (search_date, departure_stop_id, arrival_stop_id))
        rows = cur.fetchall()
        tours = [{
            "id": row[0],
            "route_id": row[1],
            "pricelist_id": row[2],
            "date": row[3].isoformat() if hasattr(row[3], "isoformat") else row[3],
            "seats": row[4]
        } for row in rows]
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
    
    return tours
