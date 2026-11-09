-- 001_d365_integrations_and_mappings.sql
-- Dynamics 365 / Dataverse and NetBox mapping foundation schema.
-- ============================================================================

CREATE TABLE IF NOT EXISTS d365_integrations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id        UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    org_url             TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'ACTIVE'
                        CHECK (status IN ('ACTIVE', 'DEGRADED', 'DISABLED')),
    token_enc           BYTEA,           -- AES-256-GCM encrypted access token JSON
    token_expires_at    TIMESTAMPTZ,
    webhook_secret_enc  BYTEA,           -- AES-256-GCM encrypted webhook secret
    last_sync_at        TIMESTAMPTZ,
    last_sync_stats     JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, org_url)
);

CREATE INDEX IF NOT EXISTS idx_d365_integrations_namespace
    ON d365_integrations (namespace_id);
CREATE INDEX IF NOT EXISTS idx_d365_integrations_status
    ON d365_integrations (status)
    WHERE status = 'ACTIVE';

ALTER TABLE d365_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE d365_integrations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON d365_integrations;
CREATE POLICY tenant_isolation_policy ON d365_integrations
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE d365_integrations FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE d365_integrations TO nce_app;
    END IF;
END $$;

-- D365 <-> NetBox cross-reference mapping table.
-- Stores confirmed and inferred mappings between Dataverse entities
-- (Accounts, Functional Locations) and NetBox entities (Tenants, Sites, Locations).
-- Rows are upserted by the bridge cron tick and surfaced as kg_edges.
CREATE TABLE IF NOT EXISTS d365_netbox_mappings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id        UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    d365_entity_type    TEXT NOT NULL
                        CHECK (d365_entity_type IN ('account', 'functional_location')),
    d365_entity_id      TEXT NOT NULL,          -- Dataverse GUID string
    d365_entity_name    TEXT NOT NULL,
    nb_entity_type      TEXT NOT NULL
                        CHECK (nb_entity_type IN ('tenant', 'site', 'location')),
    nb_entity_id        INTEGER NOT NULL,       -- NetBox integer PK
    nb_entity_name      TEXT NOT NULL,
    nb_entity_slug      TEXT,
    match_method        TEXT NOT NULL
                        CHECK (match_method IN ('custom_field', 'exact', 'slug', 'fuzzy', 'manual')),
    match_confidence    FLOAT NOT NULL DEFAULT 1.0
                        CHECK (match_confidence BETWEEN 0.0 AND 1.0),
    confirmed           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, d365_entity_type, d365_entity_id, nb_entity_type, nb_entity_id)
);

CREATE INDEX IF NOT EXISTS idx_d365_netbox_mappings_namespace
    ON d365_netbox_mappings (namespace_id);
CREATE INDEX IF NOT EXISTS idx_d365_netbox_mappings_d365_type
    ON d365_netbox_mappings (namespace_id, d365_entity_type);
CREATE INDEX IF NOT EXISTS idx_d365_netbox_mappings_confirmed
    ON d365_netbox_mappings (namespace_id, confirmed)
    WHERE confirmed = TRUE;

ALTER TABLE d365_netbox_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE d365_netbox_mappings FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON d365_netbox_mappings;
CREATE POLICY tenant_isolation_policy ON d365_netbox_mappings
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE d365_netbox_mappings FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE d365_netbox_mappings TO nce_app;
    END IF;
END $$;
