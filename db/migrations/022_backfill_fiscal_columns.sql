-- Backfill migration for deployments that missed 020_add_fiscal_columns.sql.
-- Safe to run multiple times.
ALTER TABLE public.purchase
    ADD COLUMN IF NOT EXISTS fiscal_status TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS checkbox_receipt_id TEXT,
    ADD COLUMN IF NOT EXISTS checkbox_fiscal_code TEXT,
    ADD COLUMN IF NOT EXISTS fiscal_last_error TEXT,
    ADD COLUMN IF NOT EXISTS fiscal_attempts INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS fiscalized_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS purchase_fiscal_status_pending_idx
    ON public.purchase (id)
    WHERE fiscal_status IN ('pending', 'failed');
