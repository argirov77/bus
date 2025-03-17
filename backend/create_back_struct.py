# create_back_struct.py
import os

BACKEND_DIR = "backend"
ROUTERS_DIR = os.path.join(BACKEND_DIR, "routers")

def create_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Создана директория: {path}")
    else:
        print(f"Директория уже существует: {path}")

def create_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Создан файл: {path}")

def main():
    # 1. Создаём папку backend и подпапку routers
    create_dir(BACKEND_DIR)
    create_dir(ROUTERS_DIR)

    # 2. Создаём файл main.py
    main_py = '''from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Импортируем все роутеры
from routers import stop, route, routestop, pricelist, prices, tour, passenger, ticket, available, seat

app = FastAPI()

# Настраиваем CORS (если нужно)
origins = ["http://localhost:3000"]
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
app.include_router(routestop.router)
app.include_router(pricelist.router)
app.include_router(prices.router)
app.include_router(tour.router)
app.include_router(passenger.router)
app.include_router(ticket.router)
app.include_router(available.router)
app.include_router(seat.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
'''
    create_file(os.path.join(BACKEND_DIR, "main.py"), main_py)

    # 3. Создаём файл database.py
    database_py = '''import psycopg2

# Укажите правильные параметры подключения
DATABASE_URL = "postgresql://postgres@localhost:5432/test"

def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn
'''
    create_file(os.path.join(BACKEND_DIR, "database.py"), database_py)

    # 4. Создаём файл models.py (Pydantic-модели)
    models_py = '''from pydantic import BaseModel

# Пример базовой модели
class StopBase(BaseModel):
    stop_name: str

class StopCreate(StopBase):
    pass

class Stop(StopBase):
    id: int
    class Config:
        from_attributes = True  # или orm_mode = True (Pydantic < v2)

# Аналогично можно создать модели для других сущностей
# Route, RouteStop, Pricelist, Prices, Tour, Passenger, Ticket, Available, Seat...
'''
    create_file(os.path.join(BACKEND_DIR, "models.py"), models_py)

    # 5. Пустой __init__.py для routers
    create_file(os.path.join(ROUTERS_DIR, "__init__.py"), "# Пакет роутеров")

    # 6. Генерация роутеров для каждой сущности
    # Шаблон для простых роутеров
    router_template = '''from fastapi import APIRouter
from database import get_connection
from models import {model_name}, {model_name}Create

router = APIRouter(prefix="/{prefix}", tags=["{prefix}"])

@router.get("/")
def get_{prefix}():
    """
    Пример GET-запроса, который возвращает статический список или
    делает SELECT в таблице {prefix}.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример запроса:
    # cur.execute("SELECT id, stop_name FROM stop ORDER BY id ASC;")
    # rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{{"id": 1, "{field_name}": "Test {model_name}"}}]

@router.post("/")
def create_{prefix}(item: {model_name}Create):
    """
    Пример POST-запроса, который вставляет запись в таблицу {prefix}.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Пример INSERT:
    # cur.execute("INSERT INTO stop (stop_name) VALUES (%s) RETURNING id;", (item.stop_name,))
    # new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {{"id": 999, "{field_name}": f"Created {model_name}"}}
'''

    # Список сущностей: (имя файла, префикс, имя модели, поле)
    entities = [
        ("stop", "stops", "Stop", "stop_name"),
        ("route", "routes", "Route", "name"),
        ("routestop", "routestops", "RouteStop", "placeholder_field"),
        ("pricelist", "pricelists", "Pricelist", "name"),
        ("prices", "prices", "Prices", "placeholder_field"),
        ("tour", "tours", "Tour", "placeholder_field"),
        ("passenger", "passengers", "Passenger", "name"),
        ("ticket", "tickets", "Ticket", "placeholder_field"),
        ("available", "available", "Available", "placeholder_field"),
        ("seat", "seats", "Seat", "placeholder_field"),
    ]

    for fname, prefix, model_name, field_name in entities:
        content = router_template.format(
            prefix=prefix,
            model_name=model_name,
            field_name=field_name
        )
        create_file(os.path.join(ROUTERS_DIR, f"{fname}.py"), content)

    print("\nБэкенд-структура успешно создана!")

if __name__ == "__main__":
    main()
