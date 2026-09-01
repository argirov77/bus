# LiqPay: «refund rejected: status=error»

## Симптом

В админке на странице «Заявки на возврат» после нажатия «Вернуть через
LiqPay» появляется красная строка:

```
LiqPay refund rejected: status=error
```

Заявка при этом уходит в статус `failed` (в UI — «Ошибка»), деньги НЕ
списаны и НЕ возвращены: `liqpay_refund_id` остаётся пустым.

`status=error` — это ответ самого LiqPay на `action=refund`. Причина
всегда лежит в полях `err_code` / `err_description` того же ответа.

## Что теперь пишется в логи и в БД

`backend/services/liqpay.py` логирует весь ответ LiqPay на любой
неуспешный refund:

```
LiqPay refund refused for order_id=purchase-114 amount=1350.0:
status=error code=<err_code> description=<err_description> | raw={...}
```

`backend/routers/refund_admin.py` дополнительно запрашивает у LiqPay
статус заказа (`action=status`) и складывает всё в `failure_reason`
заявки — та же строка возвращается в UI:

```
LiqPay refund rejected: status=error code=... description=...
 (order purchase-114: status=..., amount=..., currency=UAH)
```

Смотреть логи бэкенда:

```bash
docker compose logs backend --since 30m | grep -i "liqpay refund"
```

Смотреть, что сохранилось по конкретной заявке:

```sql
SELECT id, status, amount_requested, failure_reason,
       liqpay_refund_id, liqpay_response
  FROM refund_request
 WHERE id = <request_id>;
```

`liqpay_response` — это сырой JSON от LiqPay, включая `err_code`.

## Разбор причины

Сопоставьте `err_code` с [ошибками LiqPay](https://www.liqpay.ua/documentation/errors).
Чаще всего встречается одно из четырёх:

1. **Платёж не найден по `order_id`.** В `purchase.liqpay_order_id`
   лежит идентификатор, по которому LiqPay не видит успешной оплаты
   (например, заказ оплачивали по другой ссылке, а колонка перезаписана
   более поздней попыткой оплаты). Проверьте, что LiqPay знает этот
   `order_id`, — это видно в подсказке `(order ...: status=...)`.
2. **Платёж ещё не завершён.** `status=wait_accept` (или иной
   не-`success`) означает, что деньги не зачислены и возвращать нечего;
   покупка при этом у нас уже помечена `paid`. Дождитесь `success` или
   отмените платёж на стороне LiqPay.
3. **Сумма больше доступной.** `remaining` в админке считается по нашей
   таблице `sales`, а LiqPay ограничивает возврат суммой конкретного
   платежа за вычетом уже сделанных возвратов. Сравните
   `amount` из подсказки с суммой возврата.
4. **Возвраты через API не разрешены мерчанту** (доступ к API, лимит по
   времени с момента оплаты, ограничение эквайера) — здесь помогает
   только поддержка LiqPay с `err_code` на руках.

## Повторная попытка

Заявка в статусе `failed` теперь снова открывается в админке с формой и
кнопкой «Повторить возврат». Повтор безопасен: шаги, которые уже
прошли (возврат в LiqPay, фискальный чек), пропускаются по сохранённым
`liqpay_refund_id` / `fiscal_receipt_id` — двойного возврата не будет.

Если возвращать нужно не всю сумму, исправьте поле «Сумма возврата»
перед повтором.
