-- Ensure LiqPay payment method can be stored in enum-based columns.
ALTER TYPE public.payment_method_type ADD VALUE IF NOT EXISTS 'liqpay';

-- Ensure LiqPay callback tracking columns exist on purchase in older deployments.
ALTER TABLE public.purchase
    ADD COLUMN IF NOT EXISTS liqpay_order_id TEXT,
    ADD COLUMN IF NOT EXISTS liqpay_status TEXT,
    ADD COLUMN IF NOT EXISTS liqpay_payment_id TEXT,
    ADD COLUMN IF NOT EXISTS liqpay_payload JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS purchase_liqpay_order_id_uidx
    ON public.purchase (liqpay_order_id)
    WHERE liqpay_order_id IS NOT NULL;
