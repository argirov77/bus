# Инструкция по интеграции LiqPay в бэкенд

## 1. Настройка окружения
1. Получите публичный и приватный ключи мерчанта в кабинете LiqPay.
2. Добавьте их в `.env` (см. пример `.env.example`):
   ```bash
   LIQPAY_PUBLIC_KEY=<публичный_ключ>
   LIQPAY_PRIVATE_KEY=<приватный_ключ>
   # Опционально, код валюты (по умолчанию `UAH`)
   LIQPAY_CURRENCY=UAH
   ```
3. Перезапустите контейнер `backend` (или локальный сервер), чтобы переменные подхватились.

## 2. Получение плейлода для платежа
1. Бэкенд рассчитывает задолженность заказа и формирует payload LiqPay в эндпоинте `POST /public/purchase/{purchase_id}/pay`.
2. Запрос должен выполняться из публичного контекста покупки: cookie выдаётся при открытии публичной страницы покупки или билета и затем повторно используется для оплаты.
3. В ответе придёт структура:
   ```json
   {
     "provider": "liqpay",
     "data": "<base64>",
     "signature": "<base64>",
     "payload": {
       "version": "3",
       "public_key": "...",
       "action": "pay",
       "amount": 100.0,
       "currency": "UAH",
       "description": "Purchase #15",
       "order_id": "purchase-15",
       "result_url": "http://frontend/purchase/15"
     }
   }
   ```
   - `amount` — сумма к оплате с учётом задолженности заказа.
   - `order_id` принимает вид `purchase-{purchase_id}` или `ticket-{ticket_id}-{purchase_id}` при оплате конкретного билета.
   - `result_url` указывает на страницу, куда LiqPay вернёт пользователя после оплаты.

## 3. Отправка формы в LiqPay
1. На фронтенде сформируйте форму `POST` на `https://www.liqpay.ua/api/3/checkout` с полями `data` и `signature` из ответа.
2. Дополнительные поля (`language`, `sandbox`, `iframe`) LiqPay берёт из `data`, поэтому их добавление следует делать на стороне бэкенда перед подписью при необходимости.
3. После сабмита LiqPay перенаправит пользователя на `result_url`; убедитесь, что URL указывает на фронтенд вашего проекта.

## 4. Настройка страницы возврата
Бэкенд по умолчанию использует `http://localhost:3001/purchase/{purchase_id}` как базовый `result_url`. Для продакшена обновите значение в функции `_redirect_base_url` (файл `backend/routers/public.py`), чтобы вернуть пользователя на нужный домен, либо реализуйте собственную логику построения ссылки перед сборкой образа.

## 5. Callback от LiqPay
LiqPay отправляет уведомления о статусе платежа на серверный endpoint:

```
POST /public/payment/liqpay/callback
```

В теле запроса ожидаются поля `data` и `signature` (формат urlencoded или JSON). Бэкенд проверяет подпись, обновляет статус заказа
на `paid`, выпускает билеты и отправляет письмо с deep-link'ами по email покупателя. Статусы, отличные от `success`, `sandbox` или
`wait_accept`, возвращаются без изменения заказа.

## 6. Recommended flow for external frontend

Для внешнего фронтенда (без cookie-сессии и CSRF) **канонический endpoint — `POST /pay`**.

`POST /public/purchase/{purchase_id}/pay` остаётся для публичного кабинета на cookie-сессии, открытого через QR/deep-link, и не является основным для внешних интеграций.

### Обязательные заголовки для `POST /pay`

- `Content-Type: application/json`
- `X-Ticket-Token: <ticket_token_with_pay_scope>` для non-admin клиентов
- `Authorization: Bearer <admin_jwt>` — только для админских интеграций (вместо `X-Ticket-Token`)

### Правила авторизации

- non-admin доступ только с `X-Ticket-Token` (или `?token=`), содержащим scope `pay`;
- `purchase_id` в токене обязан совпадать с `purchase_id` в теле запроса;
- без токена ответ `401`, с токеном без scope `pay` или с токеном от другого заказа — `403`;
- admin может вызывать `POST /pay` через bearer JWT.

### Пример запроса/ответа

Запрос:

```http
POST /pay HTTP/1.1
Host: api.example.com
Content-Type: application/json
X-Ticket-Token: eyJhbGciOi...

{
  "purchase_id": 15
}
```

Успешный ответ (`200 OK`):

```json
{
  "provider": "liqpay",
  "data": "<base64>",
  "signature": "<base64>",
  "payload": {
    "version": "3",
    "public_key": "...",
    "action": "pay",
    "amount": 100.0,
    "currency": "UAH",
    "description": "Purchase #15",
    "order_id": "purchase-15",
    "result_url": "https://frontend.example.com/purchase/15"
  }
}
```

Далее фронтенд отправляет `data` и `signature` на `https://www.liqpay.ua/api/3/checkout` (см. раздел 3).
