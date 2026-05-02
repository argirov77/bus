-- Emergency backfill for deployments where schema_migrations says applied,
-- but purchase table still misses LiqPay/fiscal columns.

ALTER TYPE public.payment_method_type ADD VALUE IF NOT EXISTS 'liqpay';

ALTER TABLE public.purchase
    ADD COLUMN IF NOT EXISTS liqpay_order_id TEXT,
    ADD COLUMN IF NOT EXISTS liqpay_status TEXT,
    ADD COLUMN IF NOT EXISTS liqpay_payment_id TEXT,
    ADD COLUMN IF NOT EXISTS liqpay_payload JSONB,
    ADD COLUMN IF NOT EXISTS fiscal_status TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS checkbox_receipt_id TEXT,
    ADD COLUMN IF NOT EXISTS checkbox_fiscal_code TEXT,
    ADD COLUMN IF NOT EXISTS fiscal_last_error TEXT,
    ADD COLUMN IF NOT EXISTS fiscal_attempts INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS fiscalized_at TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS purchase_liqpay_order_id_uidx
    ON public.purchase (liqpay_order_id)
    WHERE liqpay_order_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS purchase_fiscal_status_pending_idx
    ON public.purchase (id)
    WHERE fiscal_status IN ('pending', 'failed');
