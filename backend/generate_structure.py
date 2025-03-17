import os

# Определим корневую директорию для backend
backend_dir = "backend"
routers_dir = os.path.join(backend_dir, "routers")

# Функция для создания директории, если её ещё нет
def create_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Создана директория: {path}")
    else:
        print(f"Директория уже существует: {path}")

# Функция для создания файла с содержимым
def create_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Создан файл: {path}")

# 1. Создаем директории
create_dir(backend_dir)
create_dir(routers_dir)

# 2. Файл backend/main.py
main_py = '''from fastapi import FastAPI
from routers import stops

app = FastAPI()

app.include_router(stops.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
'''
create_file(os.path.join(backend_dir, "main.py"), main_py)

# 3. Файл backend/database.py
database_py = '''import psycopg2

DATABASE_URL = "postgresql://user:password@localhost:5432/bus_tickets"

def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn
'''
create_file(os.path.join(backend_dir, "database.py"), database_py)

# 4. Файл backend/models.py
models_py = '''from pydantic import BaseModel

class StopBase(BaseModel):
    stop_name: str

class StopCreate(StopBase):
    pass

class Stop(StopBase):
    id: int
    class Config:
        orm_mode = True
'''
create_file(os.path.join(backend_dir, "models.py"), models_py)

# 5. Файл backend/routers/__init__.py (пустой)
create_file(os.path.join(routers_dir, "__init__.py"), "# Пустой файл для обозначения пакета routers\n")

# 6. Файл backend/routers/stops.py
stops_py = '''from fastapi import APIRouter
from models import Stop, StopCreate

router = APIRouter(prefix="/stops", tags=["stops"])

# Пример данных - список остановок
stops_data = [
    { "id": 1, "stop_name": "Stop A" },
    { "id": 2, "stop_name": "Stop B" },
]

@router.get("/", response_model=list[Stop])
def get_stops():
    return stops_data

@router.post("/", response_model=Stop)
def create_stop(stop: StopCreate):
    new_stop = { "id": len(stops_data) + 1, **stop.dict() }
    stops_data.append(new_stop)
    return new_stop
'''
create_file(os.path.join(routers_dir, "stops.py"), stops_py)

print("\nСтруктура backend создана успешно.")
