-- Open-date return tickets ("открытая дата"): prepaid return-leg vouchers.
-- A round-trip buyer can prepay the return leg without picking a date; later,
-- from the mini-cabinet, they activate it by choosing a tour + seat, which
-- materializes a real (already paid) ticket. Existing tables are untouched.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'open_ticket_status') THEN
        CREATE TYPE open_ticket_status AS ENUM ('open','redeemed','cancelled','expired');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS public.open_ticket (
    id                 SERIAL PRIMARY KEY,
    purchase_id        INTEGER NOT NULL REFERENCES public.purchase(id),
    passenger_id       INTEGER NOT NULL REFERENCES public.passenger(id),
    pricelist_id       INTEGER NOT NULL REFERENCES public.pricelist(id),
    departure_stop_id  INTEGER NOT NULL REFERENCES public.stop(id),
    arrival_stop_id    INTEGER NOT NULL REFERENCES public.stop(id),
    is_discount        BOOLEAN NOT NULL DEFAULT FALSE,
    extra_baggage      INTEGER NOT NULL DEFAULT 0,
    amount_paid        NUMERIC(10,2) NOT NULL,
    status             open_ticket_status NOT NULL DEFAULT 'open',
    expires_at         TIMESTAMP NOT NULL,
    created_at         TIMESTAMP NOT NULL DEFAULT now(),
    redeemed_ticket_id INTEGER REFERENCES public.ticket(id),
    redeemed_at        TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_open_ticket_purchase ON public.open_ticket(purchase_id);
