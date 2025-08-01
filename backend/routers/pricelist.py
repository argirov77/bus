# routers/pricelists.py
from fastapi import APIRouter, HTTPException, status, Depends
from ..auth import require_admin_token
from typing import List
from ..database import get_connection
from ..models import Pricelist, PricelistCreate, PricelistDemoUpdate

router = APIRouter(
    prefix="/pricelists",
    tags=["pricelists"],
    dependencies=[Depends(require_admin_token)],
)

@router.get("/", response_model=List[Pricelist])
def get_pricelists():
    """
    Получить все прайс-листы.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, is_demo FROM pricelist ORDER BY id ASC;")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [{"id": r[0], "name": r[1], "is_demo": r[2]} for r in rows]

@router.post("/", response_model=Pricelist, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=Pricelist, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_pricelists(item: PricelistCreate):
    """
    Создать новый прайс-лист.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO pricelist (name) VALUES (%s) RETURNING id, name, is_demo;",
        (item.name,)
    )
    new_id, new_name, is_demo = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return {"id": new_id, "name": new_name, "is_demo": is_demo}

@router.put("/{pricelist_id}", response_model=Pricelist)
def update_pricelist(pricelist_id: int, item: PricelistCreate):
    """
    Обновить название прайс-листа по ID.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE pricelist SET name = %s WHERE id = %s RETURNING id, name, is_demo;",
        (item.name, pricelist_id)
    )
    updated = cur.fetchone()
    if not updated:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Pricelist not found")

    conn.commit()
    cur.close()
    conn.close()
    return {"id": updated[0], "name": updated[1], "is_demo": updated[2]}


@router.put("/{pricelist_id}/demo", response_model=Pricelist)
def update_pricelist_demo(pricelist_id: int, data: PricelistDemoUpdate):
    """Mark or unmark a pricelist as demo. Only one pricelist may be demo."""
    conn = get_connection()
    cur = conn.cursor()
    if data.is_demo:
        cur.execute("SELECT COUNT(*) FROM pricelist WHERE is_demo")
        if cur.fetchone()[0] >= 1:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail="Only one demo pricelist allowed")
    cur.execute(
        "UPDATE pricelist SET is_demo=%s WHERE id=%s RETURNING id, name, is_demo;",
        (data.is_demo, pricelist_id),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Pricelist not found")
    return {"id": row[0], "name": row[1], "is_demo": row[2]}

@router.delete("/{pricelist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pricelist(pricelist_id: int):
    """
    Удалить прайс-лист по ID.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM pricelist WHERE id = %s RETURNING id;", (pricelist_id,))
    deleted = cur.fetchone()
    if not deleted:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Pricelist not found")

    conn.commit()
    cur.close()
    conn.close()
    # 204 No Content — тело ответа не нужно
    return
