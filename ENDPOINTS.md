# Обзор API и уровни доступа

Документ описывает все HTTP-эндпоинты FastAPI-приложения и группирует их по требуемому типу доступа. Под "токеном администратора" понимается JWT с ролью `admin`, который передаётся в заголовке `Authorization: Bearer …`. Билетные действия используют короткоживущие токены ссылок и/или cookie-сессии.

## Типы доступа

- **Публичный** – запросы, которые выполняются без каких-либо токенов. Некоторые маршруты дополнительно принимают `X-Ticket-Token` или параметры для привязки к билету, но формально не проверяют их наличие.
- **Пользовательский JWT** – требуется bearer-токен, выданный после авторизации пользователя (роль не важна).
- **Только администратор** – маршруты с зависимостью `require_admin_token`, принимают только JWT с ролью `admin`.
- **Билетный токен или админ** – маршруты с зависимостью `require_scope(...)`. Их можно вызвать либо с админским JWT, либо с действительным `X-Ticket-Token` / `token` в query-параметре, содержащим указанные scope.
- **Публичная сессия (cookie)** – маршруты из блока `/public`, которые работают только при наличии корректного cookie-сессионного идентификатора и CSRF-заголовка, полученных через ссылку на билет.

## Публичные маршруты

| Метод | Путь | Назначение и особенности |
| --- | --- | --- |
| GET | `/health` | Простой health-check сервера. |
| POST | `/auth/register` | Регистрация нового пользователя. |
| POST | `/auth/login` | Авторизация и выдача JWT. |
| POST | `/purchase/` | Создание бронирования со статусом `reserved`, возвращает ссылки на билеты. |
| POST | `/book` | Псевдоним для создания бронирования, используется на публичной витрине. |
| POST | `/purchase` | Создание бронирования со статусом `paid`; при наличии токена проверяет scope `pay`, без токена выполняется как публичный вызов. |
| POST | `/pay` | Для non-admin возвращает `200` с LiqPay payload (`provider`, `data`, `signature`, `payload`) для онлайн-оплаты заказа; для admin выполняет офлайн-пометку оплаты и возвращает `204 No Content`. Для non-admin обязателен билетный токен со scope `pay`, привязанный к этому же `purchase_id`; admin может вызывать с bearer JWT. |
| POST | `/cancel/{purchase_id}` | Отмена бронирования. Поддерживает необязательный токен со scope `cancel`. |
| POST | `/refund/{purchase_id}` | Полный возврат по бронированию. Поддерживает необязательный токен со scope `cancel`. |
| POST | `/selected_route` | Возвращает данные демо-маршрутов (используется посадочной страницей). |
| POST | `/selected_pricelist` | Возвращает демо-прайслист с ценами. |
| OPTIONS | `/selected_route` | CORS preflight для публичного демо-маршрута. |
| POST | `/search/departures` | Список отправлений с доступными местами для указанного количества пассажиров. |
| POST | `/search/arrivals` | Список пунктов назначения для выбранной отправной точки. |
| GET | `/search/dates` | Доступные даты рейсов между двумя остановками. |
| OPTIONS | `/search/departures`, `/search/arrivals` | Preflight-запросы для CORS. |
| GET | `/tours/search` | Поиск рейсов по датам/остановкам, используется публичной страницей покупки. |
| GET | `/seat/` | Возвращает схему мест. При `adminMode=false` требуется указать сегмент маршрута; при `adminMode=true` отдаёт полную схему без авторизации. |
| GET | `/passengers/` | Демонстрационный список пассажиров (заглушка). |
| POST | `/passengers/` | Демонстрационное создание пассажира (заглушка). |
| POST | `/tickets/` | Ручная выдача билета и генерация ссылки для посадки. |
| GET | `/tickets/{ticket_id}/pdf` | Генерация PDF билета. При наличии `token`/`X-Ticket-Token` проверяет scope `view`, без него доступен как публичный экспорт. |
| DELETE | `/tickets/{ticket_id}` | Удаление билета с возвратом мест в продаже. |
| GET | `/q/{opaque}` | Обмен одноразовой ссылки (QR) на cookie-сессию для публичного кабинета. |

## Маршруты, требующие пользовательский JWT

| Метод | Путь | Назначение |
| --- | --- | --- |
| GET | `/auth/verify` | Проверка валидности пользовательского токена. |

## Маршруты только для администратора

| Метод | Путь | Назначение |
| --- | --- | --- |
| GET | `/stops/` | Список остановок. |
| POST | `/stops/` | Создание остановки. |
| GET | `/stops/{stop_id}` | Получение остановки по ID. |
| PUT | `/stops/{stop_id}` | Обновление остановки. |
| DELETE | `/stops/{stop_id}` | Удаление остановки. |
| GET | `/routes/` | Список маршрутов. |
| GET | `/routes/demo` | Список маршрутов, отмеченных как демо. |
| POST | `/routes/` | Создание маршрута. |
| PUT | `/routes/{route_id}` | Обновление маршрута. |
| DELETE | `/routes/{route_id}` | Удаление маршрута. |
| PUT | `/routes/{route_id}/demo` | Переключение признака демо у маршрута. |
| GET | `/routes/{route_id}/stops` | Список остановок маршрута. |
| POST | `/routes/{route_id}/stops` | Добавление остановки в маршрут. |
| PUT | `/routes/{route_id}/stops/{routestop_id}` | Обновление остановки маршрута. |
| DELETE | `/routes/{route_id}/stops/{routestop_id}` | Удаление остановки из маршрута. |
| GET | `/pricelists/` | Список прайс-листов. |
| POST | `/pricelists/` | Создание прайс-листа. |
| PUT | `/pricelists/{pricelist_id}` | Обновление прайс-листа. |
| PUT | `/pricelists/{pricelist_id}/demo` | Отметка прайс-листа как демо. |
| DELETE | `/pricelists/{pricelist_id}` | Удаление прайс-листа. |
| GET | `/prices/` | Список цен (с фильтром по прайс-листу). |
| POST | `/prices/` | Создание цены. |
| PUT | `/prices/{price_id}` | Обновление цены. |
| DELETE | `/prices/{price_id}` | Удаление цены. |
| GET | `/available/` | Просмотр остатков мест по сегментам. |
| POST | `/available/` | Создание записи доступности. |
| PUT | `/available/{available_id}` | Обновление записи доступности. |
| DELETE | `/available/{available_id}` | Удаление записи доступности. |
| POST | `/report/` | Формирование отчёта по продажам билетов. |
| GET | `/admin/tickets/` | Список билетов рейса с пассажирами. |
| PUT | `/admin/tickets/{ticket_id}` | Редактирование билета (остановки, пассажир, багаж). |
| POST | `/admin/tickets/reassign` | Пересадка пассажиров между местами. |
| DELETE | `/admin/tickets/{ticket_id}` | Удаление билета от имени администратора. |
| GET | `/admin/purchases/` | Список заказов с фильтрами. |
| GET | `/admin/purchases/{purchase_id}` | Детали заказа, связанные билеты и лог. |
| GET | `/bundle/admin/selected_route` | Чтение выбранных маршрутов для демо-бандла. |
| POST | `/bundle/admin/selected_route` | Сохранение выбранных маршрутов для демо-бандла. |
| GET | `/bundle/admin/selected_pricelist` | Чтение выбранного прайс-листа. |
| POST | `/bundle/admin/selected_pricelist` | Сохранение выбранного прайс-листа. |
| GET | `/tours/` | Список рейсов. |
| GET | `/tours/list` | Пагинированный список рейсов с фильтрами. |
| POST | `/tours/` | Создание рейса с раскладкой мест. |
| PUT | `/tours/{tour_id}` | Обновление рейса и доступности мест. |
| DELETE | `/tours/{tour_id}` | Удаление рейса (с опцией `force`). |
| PUT | `/seat/block` | Блокировка/разблокировка места рейса. |

## Маршруты с проверкой билетного токена (scope) или админа

| Метод | Путь | Требуемый scope | Назначение |
| --- | --- | --- | --- |
| GET | `/tickets/{ticket_id}` | `view` | Детали билета, доступные действия и ссылка на PDF. |
| GET | `/tickets/{ticket_id}/seat-map` | `view` | Схема мест тура с подсветкой доступных для пересадки сегментов. |
| PATCH | `/tickets/{ticket_id}` | `edit` | Обновление данных пассажира, багажа или сегмента поездки. |
| POST | `/tickets/{ticket_id}/seat` | `seat` | Смена места в рамках того же рейса. |
| POST | `/tickets/{ticket_id}/reschedule` | `reschedule` | Перенос билета на другой рейс или сегмент. |
| POST | `/tickets/reassign` | `edit` | Массовая пересадка между местами внутри рейса. |
| POST | `/purchase/{purchase_id}/pay` | `pay` | Изменение статуса заказа на `paid`, запись продажи с `method=offline` и повторная выдача ссылок. |
| POST | `/purchase/{purchase_id}/cancel` | `cancel` | Отмена заказа с освобождением мест и записью в лог продаж. |

### Отдельный режим авторизации для внешнего фронта (`POST /pay`)

### Ответы `POST /pay`

- `200 OK` — non-admin сценарий: возвращается LiqPay payload вида `{ provider, data, signature, payload }` для перенаправления на оплату.
- `204 No Content` — admin-сценарий: заказ помечается как оплаченный офлайн, в `sales` пишется `category=paid` и `method=offline`, тело ответа отсутствует.

- Эндпоинт `POST /pay` предназначен для сценария внешнего фронта с билетными ссылками и **не использует cookie-session + CSRF** из `/public/...`.
- Для non-admin запроса обязательно передать `X-Ticket-Token` (или `?token=`) со scope `pay`.
- Токен должен быть выпущен для того же заказа: `purchase_id` из токена обязан совпадать с `purchase_id` в теле запроса.
- При отсутствии токена возвращается `401`, при отсутствии scope `pay` или несовпадении заказа — `403`.

## Публичный кабинет по cookie-сессии

| Метод | Путь | Назначение и требования |
| --- | --- | --- |
| GET | `/public/tickets/{ticket_id}` | Возвращает DTO билета после проверки cookie и CSRF. |
| GET | `/public/purchase/{purchase_id}` | Детали заказа и список билетов. |
| GET | `/public/tickets/{ticket_id}/pdf` | Генерация PDF билета в контексте публичной сессии. |
| GET | `/public/purchase/{purchase_id}/pdf` | Архив PDF-файлов всех билетов заказа. |
| POST | `/public/purchase/{purchase_id}/pay` | Формирование платёжных данных (LiqPay) для доплаты по заказу. Требует CSRF. |
| POST | `/public/purchase/{purchase_id}/reschedule/quote` | Предварительный расчёт доплаты/возврата при переносе билетов. |
| POST | `/public/purchase/{purchase_id}/reschedule` | Подтверждение переноса билетов, пересчёт сумм и логирование. |
| POST | `/public/purchase/{purchase_id}/baggage/quote` | Расчёт изменения суммы при добавлении/уборке дополнительного багажа. |
| POST | `/public/purchase/{purchase_id}/baggage` | Применение изменений по багажу и обновление заказа. |
| POST | `/public/purchase/{purchase_id}/cancel` | Частичная или полная отмена билетов в заказе, очистка cookie при полном возврате. |

## Детальные payload-контракты по публичным эндпоинтам

> Ниже перечислены именно публично доступные маршруты (без обязательного admin JWT). Для маршрутов из `/public/...` дополнительно требуются cookie-сессия после `GET /q/{opaque}` и, для mutating-операций, заголовок `X-CSRF`.

### Базовые и auth

#### `GET /health`
- **Body:** отсутствует.
- **200:** `{ "status": "ok" }`.

#### `POST /auth/register`
- **Body:**
```json
{
  "username": "string",
  "email": "user@example.com",
  "password": "string",
  "role": "user"
}
```
- **200:** `{ "id": 1, "username": "...", "email": "...", "role": "user" }`.

#### `POST /auth/login`
- **Body:**
```json
{ "username": "string", "password": "string" }
```
- **200:** `{ "token": "<jwt>" }`.
- **401:** `Invalid credentials`.

### Бронирование/покупка (внешний публичный поток)

#### Общий payload для `POST /purchase/`, `POST /book`, `POST /purchase`
- **Body:**
```json
{
  "tour_id": 101,
  "seat_nums": [5, 6],
  "passenger_names": ["Ivan Ivanov", "Petar Petrov"],
  "passenger_phone": "+380501234567",
  "passenger_email": "mail@example.com",
  "departure_stop_id": 1,
  "arrival_stop_id": 4,
  "adult_count": 2,
  "discount_count": 0,
  "extra_baggage": [false, true],
  "purchase_id": null,
  "lang": "bg"
}
```
- **200:**
```json
{
  "purchase_id": 555,
  "amount_due": 3200.0,
  "tickets": [
    { "ticket_id": 9001, "deep_link": "https://.../q/..." }
  ]
}
```

#### `POST /pay`
- **Body:**
```json
{ "purchase_id": 555 }
```
- **Non-admin (`X-Ticket-Token` со scope `pay`) → 200:**
```json
{
  "provider": "liqpay",
  "data": "base64...",
  "signature": "...",
  "payload": {
    "version": "3",
    "public_key": "...",
    "action": "pay",
    "amount": 3200.0,
    "currency": "UAH",
    "description": "...",
    "order_id": "purchase-555-...",
    "result_url": "https://...",
    "server_url": "https://.../public/payment/liqpay/callback"
  }
}
```
- **Admin JWT → 204 No Content** (офлайн-оплата).
- **401/403:** нет токена/нет scope/чужой `purchase_id`.

#### `POST /cancel/{purchase_id}`
- **Body:** отсутствует.
- **204:** успешно.

#### `POST /refund/{purchase_id}`
- **Body:** отсутствует.
- **204:** успешно.

### Публичные данные для витрины

#### `POST /selected_route`
- **Body:** `{ "lang": "bg" }`.
- **200:**
```json
{
  "forward": { "id": 1, "name": "...", "stops": [{ "id": 1, "name": "...", "arrival_time": "08:00", "departure_time": "08:10" }] },
  "backward": { "id": 2, "name": "...", "stops": [] }
}
```

#### `POST /selected_pricelist`
- **Body:** `{ "lang": "bg" }`.
- **200:**
```json
{
  "pricelist_id": 1,
  "currency": "UAH",
  "prices": [
    {
      "departure_stop_id": 1,
      "departure_name": "Sofia",
      "arrival_stop_id": 4,
      "arrival_name": "Kyiv",
      "price": 1600.0
    }
  ]
}
```

#### `POST /search/departures`
- **Body:** `{ "lang": "bg", "seats": 2 }`.
- **200:** `[{ "id": 1, "stop_name": "..." }]`.

#### `POST /search/arrivals`
- **Body:** `{ "lang": "bg", "departure_stop_id": 1, "seats": 2 }`.
- **200:** `[{ "id": 4, "stop_name": "..." }]`.

#### `GET /search/dates?departure_stop_id=1&arrival_stop_id=4&seats=2`
- **Body:** отсутствует.
- **200:** массив дат, например `['2026-03-01', '2026-03-05']`.

#### `GET /tours/search?departure_stop_id=1&arrival_stop_id=4&date=2026-03-01&seats=2`
- **200:**
```json
[
  {
    "id": 77,
    "date": "2026-03-01",
    "seats": 40,
    "layout_variant": 1,
    "departure_time": "08:00",
    "arrival_time": "20:00",
    "price": 1600.0
  }
]
```

#### `GET /seat/?tour_id=77&departure_stop_id=1&arrival_stop_id=4&adminMode=false`
- **200:**
```json
{
  "seats": [
    { "seat_id": 11, "seat_num": 1, "status": "available" },
    { "seat_id": 12, "seat_num": 2, "status": "blocked" }
  ]
}
```

#### `GET /passengers/`
- **200:** `[{ "id": 1, "name": "Test Passenger" }]`.

#### `POST /passengers/`
- **Body:** `{ "name": "Test Passenger" }`.
- **200:** `{ "id": 999, "name": "Created Passenger" }`.

### Публичные ticket-операции

#### `POST /tickets/`
- **Body:**
```json
{
  "tour_id": 77,
  "seat_num": 5,
  "purchase_id": 555,
  "passenger_name": "Ivan Ivanov",
  "passenger_phone": "+380501234567",
  "passenger_email": "mail@example.com",
  "departure_stop_id": 1,
  "arrival_stop_id": 4,
  "extra_baggage": false,
  "lang": "bg"
}
```
- **200:** `{ "ticket_id": 9001, "deep_link": "https://.../q/..." }` (дополнительно могут прийти обогащённые поля маршрута/даты).

#### `GET /tickets/{ticket_id}/pdf?lang=bg`
- **Body:** отсутствует.
- **Headers (опц.):** `X-Ticket-Token` или `?token=`.
- **200:** PDF (`application/pdf`).

#### `DELETE /tickets/{ticket_id}`
- **Body:** отсутствует.
- **204:** успешно.

### Сессия публичного кабинета

#### `GET /q/{opaque}`
- Обменивает QR/deep-link на cookies:
  - `minicab_purchase_{purchase_id}` (httpOnly),
  - `mc_csrf` (для последующих POST).
- **302:** redirect на клиентский URL заказа.

### `/public/...` — кабинет по cookie-сессии

#### `GET /public/tickets/{ticket_id}`
- **Body:** отсутствует.
- **200:** DTO билета (ключ `ticket` + денормализованные поля маршрута/пассажира/цены).

#### `POST /public/tickets/{ticket_id}/reschedule`
- **Body:**
```json
{ "tour_id": 88, "seat_num": 9 }
```
- **200:** обновлённый DTO билета.

#### `GET /public/purchase/{purchase_id}`
- **200:** агрегированные данные покупки + список билетов.

#### `GET /public/tickets/{ticket_id}/pdf`
- **200:** PDF билета.

#### `GET /public/purchase/{purchase_id}/pdf`
- **200:** ZIP-архив PDF билетов (`application/zip`).

#### `POST /public/purchase/{purchase_id}/pay`
- **Body:** отсутствует.
- **200:** LiqPay checkout payload (`provider`, `data`, `signature`, `payload`).

#### `POST /public/purchase/{purchase_id}/reschedule/quote`
- **Body:**
```json
{
  "tickets": [
    { "ticket_id": 9001, "new_tour_id": 88, "seat_num": 9 }
  ]
}
```
- **200:** расчёт (`tickets`, `total_delta`, `current_amount_due`, `new_amount_due`, `need_payment`).

#### `POST /public/purchase/{purchase_id}/reschedule`
- **Body:** такой же, как у `.../reschedule/quote`.
- **200:** применение расчёта + обновлённые суммы заказа.

#### `POST /public/purchase/{purchase_id}/baggage/quote`
- **Body:**
```json
{
  "tickets": [
    { "ticket_id": 9001, "extra_baggage": 1 }
  ]
}
```
- **200:** расчёт по багажу (`tickets`, `total_delta`, `current_amount_due`, `new_amount_due`, `need_payment`).

#### `POST /public/purchase/{purchase_id}/baggage`
- **Body:** такой же, как у `.../baggage/quote`.
- **200:** применённые изменения по багажу + обновлённые суммы.

#### `POST /public/purchase/{purchase_id}/cancel/preview`
- **Body:**
```json
{ "ticket_ids": [9001, 9002] }
```
- **200:** предварительный расчёт отмены (`ticket_ids`, `amount_delta`, `current_amount_due`, `new_amount_due`, `need_payment`).

#### `POST /public/purchase/{purchase_id}/cancel`
- **Body:** `{ "ticket_ids": [9001, 9002] }`.
- **200:** `{ cancelled_ticket_ids, amount_delta, current_amount_due, new_amount_due, remaining_tickets }`.
- При полном обнулении билетов очищается purchase-cookie.

### LiqPay интеграция (публичная)

#### `GET /public/payments/resolve?order_id=purchase-555-...`
- **200:**
```json
{
  "status": "paid",
  "purchaseId": 555,
  "purchase": {
    "id": 555,
    "status": "paid",
    "amount_due": 0,
    "customer_email": "mail@example.com",
    "customer_name": "Ivan"
  }
}
```

#### `POST /public/payment/liqpay/callback`
- **Body:** form-data или JSON с полями `data` и `signature`.
- **200:**
```json
{ "ok": true, "status": "paid", "purchase_id": 555, "payment_id": "..." }
```
