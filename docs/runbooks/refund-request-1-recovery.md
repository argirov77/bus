# Recovery: refund_request id=1 (purchase 64)

## Background

First production refund attempt (2026-06) half-completed:

* LiqPay refund **succeeded** — `liqpay_refund_id=2870201631`, 3500 ₴,
  confirmed by callback.
* CheckBox returned **422** on `POST /api/v1/receipts/service` (wrong
  endpoint for a return receipt), the backend answered 502 and the request
  went to `failed`.
* The row was manually flipped to `status=completed` via SQL as a stopgap so
  the admin "Refund" button could not trigger a second LiqPay refund.

The code fix (refund endpoint switched to `/api/v1/receipts/sell` with
`related_receipt_id`, plus idempotent processing that skips steps with
already-persisted ids) must be **deployed before** running this recovery.

## Steps (run after deploy)

```sql
-- 1) Reset the request to pending, keeping liqpay_refund_id
UPDATE refund_request
SET status = 'pending',
    processed_at = NULL,
    failure_reason = NULL
WHERE id = 1;

-- 2) Verify liqpay_refund_id is still present
SELECT id, status, liqpay_refund_id, fiscal_receipt_id
FROM refund_request
WHERE id = 1;
```

```bash
# 3) Trigger processing — the LiqPay step is skipped thanks to the
#    idempotency guard, CheckBox issues the return receipt ("чек повернення")
curl -X POST http://localhost:8000/admin/refund-requests/1/process \
  -H "Authorization: Bearer <ADMIN_JWT>" \
  -H "Content-Type: application/json" \
  -d '{"refund_amount": 3500, "void_fiscal": true}'
```

## Expected result

* `refund_request.status = 'completed'`
* `liqpay_refund_id = 2870201631` (unchanged — no second refund)
* `fiscal_receipt_id` filled with the new return-receipt id
* `fiscal_status = 'done'`
* Backend log contains:
  `LiqPay refund 2870201631 already done for request=1, skipping`

## If CheckBox returns 422 again

Do **not** tweak the request schema blindly. The response body is now logged
(`CheckBox refund receipt error: status=... body=... payload=...`) — capture
the `body` from the log and escalate with that exact message.
