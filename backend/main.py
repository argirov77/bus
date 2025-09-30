import os
import re
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

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
from .services.public_session import ensure_purchase_session


app = FastAPI()

# Healthcheck endpoint
@app.get("/health")
def health() -> dict[str, str]:
    """Simple health check returning API status."""
    return {"status": "ok"}
# Configure CORS to allow requests from the mini-cabinet front-end.
origins = [
    "http://localhost:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           # or allow_origin_regex=r"http://localhost:\d+$"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["Content-Disposition"],
    max_age=86400,
)


_purchase_pdf_pattern = re.compile(r"^/purchase/(?P<purchase_id>\d+)/pdf/?$")
_ticket_pdf_pattern = re.compile(r"^/tickets/(?P<ticket_id>\d+)/pdf/?$")


def _extract_path_requirements(path: str) -> tuple[bool, int | None, int | None]:
    """Determine whether a request path requires purchase session validation."""

    purchase_id: int | None = None
    ticket_id: int | None = None

    stripped = path.split("?")[0]
    match_purchase = _purchase_pdf_pattern.match(stripped)
    if match_purchase:
        purchase_id = int(match_purchase.group("purchase_id"))
    match_ticket = _ticket_pdf_pattern.match(stripped)
    if match_ticket:
        ticket_id = int(match_ticket.group("ticket_id"))

    segments = [segment for segment in stripped.strip("/").split("/") if segment]
    if segments and segments[0] == "public":
        if len(segments) >= 3 and segments[1] == "purchase" and segments[2].isdigit():
            purchase_id = int(segments[2])
        if len(segments) >= 3 and segments[1] == "tickets" and segments[2].isdigit():
            ticket_id = int(segments[2])
        return True, purchase_id, ticket_id

    if match_purchase or match_ticket:
        return True, purchase_id, ticket_id

    return False, None, None


class PurchaseSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        should_guard, purchase_id, ticket_id = _extract_path_requirements(request.url.path)
        if not should_guard:
            return await call_next(request)

        try:
            context = await run_in_threadpool(
                ensure_purchase_session,
                request,
                required_purchase_id=purchase_id,
                required_ticket_id=ticket_id,
            )
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        request.state.purchase_session = context
        return await call_next(request)


app.add_middleware(PurchaseSessionMiddleware)

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
