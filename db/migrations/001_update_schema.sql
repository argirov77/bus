-- Add new fields to stop table
ALTER TABLE stop
    ADD COLUMN IF NOT EXISTS stop_en VARCHAR(255),
    ADD COLUMN IF NOT EXISTS stop_bg VARCHAR(255),
    ADD COLUMN IF NOT EXISTS stop_ua VARCHAR(255),
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS location TEXT;

-- Convert ticket.extra_baggage to integer
ALTER TABLE ticket
    ALTER COLUMN extra_baggage TYPE integer USING CASE WHEN extra_baggage THEN 1 ELSE 0 END,
    ALTER COLUMN extra_baggage SET DEFAULT 0;

-- Remove phone and email from passenger
ALTER TABLE passenger DROP COLUMN IF EXISTS phone;
ALTER TABLE passenger DROP COLUMN IF EXISTS email;

-- Booking terms as smallint with default 0
ALTER TABLE tour
    ALTER COLUMN booking_terms TYPE smallint USING booking_terms::smallint,
    ALTER COLUMN booking_terms SET DEFAULT 0,
    ALTER COLUMN booking_terms SET NOT NULL;

-- Enums for purchase and payment method
CREATE TYPE IF NOT EXISTS purchase_status AS ENUM ('reserved','paid','cancelled','refunded');
CREATE TYPE IF NOT EXISTS payment_method_type AS ENUM ('online','offline');

-- Update purchase table
ALTER TABLE purchase
    DROP COLUMN IF EXISTS created_at,
    RENAME COLUMN updated_at TO update_at,
    ALTER COLUMN status TYPE purchase_status USING status::purchase_status,
    ADD COLUMN IF NOT EXISTS customer_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS customer_email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS customer_phone VARCHAR(50),
    ADD COLUMN IF NOT EXISTS amount_due DECIMAL,
    ADD COLUMN IF NOT EXISTS deadline TIMESTAMP,
    ADD COLUMN IF NOT EXISTS payment_method payment_method_type DEFAULT 'online';

-- Enum for sales categories
CREATE TYPE IF NOT EXISTS sales_category AS ENUM ('reserved','paid','cancelled','refunded','ticket_sale','part_refund');

-- Update sales table
ALTER TABLE sales
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS changed_at,
    ADD COLUMN IF NOT EXISTS date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS category sales_category,
    ADD COLUMN IF NOT EXISTS amount DECIMAL NOT NULL DEFAULT 0,
    ALTER COLUMN purchase_id DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS actor TEXT,
    ADD COLUMN IF NOT EXISTS method payment_method_type,
    ADD COLUMN IF NOT EXISTS comment TEXT;
