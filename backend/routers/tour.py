from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import date
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
    Создает новый рейс с указанными параметрами.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tour (route_id, pricelist_id, date, seats) VALUES (%s, %s, %s, %s) RETURNING id;",
        (tour.route_id, tour.pricelist_id, tour.date, tour.seats)
    )
    tour_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {
        "id": tour_id,
        "route_id": tour.route_id,
        "pricelist_id": tour.pricelist_id,
        "date": tour.date,
        "seats": tour.seats
    }

@router.delete("/{tour_id}")
def delete_tour(tour_id: int):
    """
    Удаляет рейс по его ID.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM tour WHERE id=%s RETURNING id;", (tour_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Tour not found")
    return {"deleted_id": deleted[0], "detail": "Tour deleted"}

@router.put("/{tour_id}", response_model=Tour)
def update_tour(tour_id: int, tour_data: TourCreate):
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
        raise HTTPException(status_code=404, detail="Tour not found")
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
