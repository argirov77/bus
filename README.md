# Запуск проекта в Docker

Этот репозиторий содержит бэкенд на **FastAPI** и фронтенд на **React**.
Docker Compose поднимает отдельные контейнеры: `db`, `backend` и `frontend`.
Python-зависимости устанавливаются во внутренние окружения контейнеров, поэтому конфликты с системными пакетами исключены.

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
После запуска бекенд будет доступен на `http://localhost:8000`, а фронтенд 
на `http://localhost:3000`.
Если нужно использовать другие порты, измените значения `BACKEND_PORT` и,
при желании, `FRONTEND_PORT` в файле `.env`.
Docker Compose применит эти переменные и к контейнерам, и к приложениям,
поэтому менять их достаточно в одном месте.

Для остановки выполнения используйте:
```bash
docker compose down
```

## Подключение к базе данных
В контейнере запускается PostgreSQL с настройками по умолчанию. Контейнерный
порт `5432` проброшен на хост. По умолчанию он маппится на `localhost:5433`,
но при необходимости это значение можно изменить переменной окружения
`POSTGRES_HOST_PORT`:
- **host:** `localhost`
- **port:** `5433` (или выбранный вами `POSTGRES_HOST_PORT`)
- **database:** `test1`
- **user:** `postgres`
- **password:** `postgres`

URL подключения доступен в переменной окружения `DATABASE_URL`. Например,
можно подключиться через `psql`:
```bash
psql postgresql://postgres:postgres@localhost:${POSTGRES_HOST_PORT:-5433}/test1
```

## Локальный запуск без Docker
Для разработки можно запустить сервер напрямую. Используйте Python 3.12 и установите зависимости:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
Перед запуском необходимо указать переменную окружения `DATABASE_URL`, чтобы
приложение подключилось к локальной базе данных:
```bash
export DATABASE_URL=postgresql://postgres:postgres@localhost:${POSTGRES_HOST_PORT:-5433}/test1
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
Если вы меняете `BACKEND_PORT`, не забудьте обновить и эту переменную,
чтобы фронтенд обращался к правильному порту.
