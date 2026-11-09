-- 081_odoo_vertical_engine.sql
-- Standalone & Integrated Super-Intelligent Odoo Vertical Engine + LLM Cross-Talker
-- Supports JSON-RPC 2.0, XML-RPC, and REST/OAuth2 Bearer with Entra ID Security Gate,
-- local read-model caching, and bidirectional Chatter/Discuss Cross-Engine LLM bridge.
-- ============================================================================

CREATE TABLE IF NOT EXISTS odoo_integrations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    url                     TEXT NOT NULL,
    db_name                 TEXT NOT NULL,
    protocol                TEXT NOT NULL DEFAULT 'jsonrpc'
                            CHECK (protocol IN ('jsonrpc', 'xmlrpc', 'rest_oauth2')),
    username                TEXT,
    api_key_enc             BYTEA,
    webhook_secret_enc      BYTEA,
    require_entra_gate      BOOLEAN NOT NULL DEFAULT TRUE,
    crosstalk_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    standalone_passthrough  BOOLEAN NOT NULL DEFAULT TRUE,
    synced_models           JSONB NOT NULL DEFAULT '["res.partner","crm.lead","sale.order","purchase.order","stock.picking","mrp.production","account.move","project.project","helpdesk.ticket"]'::jsonb,
    status                  TEXT NOT NULL DEFAULT 'ACTIVE'
                            CHECK (status IN ('ACTIVE', 'DEGRADED', 'DISABLED')),
    last_sync_at            TIMESTAMPTZ,
    last_sync_stats         JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, url, db_name)
);

CREATE INDEX IF NOT EXISTS idx_odoo_integrations_namespace
    ON odoo_integrations (namespace_id);

ALTER TABLE odoo_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE odoo_integrations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON odoo_integrations;
CREATE POLICY tenant_isolation_policy ON odoo_integrations
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE odoo_integrations FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE odoo_integrations TO nce_app;
    END IF;
END $$;

-- Local read-model mirror for Odoo ERP/CRM/MRP/Project/Accounting records
CREATE TABLE IF NOT EXISTS odoo_read_model (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    model_name              TEXT NOT NULL,
    odoo_id                 BIGINT NOT NULL,
    display_name            TEXT,
    state                   TEXT,
    partner_id              BIGINT,
    amount_total            NUMERIC(18, 2),
    payload                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    write_date              TIMESTAMPTZ,
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, model_name, odoo_id)
);

CREATE INDEX IF NOT EXISTS idx_odoo_read_model_lookup
    ON odoo_read_model (namespace_id, model_name, odoo_id);

ALTER TABLE odoo_read_model ENABLE ROW LEVEL SECURITY;
ALTER TABLE odoo_read_model FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON odoo_read_model;
CREATE POLICY tenant_isolation_policy ON odoo_read_model
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE odoo_read_model FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE odoo_read_model TO nce_app;
    END IF;
END $$;

-- Bidirectional LLM Cross-Talker log (Odoo Chatter/Discuss <-> LLM <-> Salesforce/Relux/D365)
CREATE TABLE IF NOT EXISTS odoo_crosstalk_messages (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    channel_or_model        TEXT NOT NULL,
    record_id               BIGINT NOT NULL DEFAULT 0,
    direction               TEXT NOT NULL
                            CHECK (direction IN ('INBOUND_FROM_ODOO', 'OUTBOUND_TO_ODOO', 'CROSS_ENGINE_BRIDGE')),
    author                  TEXT,
    prompt_or_body          TEXT NOT NULL,
    target_engines          JSONB NOT NULL DEFAULT '[]'::jsonb,
    response_summary        TEXT,
    actions_executed        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_odoo_crosstalk_messages_ns
    ON odoo_crosstalk_messages (namespace_id, created_at DESC);

ALTER TABLE odoo_crosstalk_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE odoo_crosstalk_messages FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON odoo_crosstalk_messages;
CREATE POLICY tenant_isolation_policy ON odoo_crosstalk_messages
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE odoo_crosstalk_messages FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE odoo_crosstalk_messages TO nce_app;
    END IF;
END $$;
