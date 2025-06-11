# Запуск проекта в Docker

Этот репозиторий содержит бэкенд на **FastAPI** и фронтенд на **React**.
Приложение собирается в один Docker-контейнер, который обслуживает API и статику React.
Python-зависимости устанавливаются во внутреннее виртуальное окружение, поэтому конфликты с системными пакетами исключены.

## Требования
- [Docker](https://www.docker.com/) и [docker-compose](https://docs.docker.com/compose/)

## Сборка контейнеров
```bash
docker compose build
```

## Запуск
```bash
docker compose up
```
После запуска приложение будет доступно на `http://localhost:8000`.
При необходимости порт можно изменить в файле `.env` (переменная `BACKEND_PORT`).

Для остановки выполнения используйте:
```bash
docker compose down
```

## Подключение к базе данных
В контейнере запускается PostgreSQL с настройками по умолчанию. Порт
`5432` проброшен на хост, поэтому к базе можно подключиться по
`localhost:5432`:
- **host:** `localhost`
- **port:** `5432`
- **database:** `test`
- **user:** `postgres`
- **password:** `postgres`

URL подключения доступен в переменной окружения `DATABASE_URL`. Например,
можно подключиться через `psql`:
```bash
psql postgresql://postgres:postgres@localhost:5432/test
```

## Локальный запуск без Docker
Для разработки можно запустить сервер напрямую. Используйте Python 3.12 и установите зависимости:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
Запустите приложение из корня репозитория командой:
```bash
python -m uvicorn backend.main:app --reload
```
Важно запускать команду именно из корня проекта, чтобы работали относительные импорты из `backend`.

## Настройка адреса API
Фронтенд использует переменную окружения `REACT_APP_API_URL` для обращения к бэкенду.
Создайте файл `.env` в каталоге `frontend` и укажите там URL сервера, например:
```bash
REACT_APP_API_URL=http://localhost:8000
```
Если файл уже существует, можно изменить значение переменной на свой.
