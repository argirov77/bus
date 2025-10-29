from fastapi import FastAPI
import json
import threading
import time
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from typing import Final

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


def _parse_cors_origins() -> list[str]:
    """Return the configured CORS origins.

    The project historically allowed several localhost origins.  To keep
    backwards compatibility and support production deployments (including the
    HTTPS reverse proxy on the VPS), the list is now controlled via the
    ``CORS_ORIGINS`` environment variable.  When the variable is empty we fall
    back to the original defaults.
    """

    default_origins: Final[list[str]] = [
        "http://localhost:4000",
        "http://127.0.0.1:4000",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://client-mt.netlify.app",
        "http://38.79.154.248:3000",
        "http://172.18.0.4:3000",
    ]

    def _load_from_env(var_name: str) -> list[str]:
        raw = os.getenv(var_name, "").strip()
        if not raw:
            return []

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            return [item.strip() for item in parsed if item.strip()]

        origins = [origin.strip().strip("'\"") for origin in raw.split(",") if origin.strip()]
        return origins

    for env_var in ("BACKEND_CORS_ORIGINS", "ALLOWED_ORIGINS", "CORS_ORIGINS"):
        origins = _load_from_env(env_var)
        if origins:
            return origins

    return default_origins


# Healthcheck endpoint
@app.get("/health")
def health() -> dict[str, str]:
    """Simple health check returning API status."""
    return {"status": "ok"}


# Configure CORS to allow requests from development front-end origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["Content-Disposition"],
    max_age=86400,
)

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
