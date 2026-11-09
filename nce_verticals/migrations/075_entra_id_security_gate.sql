-- 075_entra_id_security_gate.sql
-- Microsoft Entra ID (Azure AD) Identification Point & Company Allowlist Gate
-- Ensures zero-trust identity & security group/app-role verification even when
-- NCE is only used by connecting an LLM (e.g. Claude Desktop via MCP on a PC).
-- ============================================================================

CREATE TABLE IF NOT EXISTS entra_id_configs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    entra_tenant_id         TEXT NOT NULL,
    client_id               TEXT NOT NULL,
    client_secret_enc       BYTEA,
    enforce_mode            TEXT NOT NULL DEFAULT 'strict'
                            CHECK (enforce_mode IN ('strict', 'audit_only', 'disabled')),
    allowed_group_ids       JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_app_roles       JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_upns            JSONB NOT NULL DEFAULT '[]'::jsonb,
    blocked_upns            JSONB NOT NULL DEFAULT '[]'::jsonb,
    require_graph_check     BOOLEAN NOT NULL DEFAULT TRUE,
    allow_os_silent_auth    BOOLEAN NOT NULL DEFAULT TRUE,
    allow_device_code_flow  BOOLEAN NOT NULL DEFAULT TRUE,
    session_ttl_seconds     INTEGER NOT NULL DEFAULT 28800
                            CHECK (session_ttl_seconds BETWEEN 300 AND 86400),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id)
);

CREATE INDEX IF NOT EXISTS idx_entra_id_configs_namespace
    ON entra_id_configs (namespace_id);

ALTER TABLE entra_id_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE entra_id_configs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON entra_id_configs;
CREATE POLICY tenant_isolation_policy ON entra_id_configs
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE entra_id_configs FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE entra_id_configs TO nce_app;
    END IF;
END $$;

-- Verified PC / LLM sessions bound to a Microsoft Entra ID user principal
CREATE TABLE IF NOT EXISTS entra_id_sessions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    entra_oid               TEXT NOT NULL,
    entra_tid               TEXT NOT NULL,
    upn                     TEXT NOT NULL,
    display_name            TEXT,
    pc_hostname             TEXT,
    os_username             TEXT,
    auth_method             TEXT NOT NULL
                            CHECK (auth_method IN ('jwt_bearer', 'os_broker_azcli', 'device_code', 'obo_delegated', 'admin_verified')),
    matched_groups          JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_roles           JSONB NOT NULL DEFAULT '[]'::jsonb,
    status                  TEXT NOT NULL DEFAULT 'ACTIVE'
                            CHECK (status IN ('ACTIVE', 'REVOKED', 'EXPIRED')),
    expires_at              TIMESTAMPTZ NOT NULL,
    last_verified_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entra_id_sessions_namespace_oid
    ON entra_id_sessions (namespace_id, entra_oid);
CREATE INDEX IF NOT EXISTS idx_entra_id_sessions_active
    ON entra_id_sessions (namespace_id, status, expires_at)
    WHERE status = 'ACTIVE';

ALTER TABLE entra_id_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE entra_id_sessions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON entra_id_sessions;
CREATE POLICY tenant_isolation_policy ON entra_id_sessions
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE entra_id_sessions FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE entra_id_sessions TO nce_app;
    END IF;
END $$;

-- Immutable audit log of Entra ID identification & allowlist evaluations
CREATE TABLE IF NOT EXISTS entra_id_audit_log (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    entra_oid               TEXT,
    upn                     TEXT,
    pc_hostname             TEXT,
    tool_or_route           TEXT NOT NULL,
    decision                TEXT NOT NULL
                            CHECK (decision IN ('ALLOW', 'DENY', 'AUDIT_WARN')),
    reason                  TEXT NOT NULL,
    matched_groups          JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_roles           JSONB NOT NULL DEFAULT '[]'::jsonb,
    occurred_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entra_id_audit_log_namespace_time
    ON entra_id_audit_log (namespace_id, occurred_at DESC);

ALTER TABLE entra_id_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE entra_id_audit_log FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON entra_id_audit_log;
CREATE POLICY tenant_isolation_policy ON entra_id_audit_log
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE entra_id_audit_log FROM nce_app;
        GRANT SELECT, INSERT ON TABLE entra_id_audit_log TO nce_app;
    END IF;
END $$;
