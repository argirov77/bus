from fastapi import APIRouter, HTTPException, Depends
from ..database import get_connection
from ..models import Stop, StopCreate
from ..auth import require_admin_token

router = APIRouter(
    prefix="/stops",
    tags=["stops"],
    dependencies=[Depends(require_admin_token)],
)

@router.get("/", response_model=list[Stop])
def get_stops():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, stop_name FROM stop ORDER BY id ASC;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    stops_list = [{"id": row[0], "stop_name": row[1]} for row in rows]
    return stops_list

@router.post("/", response_model=Stop)
def create_stop(stop_data: StopCreate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO stop (stop_name) VALUES (%s) RETURNING id;", (stop_data.stop_name,))
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": new_id, "stop_name": stop_data.stop_name}

@router.get("/{stop_id}", response_model=Stop)
def get_stop(stop_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, stop_name FROM stop WHERE id = %s;", (stop_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Stop not found")
    return {"id": row[0], "stop_name": row[1]}

@router.put("/{stop_id}", response_model=Stop)
def update_stop(stop_id: int, stop_data: StopCreate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE stop SET stop_name = %s WHERE id = %s RETURNING id, stop_name;",
        (stop_data.stop_name, stop_id)
    )
    updated_row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated_row is None:
        raise HTTPException(status_code=404, detail="Stop not found")
    return {"id": updated_row[0], "stop_name": updated_row[1]}

@router.delete("/{stop_id}")
def delete_stop(stop_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM stop WHERE id = %s RETURNING id;", (stop_id,))
    deleted_row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted_row is None:
        raise HTTPException(status_code=404, detail="Stop not found")
    return {"deleted_id": deleted_row[0], "detail": "Stop deleted"}
