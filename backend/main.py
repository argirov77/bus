from fastapi import FastAPI
import threading
import time
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

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
)
from .routers.ticket_admin import router as admin_tickets_router


app = FastAPI()

# Healthcheck endpoint
@app.get("/health")
def health() -> dict[str, str]:
    """Simple health check returning API status."""
    return {"status": "ok"}

# Настраиваем CORS с помощью переменной окружения
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(report.router)
app.include_router(available.router)
app.include_router(seat.router)
app.include_router(search.router)
app.include_router(admin_tickets_router)
app.include_router(auth.router)


def _cancel_expired_loop():
    while True:
        time.sleep(60)
        from .database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE purchase
                   SET status='cancelled', updated_at=NOW()
                 WHERE status='reserved'
                   AND created_at < NOW() - INTERVAL '1 hour'
                 RETURNING id
                """
            )
            for row in cur.fetchall():
                cur.execute(
                    "INSERT INTO sales (purchase_id, status) VALUES (%s, 'cancelled')",
                    (row[0],),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cur.close()
            conn.close()


threading.Thread(target=_cancel_expired_loop, daemon=True).start()

# Serve React static files
# app.mount("/", StaticFiles(directory="frontend/build", html=True), name="static")

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("BACKEND_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
