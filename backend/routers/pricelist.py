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
@router.get("", response_model=List[Pricelist], include_in_schema=False)
def get_pricelists():
    """
    Получить все прайс-листы.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, currency FROM pricelist ORDER BY id ASC;")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {"id": r[0], "name": r[1], "currency": r[2], "is_demo": False}
        for r in rows
    ]

@router.post("/", response_model=Pricelist, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=Pricelist, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_pricelists(item: PricelistCreate):
    """
    Создать новый прайс-лист.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO pricelist (name, currency) VALUES (%s, %s) RETURNING id, name, currency;",
        (item.name, item.currency)
    )
    new_id, new_name, new_currency = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return {"id": new_id, "name": new_name, "currency": new_currency, "is_demo": False}

@router.put("/{pricelist_id}", response_model=Pricelist)
def update_pricelist(pricelist_id: int, item: PricelistCreate):
    """
    Обновить название прайс-листа по ID.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE pricelist SET name = %s, currency = %s WHERE id = %s RETURNING id, name, currency;",
        (item.name, item.currency, pricelist_id)
    )
    updated = cur.fetchone()
    if not updated:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Pricelist not found")

    conn.commit()
    cur.close()
    conn.close()
    return {"id": updated[0], "name": updated[1], "currency": updated[2], "is_demo": False}


@router.put("/{pricelist_id}/demo", response_model=Pricelist)
def update_pricelist_demo(pricelist_id: int, data: PricelistDemoUpdate):
    """Mark or unmark a pricelist as demo. Only one pricelist may be demo."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, currency FROM pricelist WHERE id=%s", (pricelist_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Pricelist not found")
    return {"id": row[0], "name": row[1], "currency": row[2], "is_demo": False}

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
