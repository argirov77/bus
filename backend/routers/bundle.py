from fastapi import APIRouter, Depends, HTTPException
from ..auth import require_admin_token
from ..database import get_connection
from ..models import (
    RoutePricelistBundleCreate,
    RoutePricelistBundle,
    LangRequest,
    RoutesBundleOut,
    PricelistBundleOut,
)

router = APIRouter(tags=["bundle"])


@router.api_route(
    "/admin/route_pricelist_bundle/",
    methods=["POST", "PUT"],
    response_model=RoutePricelistBundle,
    dependencies=[Depends(require_admin_token)],
)
def set_bundle(data: RoutePricelistBundleCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM route_pricelist_bundle WHERE id=1")
        if cur.fetchone():
            cur.execute(
                """
                UPDATE route_pricelist_bundle
                   SET route_forward_id=%s,
                       route_backward_id=%s,
                       pricelist_id=%s
                 WHERE id=1
                 RETURNING id, route_forward_id, route_backward_id, pricelist_id
                """,
                (data.route_forward_id, data.route_backward_id, data.pricelist_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO route_pricelist_bundle
                        (id, route_forward_id, route_backward_id, pricelist_id)
                VALUES (1,%s,%s,%s)
                RETURNING id, route_forward_id, route_backward_id, pricelist_id
                """,
                (data.route_forward_id, data.route_backward_id, data.pricelist_id),
            )
        row = cur.fetchone()
        conn.commit()
        return {
            "id": row[0],
            "route_forward_id": row[1],
            "route_backward_id": row[2],
            "pricelist_id": row[3],
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


def _get_route(cur, route_id: int, col: str):
    cur.execute("SELECT name FROM route WHERE id=%s", (route_id,))
    row = cur.fetchone()
    name = row[0] if row else ""
    cur.execute(
        f'SELECT s.id, COALESCE(s.{col}, s.stop_name) '
        f'FROM routestop rs JOIN stop s ON rs.stop_id=s.id '
        f'WHERE rs.route_id=%s ORDER BY rs."order"',
        (route_id,),
    )
    stops = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    return {"id": route_id, "name": name, "stops": stops}


@router.post("/public/routes_bundle", response_model=RoutesBundleOut)
def public_routes_bundle(data: LangRequest):
    lang = data.lang.lower()
    col = f"stop_{lang}" if lang in {"en", "bg", "ua"} else "stop_name"
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT route_forward_id, route_backward_id FROM route_pricelist_bundle WHERE id=1"
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Bundle not found")
        forward_id, backward_id = row
        forward = _get_route(cur, forward_id, col)
        backward = _get_route(cur, backward_id, col)
        return {"forward": forward, "backward": backward}
    finally:
        cur.close()
        conn.close()


@router.post("/public/pricelist_bundle", response_model=PricelistBundleOut)
def public_pricelist_bundle(data: LangRequest):
    lang = data.lang.lower()
    col = f"stop_{lang}" if lang in {"en", "bg", "ua"} else "stop_name"
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT pricelist_id FROM route_pricelist_bundle WHERE id=1"
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Bundle not found")
        pricelist_id = row[0]
        cur.execute(
            f"""
            SELECT p.departure_stop_id, COALESCE(s1.{col}, s1.stop_name),
                   p.arrival_stop_id, COALESCE(s2.{col}, s2.stop_name),
                   p.price
              FROM prices p
              JOIN stop s1 ON s1.id=p.departure_stop_id
              JOIN stop s2 ON s2.id=p.arrival_stop_id
             WHERE p.pricelist_id=%s
             ORDER BY p.id
            """,
            (pricelist_id,),
        )
        prices = [
            {
                "departure_stop_id": r[0],
                "departure_name": r[1],
                "arrival_stop_id": r[2],
                "arrival_name": r[3],
                "price": r[4],
            }
            for r in cur.fetchall()
        ]
        return {"pricelist_id": pricelist_id, "prices": prices}
    finally:
        cur.close()
        conn.close()
