-- Refund requests: tracks customer- or admin-initiated refunds against paid
-- purchases. One row per refund event (partial or full) capturing LiqPay
-- processing state and the linked CheckBox refund receipt.

-- Extend sales_category enum with 'refund_requested' so we can log the moment
-- a customer/admin creates a refund request (amount=0, audit entry only).
ALTER TYPE sales_category ADD VALUE IF NOT EXISTS 'refund_requested';

CREATE TABLE IF NOT EXISTS public.refund_request (
    id                     SERIAL PRIMARY KEY,
    purchase_id            INTEGER NOT NULL REFERENCES public.purchase(id),
    ticket_ids             INTEGER[] NOT NULL DEFAULT '{}',
    amount_requested       NUMERIC(12,2),
    amount_refunded        NUMERIC(12,2),
    currency               TEXT DEFAULT 'UAH',
    -- pending | processing | completed | failed | rejected
    status                 TEXT NOT NULL DEFAULT 'pending',
    requested_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    -- 'customer' | 'admin'
    requested_by           TEXT NOT NULL,
    reason                 TEXT,
    admin_actor            TEXT,
    processed_at           TIMESTAMP,
    liqpay_refund_id       TEXT,
    liqpay_response        JSONB,
    fiscal_receipt_id      TEXT,
    fiscal_receipt_number  TEXT,
    -- pending | sent | done | failed
    fiscal_status          TEXT,
    failure_reason         TEXT
);

CREATE INDEX IF NOT EXISTS idx_refund_request_status   ON public.refund_request(status);
CREATE INDEX IF NOT EXISTS idx_refund_request_purchase ON public.refund_request(purchase_id);

ALTER TABLE public.purchase ADD COLUMN IF NOT EXISTS refund_requested_at TIMESTAMP;
