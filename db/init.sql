--
-- PostgreSQL database dump
--

-- Dumped from database version 17.2
-- Dumped by pg_dump version 17.2

-- Started on 2025-06-11 10:02:38

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 228 (class 1259 OID 16609)
-- Name: available; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.available (
    id integer NOT NULL,
    tour_id integer NOT NULL,
    departure_stop_id integer NOT NULL,
    arrival_stop_id integer NOT NULL,
    seats integer NOT NULL
);


ALTER TABLE public.available OWNER TO postgres;

--
-- TOC entry 227 (class 1259 OID 16608)
-- Name: available_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.available_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.available_id_seq OWNER TO postgres;

--
-- TOC entry 4903 (class 0 OID 0)
-- Dependencies: 227
-- Name: available_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.available_id_seq OWNED BY public.available.id;


--
-- TOC entry 234 (class 1259 OID 16670)
-- Name: passenger; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.passenger (
    id integer NOT NULL,
    name character varying(255) NOT NULL
);


ALTER TABLE public.passenger OWNER TO postgres;

--
-- TOC entry 233 (class 1259 OID 16669)
-- Name: passenger_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.passenger_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.passenger_id_seq OWNER TO postgres;

--
-- TOC entry 4904 (class 0 OID 0)
-- Dependencies: 233
-- Name: passenger_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.passenger_id_seq OWNED BY public.passenger.id;


--
-- TOC entry 222 (class 1259 OID 16573)
-- Name: pricelist; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pricelist (
    id integer PRIMARY KEY,
    name character varying(255) NOT NULL
);


ALTER TABLE public.pricelist OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 16572)
-- Name: pricelist_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.pricelist_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pricelist_id_seq OWNER TO postgres;

--
-- TOC entry 4905 (class 0 OID 0)
-- Dependencies: 221
-- Name: pricelist_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.pricelist_id_seq OWNED BY public.pricelist.id;


--
-- TOC entry 232 (class 1259 OID 16648)
-- Name: prices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.prices (
    id integer NOT NULL,
    pricelist_id integer NOT NULL,
    departure_stop_id integer NOT NULL,
    arrival_stop_id integer NOT NULL,
    price numeric(10,2) NOT NULL
);


ALTER TABLE public.prices OWNER TO postgres;

--
-- TOC entry 231 (class 1259 OID 16647)
-- Name: prices_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.prices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.prices_id_seq OWNER TO postgres;

--
-- TOC entry 4906 (class 0 OID 0)
-- Dependencies: 231
-- Name: prices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.prices_id_seq OWNED BY public.prices.id;


--
-- TOC entry 220 (class 1259 OID 16566)
-- Name: route; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.route (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    is_demo boolean NOT NULL DEFAULT false
);


ALTER TABLE public.route OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 16565)
-- Name: route_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.route_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.route_id_seq OWNER TO postgres;

--
-- TOC entry 4907 (class 0 OID 0)
-- Dependencies: 219
-- Name: route_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.route_id_seq OWNED BY public.route.id;


ALTER TABLE ONLY public.route
    ADD CONSTRAINT route_pkey PRIMARY KEY (id);

--
-- TOC entry 230 (class 1259 OID 16631)
-- Name: routestop; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.routestop (
    id integer NOT NULL,
    route_id integer NOT NULL,
    stop_id integer NOT NULL,
    "order" integer NOT NULL,
    arrival_time time without time zone,
    departure_time time without time zone
);


ALTER TABLE public.routestop OWNER TO postgres;

--
-- TOC entry 229 (class 1259 OID 16630)
-- Name: routestop_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.routestop_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.routestop_id_seq OWNER TO postgres;

--
-- TOC entry 4908 (class 0 OID 0)
-- Dependencies: 229
-- Name: routestop_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.routestop_id_seq OWNED BY public.routestop.id;


--
-- TOC entry 226 (class 1259 OID 16597)
-- Name: seat; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.seat (
    id integer NOT NULL,
    tour_id integer NOT NULL,
    seat_num integer NOT NULL,
    available character varying(255) NOT NULL
);


ALTER TABLE public.seat OWNER TO postgres;

--
-- TOC entry 225 (class 1259 OID 16596)
-- Name: seat_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.seat_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.seat_id_seq OWNER TO postgres;

--
-- TOC entry 4909 (class 0 OID 0)
-- Dependencies: 225
-- Name: seat_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.seat_id_seq OWNED BY public.seat.id;


--
-- TOC entry 218 (class 1259 OID 16559)
-- Name: stop; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.stop (
    id integer NOT NULL,
    stop_name character varying(255) NOT NULL,
    stop_en character varying(255),
    stop_bg character varying(255),
    stop_ua character varying(255),
    description text,
    location text
);


ALTER TABLE public.stop OWNER TO postgres;

--
-- TOC entry 217 (class 1259 OID 16558)
-- Name: stop_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.stop_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stop_id_seq OWNER TO postgres;

--
-- TOC entry 4910 (class 0 OID 0)
-- Dependencies: 217
-- Name: stop_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.stop_id_seq OWNED BY public.stop.id;


--
-- TOC entry 236 (class 1259 OID 16679)
-- Name: ticket; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ticket (
    id integer NOT NULL,
    tour_id integer NOT NULL,
    seat_id integer NOT NULL,
    passenger_id integer NOT NULL,
    departure_stop_id integer NOT NULL,
    arrival_stop_id integer NOT NULL,
    purchase_id integer,
    extra_baggage integer DEFAULT 0
);


ALTER TABLE public.ticket OWNER TO postgres;

--
-- TOC entry 235 (class 1259 OID 16678)
-- Name: ticket_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ticket_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ticket_id_seq OWNER TO postgres;

--
-- TOC entry 4911 (class 0 OID 0)
-- Dependencies: 235
-- Name: ticket_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ticket_id_seq OWNED BY public.ticket.id;


--
-- TOC entry 224 (class 1259 OID 16580)
-- Name: tour; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tour (
    id integer NOT NULL,
    route_id integer NOT NULL,
    pricelist_id integer NOT NULL,
    date date NOT NULL,
    seats integer NOT NULL,
    layout_variant integer DEFAULT 1 NOT NULL,
    booking_terms smallint DEFAULT 0 NOT NULL
);


ALTER TABLE public.tour OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 16579)
-- Name: tour_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.tour_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tour_id_seq OWNER TO postgres;

--
-- TOC entry 4912 (class 0 OID 0)
-- Dependencies: 223
-- Name: tour_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.tour_id_seq OWNED BY public.tour.id;

-- Нови таблици за покупки и журнал на продажбите
SET search_path = public;

CREATE TYPE purchase_status AS ENUM ('reserved','paid','cancelled','refunded');
CREATE TYPE payment_method_type AS ENUM ('online','offline');

CREATE TABLE IF NOT EXISTS public.purchase (
    id SERIAL PRIMARY KEY,
    customer_name VARCHAR(255),
    customer_email VARCHAR(255),
    customer_phone VARCHAR(50),
    amount_due DECIMAL(12,2) NOT NULL DEFAULT 0,
    deadline TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'reserved',
    update_at TIMESTAMP,
    payment_method payment_method_type NOT NULL DEFAULT 'online',
    external_order_id TEXT,
    currency CHAR(3) NOT NULL DEFAULT 'BGN',
    total_due DECIMAL(12,2) NOT NULL DEFAULT 0,
    total_paid DECIMAL(12,2) NOT NULL DEFAULT 0,
    total_refunded DECIMAL(12,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT purchase_total_due_non_negative CHECK (total_due >= 0),
    CONSTRAINT purchase_total_paid_non_negative CHECK (total_paid >= 0),
    CONSTRAINT purchase_total_refunded_non_negative CHECK (total_refunded >= 0)
);

CREATE UNIQUE INDEX purchase_external_order_id_idx
    ON public.purchase(external_order_id)
    WHERE external_order_id IS NOT NULL;

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

CREATE TRIGGER purchase_touch_updated_at
BEFORE UPDATE ON public.purchase
FOR EACH ROW
EXECUTE FUNCTION public.tg_purchase_touch_updated_at();

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

CREATE INDEX purchase_line_item_purchase_id_idx
    ON public.purchase_line_item(purchase_id);

CREATE OR REPLACE FUNCTION public.purchase_line_item_ticket_check()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.type = 'ticket' AND NEW.ticket_id IS NULL THEN
        RAISE EXCEPTION 'ticket_id is required when type = ticket';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER purchase_line_item_ticket_check
BEFORE INSERT OR UPDATE ON public.purchase_line_item
FOR EACH ROW
EXECUTE FUNCTION public.purchase_line_item_ticket_check();

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

CREATE INDEX ledger_entry_purchase_id_idx
    ON public.ledger_entry(purchase_id, occurred_at DESC);
CREATE INDEX ledger_entry_payment_id_idx
    ON public.ledger_entry(payment_id);
CREATE INDEX ledger_entry_refund_id_idx
    ON public.ledger_entry(refund_id);

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

CREATE INDEX payment_purchase_id_idx
    ON public.payment(purchase_id);
CREATE INDEX payment_liqpay_payment_id_idx
    ON public.payment(liqpay_payment_id);
CREATE INDEX payment_purchase_status_idx
    ON public.payment(purchase_id, status);

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

CREATE INDEX refund_payment_id_idx
    ON public.refund(payment_id);

CREATE TABLE IF NOT EXISTS public.payment_allocation (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL REFERENCES public.payment(id) ON DELETE CASCADE,
    line_item_id BIGINT NOT NULL REFERENCES public.purchase_line_item(id) ON DELETE CASCADE,
    amount DECIMAL(12,2) NOT NULL,
    CONSTRAINT payment_allocation_unique UNIQUE (payment_id, line_item_id)
);

CREATE INDEX payment_allocation_payment_id_idx
    ON public.payment_allocation(payment_id);

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

CREATE TRIGGER purchase_line_item_recalc
AFTER INSERT OR UPDATE OR DELETE ON public.purchase_line_item
FOR EACH ROW
EXECUTE FUNCTION public.purchase_line_item_recalc();

CREATE OR REPLACE FUNCTION public.ledger_entry_after_insert()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM public.purchase_refresh_financials(NEW.purchase_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_entry_after_insert
AFTER INSERT ON public.ledger_entry
FOR EACH ROW
EXECUTE FUNCTION public.ledger_entry_after_insert();

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

CREATE CONSTRAINT TRIGGER payment_allocation_sum_check
AFTER INSERT OR UPDATE OR DELETE ON public.payment_allocation
DEFERRABLE INITIALLY IMMEDIATE
FOR EACH ROW
EXECUTE FUNCTION public.payment_allocation_sum_check();

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

CREATE TRIGGER payment_to_ledger_insert
AFTER INSERT OR UPDATE ON public.payment
FOR EACH ROW
EXECUTE FUNCTION public.payment_to_ledger();

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

CREATE TRIGGER refund_to_ledger_insert
AFTER INSERT OR UPDATE ON public.refund
FOR EACH ROW
EXECUTE FUNCTION public.refund_to_ledger();

CREATE TYPE sales_category AS ENUM ('reserved','paid','cancelled','refunded','ticket_sale','part_refund');

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

CREATE TRIGGER sales_view_insert
INSTEAD OF INSERT ON public.sales
FOR EACH ROW
EXECUTE FUNCTION public.sales_view_insert();
-- Table to link forward/backward routes with a pricelist
CREATE TABLE IF NOT EXISTS public.route_pricelist_bundle (
    id SERIAL PRIMARY KEY,
    route_forward_id INT NOT NULL REFERENCES public.route(id),
    route_backward_id INT NOT NULL REFERENCES public.route(id),
    pricelist_id INT NOT NULL REFERENCES public.pricelist(id)
);



--
-- TOC entry 4692 (class 2604 OID 16612)
-- Name: available id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.available ALTER COLUMN id SET DEFAULT nextval('public.available_id_seq'::regclass);


--
-- TOC entry 4695 (class 2604 OID 16673)
-- Name: passenger id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.passenger ALTER COLUMN id SET DEFAULT nextval('public.passenger_id_seq'::regclass);


--
-- TOC entry 4688 (class 2604 OID 16576)
-- Name: pricelist id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pricelist ALTER COLUMN id SET DEFAULT nextval('public.pricelist_id_seq'::regclass);


--
-- TOC entry 4694 (class 2604 OID 16651)
-- Name: prices id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prices ALTER COLUMN id SET DEFAULT nextval('public.prices_id_seq'::regclass);


--
-- TOC entry 4687 (class 2604 OID 16569)
-- Name: route id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.route ALTER COLUMN id SET DEFAULT nextval('public.route_id_seq'::regclass);


--
-- TOC entry 4693 (class 2604 OID 16634)
-- Name: routestop id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.routestop ALTER COLUMN id SET DEFAULT nextval('public.routestop_id_seq'::regclass);


--
-- TOC entry 4691 (class 2604 OID 16600)
-- Name: seat id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.seat ALTER COLUMN id SET DEFAULT nextval('public.seat_id_seq'::regclass);


--
-- TOC entry 4686 (class 2604 OID 16562)
-- Name: stop id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stop ALTER COLUMN id SET DEFAULT nextval('public.stop_id_seq'::regclass);


--
-- TOC entry 4696 (class 2604 OID 16682)
-- Name: ticket id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket ALTER COLUMN id SET DEFAULT nextval('public.ticket_id_seq'::regclass);


--
-- TOC entry 4689 (class 2604 OID 16583)
-- Name: tour id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tour ALTER COLUMN id SET DEFAULT nextval('public.tour_id_seq'::regclass);


--
-- TOC entry 4889 (class 0 OID 16609)
-- Dependencies: 228
-- Data for Name: available; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.available (id, tour_id, departure_stop_id, arrival_stop_id, seats) FROM stdin;
37	10	4	6	12
38	10	4	7	12
39	10	5	6	12
40	10	5	7	12
\.




--
-- TOC entry 4883 (class 0 OID 16573)
-- Dependencies: 222
-- Data for Name: pricelist; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.pricelist (id, name) FROM stdin;
2	Regular Price
\.


--
-- TOC entry 4893 (class 0 OID 16648)
-- Dependencies: 232
-- Data for Name: prices; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.prices (id, pricelist_id, departure_stop_id, arrival_stop_id, price) FROM stdin;
1	2	4	6	44.00
2	2	4	7	45.00
3	2	5	6	15.00
4	2	5	7	66.00
5	2	7	5	14.00
6	2	7	4	24.00
7	2	6	5	24.00
8	2	6	4	23.00
\.


--
-- TOC entry 4881 (class 0 OID 16566)
-- Dependencies: 220
-- Data for Name: route; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.route (id, name, is_demo) FROM stdin;
1	Stop1-Stop4	f
2	Stop4-Stop1	f
\.


--
-- TOC entry 4891 (class 0 OID 16631)
-- Dependencies: 230
-- Data for Name: routestop; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.routestop (id, route_id, stop_id, "order", arrival_time, departure_time) FROM stdin;
1	1	4	1	10:00:00	10:10:00
2	1	5	2	12:00:00	12:03:00
3	1	6	3	13:10:00	13:14:00
4	1	7	4	13:45:00	13:55:00
\.


--
-- TOC entry 4887 (class 0 OID 16597)
-- Dependencies: 226
-- Data for Name: seat; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.seat (id, tour_id, seat_num, available) FROM stdin;
415	10	1	0
416	10	2	0
417	10	3	0
418	10	4	0
419	10	5	0
420	10	6	0
421	10	7	0
422	10	8	0
423	10	9	123
424	10	10	123
425	10	11	123
426	10	12	123
427	10	13	123
428	10	14	123
429	10	15	123
430	10	16	123
431	10	17	123
432	10	18	123
433	10	19	123
434	10	20	123
435	10	21	0
436	10	22	0
437	10	23	0
438	10	24	0
439	10	25	0
440	10	26	0
441	10	27	0
442	10	28	0
443	10	29	0
444	10	30	0
445	10	31	0
446	10	32	0
447	10	33	0
448	10	34	0
449	10	35	0
450	10	36	0
451	10	37	0
452	10	38	0
453	10	39	0
454	10	40	0
455	10	41	0
456	10	42	0
457	10	43	0
458	10	44	0
459	10	45	0
460	10	46	0
461	10	47	0
462	10	48	0
463	10	49	0
\.


--
-- TOC entry 4879 (class 0 OID 16559)
-- Dependencies: 218
-- Data for Name: stop; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.stop (id, stop_name) FROM stdin;
4	Stop1 
5	Stop2 
6	Stop3 
7	Stop4
\.


--
-- TOC entry 4897 (class 0 OID 16679)
-- Dependencies: 236
-- Data for Name: ticket; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ticket (id, tour_id, seat_id, passenger_id, departure_stop_id, arrival_stop_id) FROM stdin;
\.


--
-- TOC entry 4885 (class 0 OID 16580)
-- Dependencies: 224
-- Data for Name: tour; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.tour (id, route_id, pricelist_id, date, seats, layout_variant) FROM stdin;
10	1	2	2025-05-14	46	1
\.


--
-- TOC entry 4913 (class 0 OID 0)
-- Dependencies: 227
-- Name: available_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.available_id_seq', 40, true);


--
-- TOC entry 4914 (class 0 OID 0)
-- Dependencies: 233
-- Name: passenger_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.passenger_id_seq', 15, true);


--
-- TOC entry 4915 (class 0 OID 0)
-- Dependencies: 221
-- Name: pricelist_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.pricelist_id_seq', 2, true);


--
-- TOC entry 4916 (class 0 OID 0)
-- Dependencies: 231
-- Name: prices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.prices_id_seq', 8, true);


--
-- TOC entry 4917 (class 0 OID 0)
-- Dependencies: 219
-- Name: route_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.route_id_seq', 2, true);


--
-- TOC entry 4918 (class 0 OID 0)
-- Dependencies: 229
-- Name: routestop_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.routestop_id_seq', 4, true);


--
-- TOC entry 4919 (class 0 OID 0)
-- Dependencies: 225
-- Name: seat_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.seat_id_seq', 463, true);


--
-- TOC entry 4920 (class 0 OID 0)
-- Dependencies: 217
-- Name: stop_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.stop_id_seq', 7, true);


--
-- TOC entry 4921 (class 0 OID 0)
-- Dependencies: 235
-- Name: ticket_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ticket_id_seq', 15, true);


--
-- TOC entry 4922 (class 0 OID 0)
-- Dependencies: 223
-- Name: tour_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.tour_id_seq', 10, true);


--
-- TOC entry 4708 (class 2606 OID 16614)
-- Name: available available_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.available
    ADD CONSTRAINT available_pkey PRIMARY KEY (id);


--
-- TOC entry 4714 (class 2606 OID 16677)
-- Name: passenger passenger_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.passenger
    ADD CONSTRAINT passenger_pkey PRIMARY KEY (id);


--
-- TOC entry 4712 (class 2606 OID 16653)
-- Name: prices prices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prices
    ADD CONSTRAINT prices_pkey PRIMARY KEY (id);


--
-- TOC entry 4710 (class 2606 OID 16636)
-- Name: routestop routestop_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.routestop
    ADD CONSTRAINT routestop_pkey PRIMARY KEY (id);


--
-- TOC entry 4706 (class 2606 OID 16602)
-- Name: seat seat_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.seat
    ADD CONSTRAINT seat_pkey PRIMARY KEY (id);


--
-- TOC entry 4698 (class 2606 OID 16564)
-- Name: stop stop_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stop
    ADD CONSTRAINT stop_pkey PRIMARY KEY (id);


--
-- TOC entry 4716 (class 2606 OID 16684)
-- Name: ticket ticket_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket
    ADD CONSTRAINT ticket_pkey PRIMARY KEY (id);


--
-- TOC entry 4704 (class 2606 OID 16585)
-- Name: tour tour_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tour
    ADD CONSTRAINT tour_pkey PRIMARY KEY (id);


--
-- TOC entry 4720 (class 2606 OID 16625)
-- Name: available available_arrival_stop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.available
    ADD CONSTRAINT available_arrival_stop_id_fkey FOREIGN KEY (arrival_stop_id) REFERENCES public.stop(id);


--
-- TOC entry 4721 (class 2606 OID 16620)
-- Name: available available_departure_stop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.available
    ADD CONSTRAINT available_departure_stop_id_fkey FOREIGN KEY (departure_stop_id) REFERENCES public.stop(id);


--
-- TOC entry 4722 (class 2606 OID 16615)
-- Name: available available_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.available
    ADD CONSTRAINT available_tour_id_fkey FOREIGN KEY (tour_id) REFERENCES public.tour(id);


--
-- TOC entry 4725 (class 2606 OID 16664)
-- Name: prices prices_arrival_stop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prices
    ADD CONSTRAINT prices_arrival_stop_id_fkey FOREIGN KEY (arrival_stop_id) REFERENCES public.stop(id);


--
-- TOC entry 4726 (class 2606 OID 16659)
-- Name: prices prices_departure_stop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prices
    ADD CONSTRAINT prices_departure_stop_id_fkey FOREIGN KEY (departure_stop_id) REFERENCES public.stop(id);


--
-- TOC entry 4727 (class 2606 OID 16654)
-- Name: prices prices_pricelist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prices
    ADD CONSTRAINT prices_pricelist_id_fkey FOREIGN KEY (pricelist_id) REFERENCES public.pricelist(id);


--
-- TOC entry 4723 (class 2606 OID 16637)
-- Name: routestop routestop_route_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.routestop
    ADD CONSTRAINT routestop_route_id_fkey FOREIGN KEY (route_id) REFERENCES public.route(id);


--
-- TOC entry 4724 (class 2606 OID 16642)
-- Name: routestop routestop_stop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.routestop
    ADD CONSTRAINT routestop_stop_id_fkey FOREIGN KEY (stop_id) REFERENCES public.stop(id);


--
-- TOC entry 4719 (class 2606 OID 16603)
-- Name: seat seat_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.seat
    ADD CONSTRAINT seat_tour_id_fkey FOREIGN KEY (tour_id) REFERENCES public.tour(id);


--
-- TOC entry 4728 (class 2606 OID 16705)
-- Name: ticket ticket_arrival_stop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket
    ADD CONSTRAINT ticket_arrival_stop_id_fkey FOREIGN KEY (arrival_stop_id) REFERENCES public.stop(id);


--
-- TOC entry 4729 (class 2606 OID 16700)
-- Name: ticket ticket_departure_stop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket
    ADD CONSTRAINT ticket_departure_stop_id_fkey FOREIGN KEY (departure_stop_id) REFERENCES public.stop(id);


--
-- TOC entry 4730 (class 2606 OID 16695)
-- Name: ticket ticket_passenger_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket
    ADD CONSTRAINT ticket_passenger_id_fkey FOREIGN KEY (passenger_id) REFERENCES public.passenger(id);


--
-- TOC entry 4731 (class 2606 OID 16690)
-- Name: ticket ticket_seat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket
    ADD CONSTRAINT ticket_seat_id_fkey FOREIGN KEY (seat_id) REFERENCES public.seat(id);


--
-- TOC entry 4732 (class 2606 OID 16685)
-- Name: ticket ticket_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket
    ADD CONSTRAINT ticket_tour_id_fkey FOREIGN KEY (tour_id) REFERENCES public.tour(id);

ALTER TABLE ONLY public.ticket
    ADD CONSTRAINT ticket_purchase_id_fkey FOREIGN KEY (purchase_id) REFERENCES public.purchase(id);


--
-- TOC entry 4717 (class 2606 OID 16591)
-- Name: tour tour_pricelist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tour
    ADD CONSTRAINT tour_pricelist_id_fkey FOREIGN KEY (pricelist_id) REFERENCES public.pricelist(id);


--
-- TOC entry 4718 (class 2606 OID 16586)
-- Name: tour tour_route_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tour
    ADD CONSTRAINT tour_route_id_fkey FOREIGN KEY (route_id) REFERENCES public.route(id);



-- ----------------------------------------------------
-- Допълнителна таблица с потребители
-- ----------------------------------------------------
CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL
);

-- Създаваме административен потребител по подразбиране
INSERT INTO public.users (username, email, hashed_password, role)
VALUES (
    'admin',
    'admin@example.com',
    '$2b$12$Y.DzD5azTaGBSLNfQCbwGOpVxBmWncTZyjNOyPNJwzLneHpIh9DO2',
    'admin'
)
ON CONFLICT DO NOTHING;

-- Completed on 2025-06-11 10:02:38

--
-- PostgreSQL database dump complete
--

