from fastapi import FastAPI
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
app.include_router(report.router)
app.include_router(available.router)
app.include_router(seat.router)
app.include_router(search.router)
app.include_router(admin_tickets_router)
app.include_router(auth.router)

# Serve React static files
# app.mount("/", StaticFiles(directory="frontend/build", html=True), name="static")

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("BACKEND_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
