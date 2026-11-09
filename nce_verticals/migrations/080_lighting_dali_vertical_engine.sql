-- 080_lighting_dali_vertical_engine.sql
-- Relux / DIALux Light Design & IEC 62386 DALI-2 / Glamox System Design Engine
-- Stores parsed photometric files (.ldt / .ies), Relux/DIALux room projects,
-- Glamox luminaire schedules, and DALI-2 bus topology & compliance reports.
-- ============================================================================

CREATE TABLE IF NOT EXISTS lighting_dali_projects (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id            UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    project_code            TEXT NOT NULL,
    project_name            TEXT NOT NULL,
    source_tool             TEXT NOT NULL DEFAULT 'relux'
                            CHECK (source_tool IN ('relux', 'dialux', 'glamox_export', 'dali_cad', 'manual')),
    building_type           TEXT NOT NULL DEFAULT 'office',
    en12464_zone_code       TEXT NOT NULL DEFAULT 'OFFICE_WRITING',
    rooms_payload           JSONB NOT NULL DEFAULT '[]'::jsonb,
    luminaires_payload      JSONB NOT NULL DEFAULT '[]'::jsonb,
    dali_universes_payload  JSONB NOT NULL DEFAULT '[]'::jsonb,
    analysis_report         JSONB NOT NULL DEFAULT '{}'::jsonb,
    compliance_passed       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, project_code)
);

CREATE INDEX IF NOT EXISTS idx_lighting_dali_projects_ns
    ON lighting_dali_projects (namespace_id, updated_at DESC);

ALTER TABLE lighting_dali_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE lighting_dali_projects FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON lighting_dali_projects;
CREATE POLICY tenant_isolation_policy ON lighting_dali_projects
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        REVOKE ALL ON TABLE lighting_dali_projects FROM nce_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE lighting_dali_projects TO nce_app;
    END IF;
END $$;
