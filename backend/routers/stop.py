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
    cur.execute(
        "SELECT id, stop_name, stop_en, stop_bg, stop_ua, description, location "
        "FROM stop ORDER BY id ASC;"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    stops_list = [
        {
            "id": row[0],
            "stop_name": row[1],
            "stop_en": row[2],
            "stop_bg": row[3],
            "stop_ua": row[4],
            "description": row[5],
            "location": row[6],
        }
        for row in rows
    ]
    return stops_list

@router.post("/", response_model=Stop)
def create_stop(stop_data: StopCreate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO stop (stop_name, stop_en, stop_bg, stop_ua, description, location)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, stop_name, stop_en, stop_bg, stop_ua, description, location;
        """,
        (
            stop_data.stop_name,
            stop_data.stop_en,
            stop_data.stop_bg,
            stop_data.stop_ua,
            stop_data.description,
            stop_data.location,
        ),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return {
        "id": row[0],
        "stop_name": row[1],
        "stop_en": row[2],
        "stop_bg": row[3],
        "stop_ua": row[4],
        "description": row[5],
        "location": row[6],
    }

@router.get("/{stop_id}", response_model=Stop)
def get_stop(stop_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, stop_name, stop_en, stop_bg, stop_ua, description, location
        FROM stop WHERE id = %s;
        """,
        (stop_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Stop not found")
    return {
        "id": row[0],
        "stop_name": row[1],
        "stop_en": row[2],
        "stop_bg": row[3],
        "stop_ua": row[4],
        "description": row[5],
        "location": row[6],
    }

@router.put("/{stop_id}", response_model=Stop)
def update_stop(stop_id: int, stop_data: StopCreate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE stop
        SET stop_name=%s, stop_en=%s, stop_bg=%s, stop_ua=%s, description=%s, location=%s
        WHERE id=%s
        RETURNING id, stop_name, stop_en, stop_bg, stop_ua, description, location;
        """,
        (
            stop_data.stop_name,
            stop_data.stop_en,
            stop_data.stop_bg,
            stop_data.stop_ua,
            stop_data.description,
            stop_data.location,
            stop_id,
        ),
    )
    updated_row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated_row is None:
        raise HTTPException(status_code=404, detail="Stop not found")
    return {
        "id": updated_row[0],
        "stop_name": updated_row[1],
        "stop_en": updated_row[2],
        "stop_bg": updated_row[3],
        "stop_ua": updated_row[4],
        "description": updated_row[5],
        "location": updated_row[6],
    }

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
