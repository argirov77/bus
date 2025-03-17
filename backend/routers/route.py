# file: route.py
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from datetime import time
from pydantic import BaseModel
from database import get_connection  # Предполагается, что у вас есть database.py

router = APIRouter(prefix="/routes", tags=["routes"])

#
# --- Pydantic модели ---
#

class RouteCreate(BaseModel):
    name: str

class Route(BaseModel):
    id: int
    name: str
    class Config:
        from_attributes = True  # или orm_mode = True

class RouteStopCreate(BaseModel):
    stop_id: int
    order: int
    arrival_time: Optional[time] = None
    departure_time: Optional[time] = None

class RouteStop(BaseModel):
    id: int
    route_id: int
    stop_id: int
    order: int
    arrival_time: Optional[time] = None
    departure_time: Optional[time] = None
    class Config:
        from_attributes = True

#
# --- Часть 1: CRUD для маршрутов (Route) ---
#

@router.get("/", response_model=List[Route])
def get_routes():
    """
    Получить список всех маршрутов
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM route ORDER BY id ASC;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]

@router.post("/", response_model=Route)
def create_route(route_data: RouteCreate):
    """
    Создать новый маршрут
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO route (name) VALUES (%s) RETURNING id;", (route_data.name,))
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": new_id, "name": route_data.name}

@router.delete("/{route_id}")
def delete_route(route_id: int):
    """
    Удалить маршрут по ID (и при необходимости его остановки)
    """
    conn = get_connection()
    cur = conn.cursor()
    # Если у вас нет CASCADE, можно удалить остановки вручную:
    # cur.execute("DELETE FROM routestop WHERE route_id = %s;", (route_id,))
    cur.execute("DELETE FROM route WHERE id=%s RETURNING id;", (route_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"deleted_id": deleted[0], "detail": "Route deleted"}

#
# --- Часть 2: CRUD для остановок маршрута (RouteStop) ---
# URL: /routes/{route_id}/stops
#

@router.get("/{route_id}/stops", response_model=List[RouteStop])
def get_route_stops(route_id: int):
    """
    Получить список остановок (RouteStop) для данного маршрута
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'SELECT id, route_id, stop_id, "order", arrival_time, departure_time '
        'FROM routestop WHERE route_id=%s ORDER BY "order" ASC;',
        (route_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "route_id": r[1],
            "stop_id": r[2],
            "order": r[3],
            "arrival_time": r[4],     # это уже Python time
            "departure_time": r[5]    # тоже time
        })
    return result

@router.post("/{route_id}/stops", response_model=RouteStop)
def create_route_stop(route_id: int, data: RouteStopCreate):
    """
    Добавить новую остановку (RouteStop) в маршрут {route_id}.
    arrival_time, departure_time - тип time, приходят в формате "HH:MM" или "HH:MM:SS".
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO routestop (route_id, stop_id, "order", arrival_time, departure_time) '
        'VALUES (%s, %s, %s, %s, %s) RETURNING id;',
        (route_id, data.stop_id, data.order, data.arrival_time, data.departure_time)
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {
        "id": new_id,
        "route_id": route_id,
        "stop_id": data.stop_id,
        "order": data.order,
        "arrival_time": data.arrival_time,
        "departure_time": data.departure_time
    }

@router.put("/{route_id}/stops/{stop_id}", response_model=RouteStop)
def update_route_stop(route_id: int, stop_id: int, data: RouteStopCreate):
    """
    Обновить остановку (arrival_time, departure_time, order, stop_id)
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'UPDATE routestop SET stop_id=%s, "order"=%s, arrival_time=%s, departure_time=%s '
        'WHERE id=%s AND route_id=%s '
        'RETURNING id, route_id, stop_id, "order", arrival_time, departure_time;',
        (data.stop_id, data.order, data.arrival_time, data.departure_time, stop_id, route_id)
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="RouteStop not found or route mismatch")
    return {
        "id": row[0],
        "route_id": row[1],
        "stop_id": row[2],
        "order": row[3],
        "arrival_time": row[4],
        "departure_time": row[5]
    }

@router.delete("/{route_id}/stops/{stop_id}")
def delete_route_stop(route_id: int, stop_id: int):
    """
    Удалить остановку (RouteStop) из маршрута
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM routestop WHERE id=%s AND route_id=%s RETURNING id;", (stop_id, route_id))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="RouteStop not found or mismatch route")
    return {"deleted_id": deleted[0], "detail": "RouteStop deleted"}
