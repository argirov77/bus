from fastapi import APIRouter, Depends, HTTPException, Query
from ..database import get_connection
from ..models import RoutePricelistBundleCreate, RoutePricelistBundle
from ..auth import require_admin_token

router = APIRouter()

admin_router = APIRouter(
    prefix="/admin/route_pricelist_bundle",
    tags=["route_pricelist_bundle"],
    dependencies=[Depends(require_admin_token)],
)

@admin_router.post("/", status_code=204)
def set_bundle(data: RoutePricelistBundleCreate):
    """Save or replace the current route/pricelist bundle."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM route_pricelist_bundle")
        cur.execute(
            """INSERT INTO route_pricelist_bundle (route_forward_id, route_backward_id, pricelist_id)
               VALUES (%s, %s, %s)""",
            (data.route_forward_id, data.route_backward_id, data.pricelist_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

@admin_router.get("/", response_model=RoutePricelistBundle | None)
def get_bundle_admin():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, route_forward_id, route_backward_id, pricelist_id FROM route_pricelist_bundle LIMIT 1"
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "route_forward_id": row[1],
        "route_backward_id": row[2],
        "pricelist_id": row[3],
    }


public_router = APIRouter(prefix="/public", tags=["public_bundle"])


def _get_stop_name(row, lang: str) -> str:
    mapping = {
        "en": row[1],
        "bg": row[2],
        "ua": row[3],
    }
    return mapping.get(lang) or row[0]


@public_router.get("/routes_bundle")
def routes_bundle(lang: str = Query("ru")):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT route_forward_id, route_backward_id FROM route_pricelist_bundle LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(404, "Bundle not configured")
    forward_id, backward_id = row

    def load_route(rid: int):
        cur.execute("SELECT id, name FROM route WHERE id=%s", (rid,))
        route_row = cur.fetchone()
        if not route_row:
            return None
        cur.execute(
            'SELECT stop_id FROM routestop WHERE route_id=%s ORDER BY "order"',
            (rid,),
        )
        stop_ids = [r[0] for r in cur.fetchall()]
        stops = []
        if stop_ids:
            cur.execute(
                "SELECT stop_name, stop_en, stop_bg, stop_ua, id FROM stop WHERE id = ANY(%s)",
                (stop_ids,),
            )
            stop_map = {r[4]: r[:4] for r in cur.fetchall()}
            for sid in stop_ids:
                srow = stop_map.get(sid)
                if srow:
                    stops.append({"id": sid, "name": _get_stop_name(srow, lang)})
        return {"id": route_row[0], "name": route_row[1], "stops": stops}

    forward = load_route(forward_id)
    backward = load_route(backward_id)

    cur.close()
    conn.close()
    return {"forward": forward, "backward": backward}


@public_router.get("/pricelist_bundle")
def pricelist_bundle(lang: str = Query("ru")):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT pricelist_id FROM route_pricelist_bundle LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(404, "Bundle not configured")
    pricelist_id = row[0]

    cur.execute("SELECT id, name FROM pricelist WHERE id=%s", (pricelist_id,))
    pl = cur.fetchone()
    if not pl:
        cur.close()
        conn.close()
        raise HTTPException(404, "Pricelist not found")

    cur.execute(
        """SELECT p.departure_stop_id, s1.stop_name, s1.stop_en, s1.stop_bg, s1.stop_ua,
                   p.arrival_stop_id, s2.stop_name, s2.stop_en, s2.stop_bg, s2.stop_ua,
                   p.price
            FROM prices p
            JOIN stop s1 ON p.departure_stop_id = s1.id
            JOIN stop s2 ON p.arrival_stop_id = s2.id
            WHERE p.pricelist_id = %s
            ORDER BY p.id""",
        (pricelist_id,),
    )
    prices = []
    for r in cur.fetchall():
        dep_id, d_ru, d_en, d_bg, d_ua, arr_id, a_ru, a_en, a_bg, a_ua, price = r
        dep_name = _get_stop_name((d_ru, d_en, d_bg, d_ua), lang)
        arr_name = _get_stop_name((a_ru, a_en, a_bg, a_ua), lang)
        prices.append(
            {
                "departure_stop_id": dep_id,
                "departure_stop_name": dep_name,
                "arrival_stop_id": arr_id,
                "arrival_stop_name": arr_name,
                "price": price,
            }
        )

    cur.close()
    conn.close()

    return {"pricelist": {"id": pl[0], "name": pl[1]}, "prices": prices}


router.include_router(admin_router)
router.include_router(public_router)
