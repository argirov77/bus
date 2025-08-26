from datetime import time as dt_time

from fastapi import APIRouter, Depends, HTTPException, Response
from ..auth import require_admin_token
from ..database import get_connection
from ..models import (
    LangRequest,
    RoutesBundleOut,
    PricelistBundleOut,
    AdminSelectedRoutesIn,
    AdminSelectedPricelistIn,
    AdminSelectedRoutesOut,
    AdminSelectedPricelistOut,
    SuccessResponse,
)
from psycopg2.errors import UndefinedColumn

router = APIRouter(tags=["bundle"])


@router.get(
    "/admin/selected_route",
    response_model=AdminSelectedRoutesOut,
    dependencies=[Depends(require_admin_token)],
)
def get_selected_routes():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT route_forward_id, route_backward_id FROM route_pricelist_bundle WHERE id=1"
        )
        row = cur.fetchone()
        if not row:
            return {"routes": []}
        routes = [{"id": r} for r in row if r]
        return {"routes": routes}
    finally:
        cur.close()
        conn.close()


@router.get(
    "/admin/selected_pricelist",
    response_model=AdminSelectedPricelistOut,
    dependencies=[Depends(require_admin_token)],
)
def get_selected_pricelist():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT pricelist_id FROM route_pricelist_bundle WHERE id=1")
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Bundle not found")
        return {"pricelist": {"id": row[0]}}
    finally:
        cur.close()
        conn.close()


@router.post(
    "/admin/selected_route",
    response_model=SuccessResponse,
    dependencies=[Depends(require_admin_token)],
)
def set_selected_routes(data: AdminSelectedRoutesIn):
    if not data.routes or len(data.routes) > 2:
        raise HTTPException(400, "Provide one or two route IDs")
    r1 = data.routes[0]
    r2 = data.routes[1] if len(data.routes) > 1 else data.routes[0]
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM route_pricelist_bundle WHERE id=1")
        if cur.fetchone():
            cur.execute(
                "UPDATE route_pricelist_bundle SET route_forward_id=%s, route_backward_id=%s WHERE id=1",
                (r1, r2),
            )
        else:
            cur.execute(
                "INSERT INTO route_pricelist_bundle (id, route_forward_id, route_backward_id, pricelist_id) VALUES (1,%s,%s,1)",
                (r1, r2),
            )
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@router.post(
    "/admin/selected_pricelist",
    response_model=SuccessResponse,
    dependencies=[Depends(require_admin_token)],
)
def set_selected_pricelist(data: AdminSelectedPricelistIn):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM route_pricelist_bundle WHERE id=1")
        if cur.fetchone():
            cur.execute(
                "UPDATE route_pricelist_bundle SET pricelist_id=%s WHERE id=1",
                (data.pricelist_id,),
            )
        else:
            cur.execute(
                "INSERT INTO route_pricelist_bundle (id, route_forward_id, route_backward_id, pricelist_id) VALUES (1,1,1,%s)",
                (data.pricelist_id,),
            )
        conn.commit()
        return {"success": True}
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
        f'SELECT s.id, COALESCE(s.{col}, s.stop_name), s.description, s.location, '
        f'rs.arrival_time, rs.departure_time '
        f'FROM routestop rs JOIN stop s ON rs.stop_id=s.id '
        f'WHERE rs.route_id=%s ORDER BY rs."order"',
        (route_id,),
    )
    def _fmt(val):
        return val.strftime("%H:%M") if isinstance(val, dt_time) else val

    stops = [
        {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "location": r[3],
            "arrival_time": _fmt(r[4]),
            "departure_time": _fmt(r[5]),
        }
        for r in cur.fetchall()
    ]
    return {"id": route_id, "name": name, "stops": stops}


@router.options("/selected_route")
def selected_route_options() -> Response:
    """Preflight request handler for selected route bundle."""
    return Response(status_code=200)


@router.post("/selected_route", response_model=RoutesBundleOut)
def selected_route(data: LangRequest):
    lang = data.lang.lower()
    col = f"stop_{lang}" if lang in {"en", "bg", "ua"} else "stop_name"
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM route WHERE is_demo ORDER BY id")
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(404, "Demo routes not found")
        forward_id = rows[0][0]
        backward_id = rows[1][0] if len(rows) > 1 else forward_id
        forward = _get_route(cur, forward_id, col)
        backward = _get_route(cur, backward_id, col)
        return {"forward": forward, "backward": backward}
    finally:
        cur.close()
        conn.close()


@router.post("/selected_pricelist", response_model=PricelistBundleOut)
def selected_pricelist(data: LangRequest):
    lang = data.lang.lower()
    # Map supported languages to their corresponding column names.  If an
    # unsupported language is requested we gracefully fall back to the
    # default ``stop_name`` column rather than constructing a non-existent
    # column like ``stop_ru`` which would raise an SQL error and bubble up as
    # a 500 response.
    lang_columns = {"en": "stop_en", "bg": "stop_bg", "ua": "stop_ua"}
    col = lang_columns.get(lang, "stop_name")
    conn = get_connection()
    cur = conn.cursor()
    try:
        # The ``pricelist`` table gained an ``is_demo`` column via a later
        # migration.  When running against an older database that lacks this
        # column the query below would raise ``UndefinedColumn`` and the
        # endpoint would return a 500 error.  To remain backwards compatible we
        # retry the lookup without the ``WHERE`` clause if the column is
        # missing, effectively selecting the first available pricelist instead
        # of failing hard.
        try:
            cur.execute("SELECT id FROM pricelist WHERE is_demo ORDER BY id LIMIT 1")
        except UndefinedColumn:
            cur.execute("SELECT id FROM pricelist ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Demo pricelist not found")
        pricelist_id = row[0]
        # Build the query dynamically with the requested translation column.
        query_tpl = """
            SELECT p.departure_stop_id, COALESCE(s1.{col}, s1.stop_name),
                   p.arrival_stop_id, COALESCE(s2.{col}, s2.stop_name),
                   p.price
              FROM prices p
              JOIN stop s1 ON s1.id=p.departure_stop_id
              JOIN stop s2 ON s2.id=p.arrival_stop_id
             WHERE p.pricelist_id=%s
             ORDER BY p.id
        """
        query = query_tpl.format(col=col)
        try:
            cur.execute(query, (pricelist_id,))
        except UndefinedColumn:
            # If the database does not contain the requested translation
            # column (e.g. ``stop_bg``), retry the query using the default
            # ``stop_name`` column instead of failing with a 500 error.
            fallback_query = query_tpl.format(col="stop_name")
            cur.execute(fallback_query, (pricelist_id,))
        except Exception as e:
            if "column" in str(e).lower() and "does not exist" in str(e).lower():
                fallback_query = query_tpl.format(col="stop_name")
                cur.execute(fallback_query, (pricelist_id,))
            else:
                raise
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
