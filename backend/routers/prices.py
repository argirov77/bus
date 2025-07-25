from fastapi import APIRouter, HTTPException, Depends
from ..database import get_connection
from ..models import Prices, PricesCreate
from ..auth import get_current_admin

router = APIRouter(
    prefix="/prices",
    tags=["prices"],
    dependencies=[Depends(get_current_admin)],
)

@router.get("/", response_model=None)
def get_prices(pricelist_id: int = None):
    """
    GET-запитване, което връща записите от таблицата prices.
    Ако е зададен pricelist_id, връща само цените за него.
    В резултата се връщат допълнителни полета с имена на спирките.
    """
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
        result.append({
            "id": row[0],
            "pricelist_id": row[1],
            "departure_stop_id": row[2],
            "departure_stop_name": row[3],
            "arrival_stop_id": row[4],
            "arrival_stop_name": row[5],
            "price": row[6]
        })
    return result

@router.post("/", response_model=Prices)
def create_price(price_data: PricesCreate):
    """
    Създава нов запис в таблицата prices и връща данните за създадената цена.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO prices (pricelist_id, departure_stop_id, arrival_stop_id, price)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (
                price_data.pricelist_id,
                price_data.departure_stop_id,
                price_data.arrival_stop_id,
                price_data.price,
            )
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return {"id": new_id, **price_data.dict()}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.put("/{price_id}", response_model=Prices)
def update_price(price_id: int, price_data: PricesCreate):
    """
    Обновява запис в таблицата prices и връща обновената цена.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
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
        if updated_row is None:
            raise HTTPException(status_code=404, detail="Price not found")
        return {
            "id": updated_row[0],
            "pricelist_id": updated_row[1],
            "departure_stop_id": updated_row[2],
            "arrival_stop_id": updated_row[3],
            "price": updated_row[4]
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.delete("/{price_id}")
def delete_price(price_id: int):
    """
    Изтрива запис от таблицата prices и връща информация за изтрития запис.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM prices WHERE id = %s RETURNING id;",
            (price_id,)
        )
        deleted_row = cur.fetchone()
        conn.commit()
        if deleted_row is None:
            raise HTTPException(status_code=404, detail="Price not found")
        return {"deleted_id": deleted_row[0], "detail": "Price deleted"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
