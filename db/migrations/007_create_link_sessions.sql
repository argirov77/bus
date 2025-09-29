CREATE TABLE IF NOT EXISTS link_sessions (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    scope VARCHAR(32) NOT NULL,
    opaque VARCHAR(128) NOT NULL UNIQUE,
    token TEXT NOT NULL,
    jti UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_link_sessions_ticket_scope
    ON link_sessions (ticket_id, scope)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_link_sessions_jti
    ON link_sessions (jti);
