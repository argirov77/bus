from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from ..auth import require_admin_token
from ..database import get_connection
from ..models import RoutePricelistBundle, RoutePricelistBundleCreate


admin_router = APIRouter(
    prefix="/admin/route_pricelist_bundle",
    tags=["route_pricelist_bundle"],
    dependencies=[Depends(require_admin_token)],
)

public_router = APIRouter(prefix="/public", tags=["public"])


@admin_router.get("/", response_model=Optional[RoutePricelistBundle])
def get_bundle():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, route_forward_id, route_backward_id, pricelist_id "
        "FROM route_pricelist_bundle ORDER BY id DESC LIMIT 1"
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


@admin_router.post("/", response_model=RoutePricelistBundle)
def set_bundle(data: RoutePricelistBundleCreate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM route_pricelist_bundle LIMIT 1")
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE route_pricelist_bundle SET route_forward_id=%s, "
            "route_backward_id=%s, pricelist_id=%s WHERE id=%s RETURNING id",
            (
                data.route_forward_id,
                data.route_backward_id,
                data.pricelist_id,
                row[0],
            ),
        )
        bundle_id = cur.fetchone()[0]
    else:
        cur.execute(
            "INSERT INTO route_pricelist_bundle "
            "(route_forward_id, route_backward_id, pricelist_id) "
            "VALUES (%s, %s, %s) RETURNING id",
            (data.route_forward_id, data.route_backward_id, data.pricelist_id),
        )
        bundle_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": bundle_id, **data.dict()}


class LangRequest(BaseModel):
    lang: str = "bg"


_def_lang_map = {
    "en": "stop_en",
    "bg": "stop_bg",
    "ua": "stop_ua",
}


def _get_bundle_ids(cur):
    cur.execute(
        "SELECT route_forward_id, route_backward_id, pricelist_id "
        "FROM route_pricelist_bundle ORDER BY id DESC LIMIT 1"
    )
    return cur.fetchone()


@public_router.post("/routes_bundle")
def public_routes_bundle(data: LangRequest):
    conn = get_connection()
    cur = conn.cursor()
    bundle = _get_bundle_ids(cur)
    if not bundle:
        cur.close()
        conn.close()
        raise HTTPException(404, "Bundle not set")
    route_ids = [bundle[0], bundle[1]]
    routes_info: List[dict] = []
    for rid in route_ids:
        cur.execute("SELECT id, name FROM route WHERE id=%s", (rid,))
        row = cur.fetchone()
        if not row:
            continue
        route_dict = {"id": row[0], "name": row[1], "stops": []}
        cur.execute(
            """
            SELECT s.id, s.stop_name, s.stop_en, s.stop_bg, s.stop_ua,
                   s.description, s.location,
                   rs.arrival_time, rs.departure_time
              FROM routestop rs
              JOIN stop s ON s.id = rs.stop_id
             WHERE rs.route_id = %s
             ORDER BY rs."order"
            """,
            (rid,),
        )
        col = _def_lang_map.get(data.lang, "stop_name")
        idx = {
            "stop_name": 1,
            "stop_en": 2,
            "stop_bg": 3,
            "stop_ua": 4,
        }[col]
        for r in cur.fetchall():
            route_dict["stops"].append(
                {
                    "id": r[0],
                    "name": r[idx],
                    "description": r[5],
                    "location": r[6],
                    "arrival_time": r[7],
                    "departure_time": r[8],
                }
            )
        routes_info.append(route_dict)
    cur.close()
    conn.close()
    return routes_info


@public_router.post("/pricelist_bundle")
def public_pricelist_bundle(data: LangRequest):
    conn = get_connection()
    cur = conn.cursor()
    bundle = _get_bundle_ids(cur)
    if not bundle:
        cur.close()
        conn.close()
        raise HTTPException(404, "Bundle not set")
    pricelist_id = bundle[2]
    cur.execute("SELECT id, name FROM pricelist WHERE id=%s", (pricelist_id,))
    pl_row = cur.fetchone()
    if not pl_row:
        cur.close()
        conn.close()
        raise HTTPException(404, "Pricelist not found")
    pricelist = {"id": pl_row[0], "name": pl_row[1], "prices": []}
    cur.execute(
        """
        SELECT p.id, p.departure_stop_id, p.arrival_stop_id, p.price,
               s1.stop_name, s1.stop_en, s1.stop_bg, s1.stop_ua,
               s2.stop_name, s2.stop_en, s2.stop_bg, s2.stop_ua
          FROM prices p
          JOIN stop s1 ON p.departure_stop_id = s1.id
          JOIN stop s2 ON p.arrival_stop_id = s2.id
         WHERE p.pricelist_id = %s
         ORDER BY p.id
        """,
        (pricelist_id,),
    )
    col = _def_lang_map.get(data.lang, "stop_name")
    idx_map = {
        "stop_name": (4, 8),
        "stop_en": (5, 9),
        "stop_bg": (6, 10),
        "stop_ua": (7, 11),
    }
    idx_dep, idx_arr = idx_map[col]
    for r in cur.fetchall():
        pricelist["prices"].append(
            {
                "id": r[0],
                "departure_stop_id": r[1],
                "arrival_stop_id": r[2],
                "price": r[3],
                "departure_name": r[idx_dep],
                "arrival_name": r[idx_arr],
            }
        )
    cur.close()
    conn.close()
    return pricelist
