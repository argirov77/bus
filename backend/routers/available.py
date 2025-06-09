from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from ..database import get_connection

router = APIRouter(prefix="/available", tags=["available"])

class AvailableCreate(BaseModel):
    tour_id: int
    departure_stop_id: int
    arrival_stop_id: int
    seats: int

class Available(BaseModel):
    id: int
    tour_id: int
    departure_stop_id: int
    arrival_stop_id: int
    seats: int

    class Config:
        orm_mode = True

@router.get("/", response_model=list[Available])
def get_available(
    tour_id: int = Query(None, description="ID на рейса"),
    departure_stop_id: int = Query(None, description="ID на отправната спирка"),
    arrival_stop_id: int = Query(None, description="ID на крайната спирка")
):
    """
    GET endpoint, който връща записи от таблицата available.
    Филтрира по tour_id, departure_stop_id и arrival_stop_id, ако са зададени.
    """
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT id, tour_id, departure_stop_id, arrival_stop_id, seats FROM available"
    filters = []
    params = []
    if tour_id is not None:
        filters.append("tour_id = %s")
        params.append(tour_id)
    if departure_stop_id is not None:
        filters.append("departure_stop_id = %s")
        params.append(departure_stop_id)
    if arrival_stop_id is not None:
        filters.append("arrival_stop_id = %s")
        params.append(arrival_stop_id)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY id;"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": row[0], "tour_id": row[1], "departure_stop_id": row[2], "arrival_stop_id": row[3], "seats": row[4]}
        for row in rows
    ]

@router.post("/", response_model=Available)
def create_available(item: AvailableCreate):
    """
    POST endpoint, който създава нов запис в таблицата available.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO available (tour_id, departure_stop_id, arrival_stop_id, seats)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (item.tour_id, item.departure_stop_id, item.arrival_stop_id, item.seats)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return {
            "id": new_id,
            "tour_id": item.tour_id,
            "departure_stop_id": item.departure_stop_id,
            "arrival_stop_id": item.arrival_stop_id,
            "seats": item.seats
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.put("/{available_id}", response_model=Available)
def update_available(available_id: int, item: AvailableCreate):
    """
    PUT endpoint, който актуализира запис в таблицата available.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE available
            SET tour_id = %s,
                departure_stop_id = %s,
                arrival_stop_id = %s,
                seats = %s
            WHERE id = %s
            RETURNING id, tour_id, departure_stop_id, arrival_stop_id, seats;
            """,
            (item.tour_id, item.departure_stop_id, item.arrival_stop_id, item.seats, available_id)
        )
        updated_row = cur.fetchone()
        if updated_row is None:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
        return {
            "id": updated_row[0],
            "tour_id": updated_row[1],
            "departure_stop_id": updated_row[2],
            "arrival_stop_id": updated_row[3],
            "seats": updated_row[4]
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.delete("/{available_id}")
def delete_available(available_id: int):
    """
    DELETE endpoint, който изтрива запис от таблицата available.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM available WHERE id = %s RETURNING id;", (available_id,))
        deleted_row = cur.fetchone()
        if deleted_row is None:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
        return {"deleted_id": deleted_row[0], "detail": "Record deleted"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
