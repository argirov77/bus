-- Create purchase and sales tables if they do not exist

-- Enums needed for purchase and sales
CREATE TYPE IF NOT EXISTS purchase_status AS ENUM ('reserved','paid','cancelled','refunded');
CREATE TYPE IF NOT EXISTS payment_method_type AS ENUM ('online','offline');
CREATE TYPE IF NOT EXISTS sales_category AS ENUM ('reserved','paid','cancelled','refunded','ticket_sale','part_refund');

-- Purchase table
CREATE TABLE IF NOT EXISTS public.purchase (
    id SERIAL PRIMARY KEY,
    customer_name VARCHAR(255),
    customer_email VARCHAR(255),
    customer_phone VARCHAR(50),
    amount_due DECIMAL,
    deadline TIMESTAMP,
    status purchase_status NOT NULL DEFAULT 'reserved',
    update_at TIMESTAMP,
    payment_method payment_method_type NOT NULL DEFAULT 'online'
);

-- Sales table referencing purchase
CREATE TABLE IF NOT EXISTS public.sales (
    id SERIAL PRIMARY KEY,
    date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    category sales_category NOT NULL,
    amount DECIMAL NOT NULL,
    purchase_id INTEGER REFERENCES public.purchase(id),
    actor TEXT,
    method payment_method_type,
    comment TEXT
);
