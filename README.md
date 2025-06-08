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
