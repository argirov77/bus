CREATE TABLE otp_challenge (
    id UUID PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    purchase_id INTEGER,
    action VARCHAR(32) NOT NULL,
    code VARCHAR(6) NOT NULL,
    exp TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_otp_challenge_ticket
    ON otp_challenge (ticket_id, action);

CREATE TABLE op_token (
    token VARCHAR(255) PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    purchase_id INTEGER,
    action VARCHAR(32) NOT NULL,
    exp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    used_at TIMESTAMPTZ
);

CREATE INDEX idx_op_token_ticket
    ON op_token (ticket_id, action)
    WHERE used_at IS NULL;
