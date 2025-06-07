# Запуск проекта в Docker

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
После запуска приложение будет доступно на `http://localhost:8000`. API и
фронтенд работают на одном порту.

Для остановки выполнения используйте:
```bash
docker compose down
```
