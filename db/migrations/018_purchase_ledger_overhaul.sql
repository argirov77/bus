-- Migration: purchase ledger overhaul and LiqPay-ready schema
-- This migration augments the purchase table, introduces professional
-- payment/refund/ledger tables and replaces the legacy sales table with a
-- compatibility view backed by ledger entries.

BEGIN;

-- 1. Upgrade purchase table with new accounting columns.
ALTER TABLE public.purchase
    ADD COLUMN IF NOT EXISTS external_order_id TEXT,
    ADD COLUMN IF NOT EXISTS currency CHAR(3) NOT NULL DEFAULT 'BGN',
    ADD COLUMN IF NOT EXISTS total_due DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_paid DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_refunded DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

-- Convert status column to plain text while preserving existing values.
ALTER TABLE public.purchase ALTER COLUMN status DROP DEFAULT;
ALTER TABLE public.purchase ALTER COLUMN status TYPE TEXT USING status::TEXT;
ALTER TABLE public.purchase ALTER COLUMN status SET DEFAULT 'reserved';
ALTER TABLE public.purchase ALTER COLUMN status SET NOT NULL;

-- Ensure amount_due is never NULL for backwards compatibility.
ALTER TABLE public.purchase ALTER COLUMN amount_due SET DEFAULT 0;
UPDATE public.purchase SET amount_due = COALESCE(amount_due, 0);

-- Prime totals for legacy data.
UPDATE public.purchase
   SET total_due = COALESCE(amount_due, 0),
       total_paid = COALESCE(total_paid, 0),
       total_refunded = COALESCE(total_refunded, 0),
       updated_at = NOW()
 WHERE total_due IS NULL;

UPDATE public.purchase
   SET updated_at = COALESCE(update_at, updated_at);

UPDATE public.purchase
   SET created_at = COALESCE(created_at, COALESCE(update_at, NOW()))
 WHERE created_at IS NULL;

-- Unique index for external order id used by LiqPay.
CREATE UNIQUE INDEX IF NOT EXISTS purchase_external_order_id_idx
    ON public.purchase(external_order_id)
    WHERE external_order_id IS NOT NULL;

-- Guard rails for totals being non-negative.
ALTER TABLE public.purchase
    ADD CONSTRAINT purchase_total_due_non_negative CHECK (total_due >= 0),
    ADD CONSTRAINT purchase_total_paid_non_negative CHECK (total_paid >= 0),
    ADD CONSTRAINT purchase_total_refunded_non_negative CHECK (total_refunded >= 0);

-- Trigger to touch updated_at on any update.
CREATE OR REPLACE FUNCTION public.tg_purchase_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.amount_due IS DISTINCT FROM OLD.amount_due THEN
        NEW.total_due := COALESCE(NEW.amount_due, 0);
    END IF;
    NEW.updated_at := NOW();
    NEW.update_at := NEW.updated_at;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS purchase_touch_updated_at ON public.purchase;
CREATE TRIGGER purchase_touch_updated_at
BEFORE UPDATE ON public.purchase
FOR EACH ROW
EXECUTE FUNCTION public.tg_purchase_touch_updated_at();

-- 2. Purchase line items representing the snapshot of an order.
CREATE TABLE IF NOT EXISTS public.purchase_line_item (
    id BIGSERIAL PRIMARY KEY,
    purchase_id BIGINT NOT NULL REFERENCES public.purchase(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    ticket_id BIGINT NULL REFERENCES public.ticket(id),
    description TEXT,
    qty INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(12,2) NOT NULL,
    tax_rate NUMERIC(5,2) DEFAULT 0,
    total DECIMAL(12,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS purchase_line_item_purchase_id_idx
    ON public.purchase_line_item(purchase_id);

-- Ensure ticket_id is present for ticket line items.
CREATE OR REPLACE FUNCTION public.purchase_line_item_ticket_check()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.type = 'ticket' AND NEW.ticket_id IS NULL THEN
        RAISE EXCEPTION 'ticket_id is required when type = ticket';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS purchase_line_item_ticket_check ON public.purchase_line_item;
CREATE TRIGGER purchase_line_item_ticket_check
BEFORE INSERT OR UPDATE ON public.purchase_line_item
FOR EACH ROW
EXECUTE FUNCTION public.purchase_line_item_ticket_check();

-- Backfill a baseline line item for legacy purchases so totals stay in sync.
INSERT INTO public.purchase_line_item (purchase_id, type, description, qty, unit_price, total)
SELECT pu.id, 'service', 'Legacy balance', 1, COALESCE(pu.amount_due, 0), COALESCE(pu.amount_due, 0)
  FROM public.purchase pu
 WHERE COALESCE(pu.amount_due, 0) <> 0
   AND NOT EXISTS (
       SELECT 1 FROM public.purchase_line_item pli WHERE pli.purchase_id = pu.id
   );

-- 3. Unified ledger storing all monetary movements.
CREATE TABLE IF NOT EXISTS public.ledger_entry (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMP NOT NULL DEFAULT NOW(),
    entry_type TEXT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'BGN',
    purchase_id BIGINT REFERENCES public.purchase(id),
    payment_id BIGINT,
    refund_id BIGINT,
    actor TEXT,
    comment TEXT
);

CREATE INDEX IF NOT EXISTS ledger_entry_purchase_id_idx
    ON public.ledger_entry(purchase_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ledger_entry_payment_id_idx
    ON public.ledger_entry(payment_id);
CREATE INDEX IF NOT EXISTS ledger_entry_refund_id_idx
    ON public.ledger_entry(refund_id);

-- 4. Payments table capturing LiqPay metadata.
CREATE TABLE IF NOT EXISTS public.payment (
    id BIGSERIAL PRIMARY KEY,
    purchase_id BIGINT NOT NULL REFERENCES public.purchase(id) ON DELETE CASCADE,
    amount DECIMAL(12,2) NOT NULL,
    currency CHAR(3) NOT NULL,
    method TEXT NOT NULL,
    status TEXT NOT NULL,
    paid_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    provider TEXT NOT NULL DEFAULT 'liqpay',
    provider_status TEXT,
    liqpay_payment_id BIGINT,
    liqpay_order_id TEXT,
    action TEXT,
    paytype TEXT,
    is_sandbox BOOLEAN DEFAULT FALSE,
    callback_data_b64 TEXT,
    callback_signature TEXT,
    signature_valid BOOLEAN,
    raw_provider_payload JSONB,
    err_code TEXT,
    err_description TEXT,
    card_mask TEXT,
    card_type TEXT,
    mpi_eci TEXT,
    acq_id TEXT,
    finalized_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS payment_purchase_id_idx
    ON public.payment(purchase_id);
CREATE INDEX IF NOT EXISTS payment_liqpay_payment_id_idx
    ON public.payment(liqpay_payment_id);
CREATE INDEX IF NOT EXISTS payment_purchase_status_idx
    ON public.payment(purchase_id, status);

-- 5. Refunds table tracking partial refunds.
CREATE TABLE IF NOT EXISTS public.refund (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL REFERENCES public.payment(id) ON DELETE CASCADE,
    amount DECIMAL(12,2) NOT NULL,
    reason TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    provider TEXT NOT NULL DEFAULT 'liqpay',
    liqpay_refund_payment_id BIGINT,
    provider_status TEXT,
    err_code TEXT,
    err_description TEXT
);

CREATE INDEX IF NOT EXISTS refund_payment_id_idx
    ON public.refund(payment_id);

-- 6. Payment allocation table to map payments to line items.
CREATE TABLE IF NOT EXISTS public.payment_allocation (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL REFERENCES public.payment(id) ON DELETE CASCADE,
    line_item_id BIGINT NOT NULL REFERENCES public.purchase_line_item(id) ON DELETE CASCADE,
    amount DECIMAL(12,2) NOT NULL
);

ALTER TABLE public.payment_allocation
    ADD CONSTRAINT payment_allocation_unique UNIQUE (payment_id, line_item_id);

CREATE INDEX IF NOT EXISTS payment_allocation_payment_id_idx
    ON public.payment_allocation(payment_id);

-- 7. Helper function to refresh purchase totals based on ledger entries.
CREATE OR REPLACE FUNCTION public.purchase_refresh_financials(target_purchase_id BIGINT)
RETURNS VOID AS $$
DECLARE
    paid_total DECIMAL(12,2);
    refunded_total DECIMAL(12,2);
    due_total DECIMAL(12,2);
    existing_status TEXT;
    computed_status TEXT;
BEGIN
    IF target_purchase_id IS NULL THEN
        RETURN;
    END IF;

    SELECT total_due, status
      INTO due_total, existing_status
      FROM public.purchase
     WHERE id = target_purchase_id
     FOR UPDATE;

    SELECT COALESCE(SUM(CASE
                WHEN entry_type IN ('payment','capture','adjustment+') THEN amount
                ELSE 0 END), 0),
           COALESCE(SUM(CASE
                WHEN entry_type IN ('refund','chargeback','adjustment-') THEN -amount
                ELSE 0 END), 0)
      INTO paid_total, refunded_total
      FROM public.ledger_entry
     WHERE purchase_id = target_purchase_id;

    IF due_total IS NULL THEN
        due_total := 0;
    END IF;

    computed_status := existing_status;

    IF refunded_total >= paid_total AND paid_total > 0 THEN
        computed_status := 'refunded';
    ELSIF paid_total >= due_total AND due_total > 0 THEN
        computed_status := 'paid';
    ELSIF paid_total > 0 AND paid_total < due_total THEN
        computed_status := 'partial';
    ELSIF due_total = 0 THEN
        computed_status := 'cancelled';
    ELSIF paid_total = 0 AND due_total > 0 THEN
        computed_status := 'reserved';
    END IF;

    UPDATE public.purchase
       SET total_paid = paid_total,
           total_refunded = refunded_total,
           status = computed_status,
           updated_at = NOW(),
           update_at = NOW()
     WHERE id = target_purchase_id;
END;
$$ LANGUAGE plpgsql;

-- 8. Recalculate total due when line items change.
CREATE OR REPLACE FUNCTION public.purchase_line_item_recalc()
RETURNS TRIGGER AS $$
DECLARE
    target BIGINT;
    computed_total DECIMAL(12,2);
BEGIN
    target := COALESCE(NEW.purchase_id, OLD.purchase_id);
    IF target IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT COALESCE(SUM(total), 0)
      INTO computed_total
      FROM public.purchase_line_item
     WHERE purchase_id = target;

    UPDATE public.purchase
       SET total_due = computed_total,
           amount_due = computed_total,
           updated_at = NOW(),
           update_at = NOW()
     WHERE id = target;

    PERFORM public.purchase_refresh_financials(target);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS purchase_line_item_recalc ON public.purchase_line_item;
CREATE TRIGGER purchase_line_item_recalc
AFTER INSERT OR UPDATE OR DELETE ON public.purchase_line_item
FOR EACH ROW
EXECUTE FUNCTION public.purchase_line_item_recalc();

-- 9. Trigger to recompute purchase totals when ledger entries are inserted.
CREATE OR REPLACE FUNCTION public.ledger_entry_after_insert()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM public.purchase_refresh_financials(NEW.purchase_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ledger_entry_after_insert ON public.ledger_entry;
CREATE TRIGGER ledger_entry_after_insert
AFTER INSERT ON public.ledger_entry
FOR EACH ROW
EXECUTE FUNCTION public.ledger_entry_after_insert();

-- 10. Validate payment allocation sums.
CREATE OR REPLACE FUNCTION public.payment_allocation_sum_check()
RETURNS TRIGGER AS $$
DECLARE
    target_payment BIGINT;
    allocated_total DECIMAL(12,2);
    payment_amount DECIMAL(12,2);
BEGIN
    target_payment := COALESCE(NEW.payment_id, OLD.payment_id);
    IF target_payment IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT COALESCE(SUM(amount), 0)
      INTO allocated_total
      FROM public.payment_allocation
     WHERE payment_id = target_payment;

    SELECT amount INTO payment_amount
      FROM public.payment
     WHERE id = target_payment;

    IF payment_amount IS NOT NULL AND allocated_total > payment_amount + 0.01 THEN
        RAISE EXCEPTION 'Allocated amount % exceeds payment amount % for payment %',
            allocated_total, payment_amount, target_payment;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS payment_allocation_sum_check ON public.payment_allocation;
CREATE CONSTRAINT TRIGGER payment_allocation_sum_check
AFTER INSERT OR UPDATE OR DELETE ON public.payment_allocation
DEFERRABLE INITIALLY IMMEDIATE
FOR EACH ROW
EXECUTE FUNCTION public.payment_allocation_sum_check();

-- 11. Payment trigger to mirror successful operations into the ledger.
CREATE OR REPLACE FUNCTION public.payment_to_ledger()
RETURNS TRIGGER AS $$
DECLARE
    entry_exists BOOLEAN;
    target_entry_type TEXT;
    entry_amount DECIMAL(12,2);
BEGIN
    IF NEW.status <> 'succeeded' THEN
        RETURN NEW;
    END IF;

    target_entry_type := CASE
        WHEN NEW.action = 'hold' THEN 'hold'
        WHEN NEW.action = 'capture' THEN 'capture'
        ELSE 'payment'
    END;

    SELECT EXISTS (
        SELECT 1 FROM public.ledger_entry
         WHERE payment_id = NEW.id
           AND entry_type = target_entry_type
    ) INTO entry_exists;

    IF NOT entry_exists THEN
        entry_amount := CASE
            WHEN target_entry_type = 'hold' THEN 0
            ELSE NEW.amount
        END;
        INSERT INTO public.ledger_entry (occurred_at, entry_type, amount, currency, purchase_id, payment_id, actor, comment)
        VALUES (COALESCE(NEW.paid_at, NEW.created_at), target_entry_type, entry_amount, NEW.currency, NEW.purchase_id, NEW.id, NULL, NEW.provider_status);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS payment_to_ledger_insert ON public.payment;
CREATE TRIGGER payment_to_ledger_insert
AFTER INSERT OR UPDATE ON public.payment
FOR EACH ROW
EXECUTE FUNCTION public.payment_to_ledger();

-- 12. Refund trigger to push successful refunds into the ledger.
CREATE OR REPLACE FUNCTION public.refund_to_ledger()
RETURNS TRIGGER AS $$
DECLARE
    entry_exists BOOLEAN;
BEGIN
    IF NEW.status <> 'succeeded' THEN
        RETURN NEW;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM public.ledger_entry
         WHERE refund_id = NEW.id AND entry_type = 'refund'
    ) INTO entry_exists;

    IF NOT entry_exists THEN
        INSERT INTO public.ledger_entry (occurred_at, entry_type, amount, currency, purchase_id, payment_id, refund_id, actor, comment)
        SELECT COALESCE(NEW.created_at, NOW()), 'refund', -NEW.amount, pay.currency, pay.purchase_id, NEW.payment_id, NEW.id, NULL, NEW.provider_status
          FROM public.payment pay
         WHERE pay.id = NEW.payment_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS refund_to_ledger_insert ON public.refund;
CREATE TRIGGER refund_to_ledger_insert
AFTER INSERT OR UPDATE ON public.refund
FOR EACH ROW
EXECUTE FUNCTION public.refund_to_ledger();

-- 13. Migrate legacy sales data into the ledger (if present).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sales') THEN
        INSERT INTO public.ledger_entry (occurred_at, entry_type, amount, currency, purchase_id, actor, comment)
        SELECT
            s.date,
            CASE
                WHEN s.category IN ('paid', 'ticket_sale') THEN 'payment'
                WHEN s.category IN ('refunded', 'part_refund') THEN 'refund'
                WHEN s.category = 'cancelled' THEN 'adjustment-'
                ELSE 'hold'
            END,
            CASE
                WHEN s.category IN ('refunded', 'part_refund', 'cancelled') THEN -COALESCE(s.amount,0)
                ELSE COALESCE(s.amount,0)
            END,
            'BGN',
            s.purchase_id,
            s.actor,
            s.comment
        FROM public.sales s;
    END IF;
END
$$;

-- Drop legacy sales table to replace with a compatibility view.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sales') THEN
        DROP TABLE public.sales;
    END IF;
END
$$;

-- Compatibility view exposing legacy columns backed by ledger entries.
CREATE OR REPLACE VIEW public.sales AS
SELECT
    le.id,
    le.occurred_at AS date,
    CASE
        WHEN le.entry_type IN ('payment','capture') THEN 'paid'::sales_category
        WHEN le.entry_type IN ('refund','chargeback','adjustment-') THEN 'refunded'::sales_category
        WHEN le.entry_type = 'hold' THEN 'reserved'::sales_category
        ELSE 'ticket_sale'::sales_category
    END AS category,
    CASE WHEN le.amount < 0 THEN -le.amount ELSE le.amount END AS amount,
    le.purchase_id,
    le.actor,
    NULL::payment_method_type AS method,
    le.comment
FROM public.ledger_entry le;

-- INSTEAD OF trigger to redirect inserts on sales view into the ledger.
CREATE OR REPLACE FUNCTION public.sales_view_insert()
RETURNS TRIGGER AS $$
DECLARE
    entry_type TEXT;
    entry_amount DECIMAL(12,2);
BEGIN
    entry_type := CASE
        WHEN NEW.category IN ('paid', 'ticket_sale') THEN 'payment'
        WHEN NEW.category IN ('refunded', 'part_refund') THEN 'refund'
        WHEN NEW.category = 'cancelled' THEN 'adjustment-'
        ELSE 'hold'
    END;

    entry_amount := COALESCE(NEW.amount, 0);
    IF entry_type IN ('refund', 'chargeback', 'adjustment-') THEN
        entry_amount := -ABS(entry_amount);
    ELSE
        entry_amount := ABS(entry_amount);
    END IF;

    INSERT INTO public.ledger_entry (occurred_at, entry_type, amount, currency, purchase_id, actor, comment)
    VALUES (COALESCE(NEW.date, NOW()), entry_type, entry_amount, 'BGN', NEW.purchase_id, NEW.actor, NEW.comment);

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS sales_view_insert ON public.sales;
CREATE TRIGGER sales_view_insert
INSTEAD OF INSERT ON public.sales
FOR EACH ROW
EXECUTE FUNCTION public.sales_view_insert();

COMMIT;
