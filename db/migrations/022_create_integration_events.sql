CREATE TABLE IF NOT EXISTS integration_events (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    purchase_id BIGINT REFERENCES purchase(id) ON DELETE SET NULL,
    ticket_id BIGINT REFERENCES ticket(id) ON DELETE SET NULL,
    external_id TEXT,
    status TEXT NOT NULL,
    payload_json JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_integration_events_created_at
    ON integration_events (created_at);

CREATE INDEX IF NOT EXISTS idx_integration_events_provider
    ON integration_events (provider);

CREATE INDEX IF NOT EXISTS idx_integration_events_purchase_id
    ON integration_events (purchase_id);
