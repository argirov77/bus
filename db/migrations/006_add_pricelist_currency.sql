ALTER TABLE pricelist
    ADD COLUMN IF NOT EXISTS currency character varying(16) NOT NULL DEFAULT 'UAH';
