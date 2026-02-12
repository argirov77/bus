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
       "result_url": "https://maximovtours.com/return",
       "server_url": "https://maximovtours.com/api/public/payment/liqpay/callback"
     }
   }
   ```
   - `amount` — сумма к оплате с учётом задолженности заказа.
   - `order_id` принимает вид `purchase-{purchase_id}` или `ticket-{ticket_id}-{purchase_id}` при оплате конкретного билета.
   - `result_url` указывает на страницу, куда LiqPay вернёт пользователя после оплаты.
   - `server_url` — публичный HTTPS callback, куда LiqPay отправляет server-to-server уведомления.

## 3. Отправка формы в LiqPay
1. На фронтенде сформируйте форму `POST` на `https://www.liqpay.ua/api/3/checkout` с полями `data` и `signature` из ответа.
2. Дополнительные поля (`language`, `sandbox`, `iframe`) LiqPay берёт из `data`, поэтому их добавление следует делать на стороне бэкенда перед подписью при необходимости.
3. После сабмита LiqPay перенаправит пользователя на `result_url`; убедитесь, что URL указывает на фронтенд вашего проекта.

## 4. Настройка страницы возврата
`result_url` строится из `CLIENT_APP_BASE` (или `APP_PUBLIC_URL`) как `https://<public-domain>/return`.
`server_url` строится из той же базы как `https://<public-domain>/api/public/payment/liqpay/callback`.
LiqPay должен видеть только публичный HTTPS домен, а не внутренние IP/порты (например `38.79.154.248:8000`).
Если переменная не задана или указывает на `localhost`, API вернёт ошибку 500 и не сформирует checkout payload.

## 5. Callback от LiqPay
LiqPay отправляет уведомления о статусе платежа на серверный endpoint:

```
POST /public/payment/liqpay/callback
```

В теле запроса ожидаются поля `data` и `signature` (формат urlencoded или JSON). Бэкенд проверяет подпись, обновляет статус заказа
на `paid`, выпускает билеты и отправляет письмо с deep-link'ами по email покупателя. Статусы, отличные от `success`, `sandbox` или
`wait_accept`, возвращаются без изменения заказа.

## 6. Альтернативный способ авторизации для оплаты (внешний фронт)

Помимо cookie-session сценария `/public/...`, в API есть отдельный endpoint `POST /pay` для внешних интеграций по билетному токену:

- non-admin доступ только с `X-Ticket-Token` (или `?token=`), содержащим scope `pay`;
- `purchase_id` в токене обязан совпадать с `purchase_id` в теле запроса;
- без токена ответ `401`, с токеном без scope `pay` или с токеном от другого заказа — `403`;
- admin может вызывать `POST /pay` через bearer JWT.

## 7. Разрешение статуса оплаты по `order_id`
Добавлен endpoint:

```
GET /public/payments/resolve?order_id=...
```

- валидирует `order_id`;
- находит связанный `purchase_id`;
- смотрит сохранённый статус покупки и последний статус LiqPay в БД;
- при необходимости делает server-to-server verify (`action=status`) в LiqPay;
- при подтверждении оплаты отмечает покупку `paid` тем же путём, что и callback.

Ответ:

```json
{
  "status": "paid|pending|failed",
  "purchaseId": 15,
  "purchase": {
    "id": 15,
    "status": "paid",
    "amount_due": 100.0,
    "customer_email": "...",
    "customer_name": "..."
  }
}
```
