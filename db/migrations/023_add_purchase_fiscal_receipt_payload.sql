-- Add persisted CheckBox receipt URL and sanitized payload for operator visibility/audit.
ALTER TABLE public.purchase
    ADD COLUMN IF NOT EXISTS fiscal_receipt_url TEXT,
    ADD COLUMN IF NOT EXISTS fiscal_payload JSONB;

-- Keep fiscal status constrained to known values when present.
ALTER TABLE public.purchase
    DROP CONSTRAINT IF EXISTS purchase_fiscal_status_check;

ALTER TABLE public.purchase
    ADD CONSTRAINT purchase_fiscal_status_check
    CHECK (
        fiscal_status IS NULL
        OR fiscal_status IN ('pending', 'processing', 'done', 'failed')
    );
