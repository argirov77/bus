from fastapi import APIRouter, HTTPException
from database import get_connection
from models import Prices, PricesCreate

router = APIRouter(prefix="/prices", tags=["prices"])

@router.get("/", response_model=None)  # пока уберём response_model, чтобы вернуть любые поля
def get_prices(pricelist_id: int = None):
    conn = get_connection()
    cur = conn.cursor()
    if pricelist_id is not None:
        cur.execute(
            """
            SELECT p.id,
                   p.pricelist_id,
                   p.departure_stop_id,
                   s1.stop_name AS departure_name,
                   p.arrival_stop_id,
                   s2.stop_name AS arrival_name,
                   p.price
            FROM prices p
            JOIN stop s1 ON p.departure_stop_id = s1.id
            JOIN stop s2 ON p.arrival_stop_id = s2.id
            WHERE p.pricelist_id = %s
            ORDER BY p.id ASC;
            """,
            (pricelist_id,)
        )
    else:
        cur.execute(
            """
            SELECT p.id,
                   p.pricelist_id,
                   p.departure_stop_id,
                   s1.stop_name AS departure_name,
                   p.arrival_stop_id,
                   s2.stop_name AS arrival_name,
                   p.price
            FROM prices p
            JOIN stop s1 ON p.departure_stop_id = s1.id
            JOIN stop s2 ON p.arrival_stop_id = s2.id
            ORDER BY p.id ASC;
            """
        )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for row in rows:
        # row = [id, pricelist_id, departure_stop_id, departure_name, arrival_stop_id, arrival_name, price]
        result.append({
            "id": row[0],
            "pricelist_id": row[1],
            "departure_stop_id": row[2],
            "departure_stop_name": row[3],   # <-- ключи с названиями
            "arrival_stop_id": row[4],
            "arrival_stop_name": row[5],
            "price": row[6]
        })

    return result



@router.post("/", response_model=Prices)
def create_price(price_data: PricesCreate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO prices (pricelist_id, departure_stop_id, arrival_stop_id, price) VALUES (%s, %s, %s, %s) RETURNING id;",
        (
            price_data.pricelist_id,
            price_data.departure_stop_id,
            price_data.arrival_stop_id,
            price_data.price,
        )
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": new_id, **price_data.dict()}

@router.put("/{price_id}", response_model=Prices)
def update_price(price_id: int, price_data: PricesCreate):
    conn = get_connection()
    cur = conn.cursor()
    # Обновляем запись в таблице prices
    cur.execute(
        """
        UPDATE prices
        SET pricelist_id = %s,
            departure_stop_id = %s,
            arrival_stop_id = %s,
            price = %s
        WHERE id = %s
        RETURNING id, pricelist_id, departure_stop_id, arrival_stop_id, price;
        """,
        (
            price_data.pricelist_id,
            price_data.departure_stop_id,
            price_data.arrival_stop_id,
            price_data.price,
            price_id
        )
    )
    updated_row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated_row is None:
        raise HTTPException(status_code=404, detail="Price not found")
    return {
        "id": updated_row[0],
        "pricelist_id": updated_row[1],
        "departure_stop_id": updated_row[2],
        "arrival_stop_id": updated_row[3],
        "price": updated_row[4]
    }

@router.delete("/{price_id}")
def delete_price(price_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM prices WHERE id = %s RETURNING id;",
        (price_id,)
    )
    deleted_row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted_row is None:
        raise HTTPException(status_code=404, detail="Price not found")
    return {"deleted_id": deleted_row[0], "detail": "Price deleted"}
