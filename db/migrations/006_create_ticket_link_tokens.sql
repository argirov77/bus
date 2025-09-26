CREATE TABLE IF NOT EXISTS ticket_link_tokens (
    jti UUID PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    purchase_id INTEGER,
    scopes JSONB NOT NULL,
    lang VARCHAR(16) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ticket_link_tokens_ticket_id
    ON ticket_link_tokens (ticket_id);
