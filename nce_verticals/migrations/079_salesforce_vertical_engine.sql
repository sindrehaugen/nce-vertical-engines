-- 079_salesforce_vertical_engine.sql
-- Standalone & Integrated Salesforce Vertical Engine Schema
-- Supports all 3 auth modes (Connected App OAuth2, JWT Bearer, Entra ID Delegated),
-- standalone pass-through mode, bidirectional local read-model cache, and webhooks.
-- ============================================================================

CREATE TABLE IF NOT EXISTS salesforce_integrations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    instance_url            TEXT NOT NULL,
    login_url               TEXT NOT NULL DEFAULT 'https://login.salesforce.com',
    api_version             TEXT NOT NULL DEFAULT 'v60.0',
    auth_mode               TEXT NOT NULL DEFAULT 'client_credentials'
                            CHECK (auth_mode IN ('client_credentials', 'refresh_token', 'jwt_bearer', 'entra_delegated')),
    client_id               TEXT,
    client_secret_enc       BYTEA,
    refresh_token_enc       BYTEA,
    jwt_subject             TEXT,
    jwt_private_key_enc     BYTEA,
    webhook_secret_enc      BYTEA,
    standalone_passthrough  BOOLEAN NOT NULL DEFAULT FALSE,
    sync_enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    require_entra_gate      BOOLEAN NOT NULL DEFAULT TRUE,
    sync_objects            JSONB NOT NULL DEFAULT '["Account","Contact","Lead","Opportunity","Case","Task"]'::jsonb,
    status                  TEXT NOT NULL DEFAULT 'ACTIVE'
                            CHECK (status IN ('ACTIVE', 'DEGRADED', 'DISABLED')),
    last_sync_at            TIMESTAMPTZ,
    last_sync_stats         JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, instance_url)
);

CREATE INDEX IF NOT EXISTS idx_salesforce_integrations_namespace
    ON salesforce_integrations (namespace_id);

ALTER TABLE salesforce_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE salesforce_integrations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON salesforce_integrations;
CREATE POLICY tenant_isolation_policy ON salesforce_integrations
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE salesforce_integrations FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE salesforce_integrations TO nce_app;
    END IF;
END $$;

-- Local read-model cache for bidirectional sync & Knowledge Graph projection
CREATE TABLE IF NOT EXISTS salesforce_read_model (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    sf_id                   TEXT NOT NULL,
    sobject_type            TEXT NOT NULL,
    name                    TEXT,
    owner_id                TEXT,
    parent_sf_id            TEXT,
    status_or_stage         TEXT,
    payload                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    sys_modstamp            TIMESTAMPTZ,
    is_deleted              BOOLEAN NOT NULL DEFAULT FALSE,
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, sobject_type, sf_id)
);

CREATE INDEX IF NOT EXISTS idx_salesforce_read_model_lookup
    ON salesforce_read_model (namespace_id, sobject_type, sf_id);
CREATE INDEX IF NOT EXISTS idx_salesforce_read_model_modstamp
    ON salesforce_read_model (namespace_id, sobject_type, sys_modstamp DESC);

ALTER TABLE salesforce_read_model ENABLE ROW LEVEL SECURITY;
ALTER TABLE salesforce_read_model FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON salesforce_read_model;
CREATE POLICY tenant_isolation_policy ON salesforce_read_model
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE salesforce_read_model FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE salesforce_read_model TO nce_app;
    END IF;
END $$;

-- Idempotent Salesforce Webhook / Outbound Message / Platform Event log
CREATE TABLE IF NOT EXISTS salesforce_webhook_events (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    event_id                TEXT NOT NULL,
    sobject_type            TEXT NOT NULL,
    sf_id                   TEXT NOT NULL,
    change_type             TEXT NOT NULL,
    payload                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    processed_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_salesforce_webhook_events_ns
    ON salesforce_webhook_events (namespace_id, processed_at DESC);

ALTER TABLE salesforce_webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE salesforce_webhook_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON salesforce_webhook_events;
CREATE POLICY tenant_isolation_policy ON salesforce_webhook_events
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE salesforce_webhook_events FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE salesforce_webhook_events TO nce_app;
    END IF;
END $$;
