-- Persist LiqPay order mapping and last known status per purchase.
ALTER TABLE public.purchase
    ADD COLUMN IF NOT EXISTS liqpay_order_id TEXT,
    ADD COLUMN IF NOT EXISTS liqpay_status TEXT,
    ADD COLUMN IF NOT EXISTS liqpay_payment_id TEXT,
    ADD COLUMN IF NOT EXISTS liqpay_payload JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS purchase_liqpay_order_id_uidx
    ON public.purchase (liqpay_order_id)
    WHERE liqpay_order_id IS NOT NULL;
