-- Add discount price support
ALTER TABLE prices ADD COLUMN IF NOT EXISTS discount_price numeric(10,2);
UPDATE prices SET discount_price = price WHERE discount_price IS NULL;
ALTER TABLE ticket ADD COLUMN IF NOT EXISTS discounted boolean NOT NULL DEFAULT FALSE;
