from fastapi import FastAPI, Request, Response
import threading
import time
from fastapi.staticfiles import StaticFiles
import os
import re

# Ensure application runs in Bulgarian time (UTC+3) so all logs and time-based
# functions reflect the expected timezone.
os.environ.setdefault("TZ", "Europe/Sofia")
time.tzset()

# Импортируем все роутеры
from .routers import (
    stop,
    route,
    pricelist,
    prices,
    tour,
    passenger,
    report,
    available,
    seat,
    search,
    ticket,
    purchase,
    auth,
    bundle,
    public,
)
from .routers.ticket_admin import router as admin_tickets_router
from .routers.purchase_admin import router as admin_purchases_router


app = FastAPI()

# Healthcheck endpoint
@app.get("/health")
def health() -> dict[str, str]:
    """Simple health check returning API status."""
    return {"status": "ok"}
def _split_origins(value: str | None) -> list[str]:
    if not value:
        return []
    return [origin.strip() for origin in value.split(",") if origin.strip()]


cors_origins = [
    "https://client-mt.netlify.app",
    "http://localhost:4000",
    "http://127.0.0.1:4000",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://38.79.154.248:3000",
    "http://172.18.0.4:3000",
]
cors_origins.extend(_split_origins(os.getenv("CORS_ORIGINS")))
cors_origins.extend(_split_origins(os.getenv("INTERNAL_ADMIN_ORIGINS")))

internal_admin_origin_regex = os.getenv(
    "INTERNAL_ADMIN_ORIGIN_REGEX",
    r"^http://(localhost|127\.0\.0\.1"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})"
    r"(:\d{2,5})?$",
)

allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
default_allowed_headers = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
    "User-Agent",
    "DNT",
    "Cache-Control",
    "X-Requested-With",
    "If-Modified-Since",
    "Keep-Alive",
    "X-Access-Token",
    "X-Access-Refresh-Token",
]


def _is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    if origin in cors_origins:
        return True
    return bool(re.match(internal_admin_origin_regex, origin))


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    is_allowed = _is_origin_allowed(origin)

    if request.method == "OPTIONS" and "access-control-request-method" in request.headers:
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    if is_allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
        response.headers["Vary"] = "Origin"

        request_headers = request.headers.get("access-control-request-headers")
        allow_headers = request_headers or ", ".join(default_allowed_headers)
        response.headers["Access-Control-Allow-Headers"] = allow_headers
        response.headers["Access-Control-Allow-Methods"] = ", ".join(allowed_methods)
        response.headers["Access-Control-Max-Age"] = "86400"

    return response

# Подключаем роутеры
app.include_router(stop.router)
app.include_router(route.router)
app.include_router(pricelist.router)
app.include_router(prices.router)
app.include_router(tour.router)
app.include_router(passenger.router)
app.include_router(ticket.router)
app.include_router(purchase.router)
app.include_router(purchase.actions_router)
app.include_router(report.router)
app.include_router(available.router)
app.include_router(seat.router)
app.include_router(search.router)
app.include_router(bundle.router)
app.include_router(public.session_router)
app.include_router(public.router)
app.include_router(admin_tickets_router)
app.include_router(admin_purchases_router)
app.include_router(auth.router)


def _cancel_expired_loop():
    while True:
        time.sleep(60)
        from .database import get_connection
        from .ticket_utils import free_ticket

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id FROM purchase WHERE status='reserved' AND deadline < NOW()",
            )
            purchase_ids = [row[0] for row in cur.fetchall()]

            for pid in purchase_ids:
                cur.execute(
                    "SELECT id FROM ticket WHERE purchase_id=%s",
                    (pid,),
                )
                for t_row in cur.fetchall():
                    free_ticket(cur, t_row[0])

                cur.execute(
                    "UPDATE purchase SET status='cancelled', update_at=NOW() WHERE id=%s",
                    (pid,),
                )
                cur.execute(
                    "INSERT INTO sales (purchase_id, category, amount, actor, method) VALUES (%s, 'cancelled', 0, 'system', NULL)",
                    (pid,),
                )

            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cur.close()
            conn.close()


def _finish_departed_tours_loop():
    while True:
        time.sleep(60)
        from .database import get_connection

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT t.id
                  FROM tour t
                  JOIN routestop rs ON rs.route_id = t.route_id AND rs."order" = 1
                 WHERE (t.date + rs.departure_time) <= NOW()
                """
            )
            tour_ids = [r[0] for r in cur.fetchall()]
            if tour_ids:
                cur.execute(
                    "UPDATE available SET seats = 0 WHERE tour_id = ANY(%s)",
                    (tour_ids,),
                )
                cur.execute(
                    "UPDATE seat SET available = '0' WHERE tour_id = ANY(%s)",
                    (tour_ids,),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cur.close()
            conn.close()


threading.Thread(target=_cancel_expired_loop, daemon=True).start()
threading.Thread(target=_finish_departed_tours_loop, daemon=True).start()

# Serve React static files
# app.mount("/", StaticFiles(directory="frontend/build", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("BACKEND_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
