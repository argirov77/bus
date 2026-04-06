# Отчёт об инциденте безопасности — VPS vm2380 (maximovtours.com)
## Дата инцидента: ~15 февраля 2025 — 6 апреля 2026

---

## 1. АРХИТЕКТУРА ПРОЕКТА

### Публичная часть (клиентский фронтенд)
- **Сайт:** maximovtours.com
- **Хостинг:** Netlify
- **Репо:** публичный GitHub
- **API-вызовы:** клиент обращается не напрямую к бэкенду, а через Netlify proxy `maximovtours.com/api/...` → VPS backend

### Серверная часть (VPS)
- **VPS:** vm2380, Ubuntu, 4 ядра, 4 ГБ RAM
- **Docker Compose проект `bus`:**
  - `backend` — FastAPI (Python), порт 8000
  - `frontend` — React admin-панель, порт 3000
  - `db` — PostgreSQL 14, порт 5432/5433
- **Docker Compose проект `spy_bot`** (телеграм-игра "Шпион"):
  - `spy_api`, `spy_bot`, `spy_db` — PostgreSQL 15
- **Nginx** — reverse proxy на порту 80
- **Caddy** — был в конфигурации bus, но не использовался

---

## 2. ЧТО ПРОИЗОШЛО

### Вектор атаки
Это **НЕ таргетированная атака** на maximovtours.com. Это массовое автоматическое сканирование интернета ботнетами-майнерами.

Боты сканируют все IP-адреса подряд, находят открытые порты PostgreSQL, пробуют дефолтные пароли (postgres:postgres — первое, что пробуют), и при успехе устанавливают криптомайнер.

### Хронология
1. **~15 февраля 2025** — первое проникновение. В контейнере db обнаружен файл `/tmp/init` (2.7 МБ) с датой 15 февраля. Криптомайнер запущен на хосте (PID работал 166 дней = с момента запуска VPS).
2. **Февраль-Апрель 2026** — майнер работал непрерывно, потребляя 100% CPU (все 4 ядра) и 2.3 ГБ RAM. За это время прошло ~7 ГБ трафика.
3. **6 апреля 2026** — обнаружение при анализе логов. Повторяющиеся атаки каждые ~40-80 минут от автоматизированных сканеров.

### Как проникли
1. **Порт PostgreSQL 5432 был открыт на весь интернет** (в `docker-compose.yml` опубликован через `ports: "5433:5432"`)
2. **Пароль — `postgres:postgres`** — дефолтный, первое что пробуют боты
3. Атакующие подключились к PostgreSQL, использовали `COPY TO PROGRAM` для выполнения shell-команд
4. Скачали и запустили криптомайнер внутри контейнера
5. Майнер выбрался на хост через Docker (процессы `lxd`)

### Оба проекта (bus и spy_bot) были скомпрометированы одинаково — оба имели PostgreSQL с дефолтными паролями и открытыми портами.

---

## 3. ЧТО ОБНАРУЖИЛИ

### На хосте (VPS)
- **Криптомайнер** — PID 1451784, пользователь `lxd`, 381% CPU, 2.3 ГБ RAM, работал 166 дней
- **Перезапуск майнера** — после kill он перезапускался через bash-скрипты и `init`-процессы
- Вредоносные процессы: `/tmp/mysql`, `/tmp/init`, множество `bash`-процессов от пользователя `lxd`

### В контейнере PostgreSQL (bus)
- **Вредоносная роль `priv_esc`** с правами суперпользователя — создана атакующими
- **Вредоносные файлы:** `/tmp/init` (2.7 МБ, от 15.02), `/tmp/mysql` (2 МБ, от 06.04)
- Многочисленные попытки эскалации привилегий (event triggers, C-функции, materialized view exploits)

### В контейнере PostgreSQL (spy_bot)
- Аналогичное заражение через тот же вектор

### В логах бэкенда
- Множественные сканирования на уязвимости: `.env`, `.git/config`, `docker-compose.yml`, `phpunit`, `actuator/env`, `wp-config.php` и десятки других
- Запросы с закодированными URL (`/%c0`) — попытки обхода путей
- POST-запросы к Next.js эндпоинтам — слепое сканирование
- Все вернули 404

### SSH
- Постоянный brute-force паролей (root, admin, test, user и др.) с множества IP
- **НИ ОДНОГО успешного входа** — только `Failed password` в логах

### Утечки
- **LiqPay ключи** — sandbox (тестовые), не боевые → финансового ущерба нет
- **Все env-переменные контейнеров** потенциально скомпрометированы (JWT_SECRET, ADMIN_TOKEN, пароли SMTP и др.), т.к. атакующие имели shell в контейнере
- **Данные в БД** — база `test1` не существовала, поэтому пользовательских данных для кражи не было

---

## 4. ЧТО СДЕЛАЛИ (выполнено)

- [x] Убили криптомайнер (kill -9)
- [x] Остановили все Docker-контейнеры
- [x] Удалили все заражённые контейнеры (spy_bot, spy_api, spy_db, bus-caddy-1)
- [x] Удалили заражённые volumes (spy_bot_pgdata, bus_pgdata, bus_caddy_*)
- [x] Очистили Docker (docker system prune -a --volumes)
- [x] Убили все вредоносные процессы lxd
- [x] Проверили crontab — чисто, нет вредоносных заданий
- [x] Проверили /tmp — чисто
- [x] Порт 5432 больше не открыт

### Текущее состояние VPS
- CPU: 0% (был 100%)
- RAM: свободна
- Docker: пусто
- Открытые порты: 80 (nginx), 22 (SSH), 53 (DNS) — нормально

---

## 5. ЧТО НЕОБХОДИМО ДОДЕЛАТЬ

### 5.1. Для кодинг-агента (изменения в коде)

#### A. Исправить `docker-compose.yml`

```yaml
version: '3.8'

services:
  db:
    image: postgres:14
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    # КРИТИЧНО: порт ТОЛЬКО для localhost, НЕ открывать наружу
    ports:
      - "127.0.0.1:5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    # Ограничения ресурсов
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M

  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    restart: always
    depends_on:
      - db
    env_file:
      - .env
    # ТОЛЬКО localhost — nginx будет проксировать
    ports:
      - "127.0.0.1:8000:8000"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: always
    depends_on:
      - backend
    env_file:
      - .env
    # ТОЛЬКО localhost
    ports:
      - "127.0.0.1:3000:3000"

volumes:
  pgdata:
```

#### B. Создать `.env` файл (вынести все секреты из docker-compose.yml)

```env
# Database
POSTGRES_DB=bustickets
POSTGRES_USER=busapp
POSTGRES_PASSWORD=<СГЕНЕРИРОВАТЬ: openssl rand -base64 32>
DATABASE_URL=postgresql://busapp:<ТОТ_ЖЕ_ПАРОЛЬ>@db:5432/bustickets

# App
JWT_SECRET=<СГЕНЕРИРОВАТЬ: openssl rand -base64 32>
ADMIN_USERNAME=<ПРИДУМАТЬ>
ADMIN_PASSWORD=<СГЕНЕРИРОВАТЬ: openssl rand -base64 16>
ADMIN_TOKEN=<СГЕНЕРИРОВАТЬ: openssl rand -base64 32>
TICKET_LINK_SECRET=<СГЕНЕРИРОВАТЬ: openssl rand -base64 32>
TICKET_LINK_TTL_DAYS=3

# LiqPay (пока sandbox)
LIQPAY_PUBLIC_KEY=sandbox_i84795238845
LIQPAY_PRIVATE_KEY=sandbox_EV9oE4D9nfHAIiD7A0kfyN5kkae9Ss9S01pyyD9D
LIQPAY_CURRENCY=UAH

# URLs
APP_PUBLIC_URL=https://maximovtours.com/
CLIENT_APP_BASE=https://maximovtours.com/
PUBLIC_API_BASE=https://maximovtours.com/api/
CORS_ORIGINS=https://maximovtours.com

# Ports (внутренние)
BACKEND_PORT=8000
FRONTEND_PORT=3000
POSTGRES_PORT=5432
POSTGRES_HOST_PORT=5433
DB_HOST=db

# SMTP (настроить когда будет реальный)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=example
SMTP_PASSWORD=changeme
SMTP_FROM=noreply@example.com
SMTP_FROM_NAME=Bus Tickets
```

#### C. Добавить `.env` в `.gitignore`

```
.env
.env.local
.env.production
```

#### D. Создать `.env.example` (без секретов, для документации)

```env
POSTGRES_DB=bustickets
POSTGRES_USER=busapp
POSTGRES_PASSWORD=CHANGE_ME
DATABASE_URL=postgresql://busapp:CHANGE_ME@db:5432/bustickets
JWT_SECRET=CHANGE_ME
ADMIN_USERNAME=CHANGE_ME
ADMIN_PASSWORD=CHANGE_ME
ADMIN_TOKEN=CHANGE_ME
# ... остальные переменные
```

#### E. Убрать секреты из frontend-контейнера

В текущем `docker-compose.yml` ВСЕ env-переменные (включая DATABASE_URL, LIQPAY_PRIVATE_KEY, JWT_SECRET) передаются во frontend-контейнер. Это неправильно — frontend не должен знать пароль от БД или приватный ключ LiqPay.

Frontend-сервис должен получать только:
```
APP_PUBLIC_URL, PUBLIC_API_BASE, FRONTEND_PORT
```

#### F. Добавить healthcheck в docker-compose.yml

```yaml
  db:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $POSTGRES_USER -d $POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    depends_on:
      db:
        condition: service_healthy
```

### 5.2. Для администратора (выполнить на VPS)

#### A. Защитить SSH

```bash
# 1. Убедиться что SSH-ключ настроен (ПЕРЕД отключением паролей!)
# На ЛОКАЛЬНОЙ машине:
ssh-copy-id root@<IP_VPS>

# 2. На VPS — отключить вход по паролю:
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd
```

#### B. Настроить файрвол (UFW)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS (когда настроите SSL)
# НЕ открывать 5432, 5433, 8000, 3000!
ufw enable
ufw status
```

#### C. Установить fail2ban

```bash
apt update && apt install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

#### D. Настроить автоматические обновления безопасности

```bash
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

#### E. Настроить бэкапы базы данных

```bash
# Создать директорию для бэкапов
mkdir -p /root/backups

# Создать скрипт бэкапа
cat > /root/backups/backup-db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/root/backups
DAYS_TO_KEEP=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Дамп базы из Docker-контейнера
docker exec bus-db-1 pg_dump -U busapp bustickets | gzip > $BACKUP_DIR/db_$TIMESTAMP.sql.gz

# Удалить бэкапы старше N дней
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +$DAYS_TO_KEEP -delete

echo "Backup completed: db_$TIMESTAMP.sql.gz"
EOF

chmod +x /root/backups/backup-db.sh

# Добавить в cron (ежедневно в 3:00)
(crontab -l 2>/dev/null; echo "0 3 * * * /root/backups/backup-db.sh >> /root/backups/backup.log 2>&1") | crontab -
```

#### F. Настроить SSL (HTTPS)

Вариант 1 — через Nginx + Certbot:
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-api-domain.com
```

Вариант 2 — если API доступен только через Netlify proxy, SSL на VPS не обязателен, но рекомендуется.

### 5.3. Последовательность безопасного перезапуска

```bash
# 1. Создать .env файл с новыми паролями
cd ~/bus
nano .env  # вставить содержимое из раздела 5.1.B

# 2. Сгенерировать пароли
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"
echo "JWT_SECRET=$(openssl rand -base64 32)"
echo "ADMIN_TOKEN=$(openssl rand -base64 32)"
echo "ADMIN_PASSWORD=$(openssl rand -base64 16)"
echo "TICKET_LINK_SECRET=$(openssl rand -base64 32)"

# 3. Обновить docker-compose.yml (убрать хардкод env, добавить env_file)

# 4. Настроить файрвол ПЕРЕД запуском
ufw enable

# 5. Запустить
docker compose up -d --build

# 6. Проверить
docker compose logs --tail=20
docker compose ps
ss -tlnp  # убедиться что 5432 НЕ открыт наружу
```

---

## 6. ЧЕКЛИСТ БЕЗОПАСНОСТИ

### Критичное (сделать ДО запуска)
- [ ] Порт PostgreSQL закрыт снаружи (127.0.0.1 в docker-compose)
- [ ] Пароль PostgreSQL сменён с `postgres` на сложный
- [ ] Все секреты (JWT, admin, ticket) сменены
- [ ] Секреты вынесены в .env, .env добавлен в .gitignore
- [ ] Frontend-контейнер не получает секреты бэкенда
- [ ] UFW файрвол настроен и включен

### Важное (сделать в ближайшее время)
- [ ] SSH вход по ключу, пароли отключены
- [ ] fail2ban установлен
- [ ] Бэкапы БД настроены по cron
- [ ] SSL/HTTPS настроен
- [ ] Автообновления безопасности включены

### На будущее (при переходе в продакшн)
- [ ] Заменить sandbox LiqPay ключи на боевые
- [ ] Настроить реальный SMTP
- [ ] Настроить мониторинг (uptime, CPU alerts)
- [ ] Рассмотреть отдельный пользователь PostgreSQL для приложения (не postgres/superuser)
- [ ] Рассмотреть Docker secrets вместо .env для продакшн

---

## 7. ИТОГОВАЯ ОЦЕНКА УЩЕРБА

| Параметр | Статус |
|----------|--------|
| Финансовый ущерб | ❌ Нет (LiqPay sandbox) |
| Утечка данных пользователей | ❌ Нет (БД test1 не существовала) |
| Компрометация SSH | ❌ Нет (только failed attempts) |
| Криптомайнинг | ✅ Да, ~166 дней на 4 ядрах |
| Расход ресурсов VPS | ✅ Да (CPU, RAM, трафик ~7 ГБ) |
| Компрометация секретов | ⚠️ Потенциально (env-переменные в контейнерах) |
| Компрометация исходного кода | ❌ Нет |
| Доступ к хосту | ⚠️ Частично (процессы lxd на хосте, но без root) |
