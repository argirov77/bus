DROP TABLE IF EXISTS link_sessions;

CREATE TABLE link_sessions (
    jti VARCHAR(255) PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    purchase_id INTEGER,
    scope VARCHAR(32) NOT NULL,
    exp TIMESTAMPTZ NOT NULL,
    redeemed TIMESTAMPTZ,
    used TIMESTAMPTZ,
    revoked TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_link_sessions_ticket_scope
    ON link_sessions (ticket_id, scope)
    WHERE revoked IS NULL;

CREATE INDEX idx_link_sessions_purchase_scope
    ON link_sessions (purchase_id, scope)
    WHERE revoked IS NULL;
