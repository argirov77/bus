# CheckBox: диагностика смены и добивание refund_request id=1

## Симптом

`POST /api/admin/refund-requests/1/process` → HTTP 502:

```
{"detail":"CheckBox refund failed: Client error '400 Bad Request' for url 'https://api.checkbox.ua/api/v1/shifts'"}
```

Старый `_ensure_shift()` распознавал только статус `OPENED`, начальная
проверка смены глотала любые ошибки (`except Exception: pass`), а
`raise_for_status()` терял тело 400-ответа. Если смена кассира висела в
`CREATED`/`OPENING`/`CLOSING` (или GET-проверка падала), код слепо делал
`POST /api/v1/shifts` и получал 400 «зміна вже відкрита» без какой-либо
диагностики.

После фикса `_ensure_shift()` покрывает все статусы (`null`, `CREATED`,
`OPENING`, `OPENED`, `CLOSING`, `CLOSED`), а на 400 от `POST /shifts`
перечитывает текущую смену кассира и переиспользует её. Тела всех 4xx/5xx
ответов CheckBox теперь логируются (`CheckBox <METHOD> <URL> -> <status>
body=...`).

## Ручная диагностика (выполнять на прод-хосте)

```bash
# 1) Креды из контейнера
docker compose exec -T backend sh -c 'echo "PIN=$CHECKBOX_CASHIER_PIN"; echo "LIC=$CHECKBOX_LICENSE_KEY"; echo "API=${CHECKBOX_API_URL:-https://api.checkbox.ua}"'

# 2) Токен кассира
TOKEN=$(curl -s -X POST "$API/api/v1/cashier/signinPinCode" \
  -H "X-License-Key: $LIC" -H "Content-Type: application/json" \
  -d "{\"pin_code\": \"$PIN\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 3) Текущая смена кассира (главный вопрос: какой status?)
curl -s "$API/api/v1/cashier/shift" -H "Authorization: Bearer $TOKEN" -H "X-License-Key: $LIC" | python3 -m json.tool

# 4) Кассир и привязка к кассе
curl -s "$API/api/v1/cashier/me" -H "Authorization: Bearer $TOKEN" -H "X-License-Key: $LIC" | python3 -m json.tool

# 5) Точное тело 400 при открытии смены
curl -si -X POST "$API/api/v1/shifts" -H "Authorization: Bearer $TOKEN" -H "X-License-Key: $LIC"
```

Альтернатива без кредов: `GET /api/admin/integrations/checkbox/health`
(админ-JWT) — делает signin и показывает статус смены.

### Интерпретация

| Что видно | Значение | Что делает новый код |
|---|---|---|
| шаг 3 → `status=OPENED` | смена уже открыта | переиспользует её (`Using existing OPENED shift`) |
| шаг 3 → `CREATED`/`OPENING` | смена открывается | ждёт до 30 с до `OPENED` |
| шаг 3 → `CLOSING` | смена закрывается | ждёт `CLOSED`, открывает новую |
| шаг 3 → `null`/`CLOSED` | смены нет | `POST /shifts`, ждёт `OPENED` |
| шаг 5 → 400 `shift_already_opened` | гонка/устаревшее состояние | перечитывает смену кассира, переиспользует |
| шаг 5 → 400 про лицензию/кассу | нет `X-License-Key` или кассир не привязан к кассе | чинить в кабинете CheckBox: лицензия, привязка кассира |
| шаг 3/5 → 5xx | проблема на стороне CheckBox | см. «Резервный путь» ниже |

## Прогон refund_request id=1 (после деплоя)

```bash
# откатить заявку в pending (liqpay_refund_id сохраняется)
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "UPDATE refund_request SET status='\''pending'\'', processed_at=NULL, failure_reason=NULL WHERE id=1;"'

# дёрнуть процессинг
curl -i -X POST https://admin.maximovtours.com/api/admin/refund-requests/1/process \
  -H "Authorization: Bearer <ADMIN_JWT>" \
  -H "Content-Type: application/json" \
  -d '{"refund_amount": 3500, "void_fiscal": true}'

# проверка
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT status, liqpay_refund_id, fiscal_receipt_id, fiscal_status FROM refund_request WHERE id=1;"'
```

Ожидаемо: HTTP 200; `status=completed`, `liqpay_refund_id=2870201631`
(не изменился — идемпотентность), `fiscal_receipt_id` = новый UUID,
`fiscal_status=done`. В логах backend:
`LiqPay refund 2870201631 already done for request=1, skipping`,
`Using existing OPENED shift ...` (или `CheckBox shift ... OPENED`),
`CheckBox receipt ... DONE`.

Если снова 502 — в логах backend теперь будет точное тело ответа CheckBox
(`CheckBox POST https://api.checkbox.ua/... -> 4xx body=...`). Не подгонять
схему вслепую — зафиксировать body и разбирать предметно.

## Резервный путь (только если CheckBox сам отдаёт 5xx / не открывает смену)

1. Пробить чек повернення вручную через кабинет CheckBox
   (продажа → повернення по чеку продажи purchase 64).
2. Записать результат в БД:

```sql
UPDATE refund_request
SET fiscal_receipt_id = '<uuid ручного чека>',
    fiscal_receipt_number = '<фіскальний номер>',
    fiscal_status = 'manual',
    status = 'completed',
    processed_at = NOW(),
    failure_reason = NULL
WHERE id = 1;
```

3. Приложить к отчёту ссылку на чек и тело ошибки CheckBox из логов.
