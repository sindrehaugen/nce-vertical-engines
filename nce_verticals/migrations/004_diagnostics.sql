-- 004_diagnostics.sql
-- Diagnostic Log Digestion Engine — Phase 1: schema foundation
-- Batch 67 — diag-schema
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1.  diag_ingestions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS diag_ingestions (
    id                 UUID        NOT NULL DEFAULT gen_random_uuid(),
    namespace_id       UUID        NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    ingest_id          TEXT        NOT NULL,
    source             TEXT        CHECK (source IN ('upload', 'api', 'ticketing')),
    vendor_profile     TEXT,
    device_slug        TEXT,
    landing_uri        TEXT,
    status             TEXT        NOT NULL DEFAULT 'PENDING'
                                   CHECK (status IN ('PENDING', 'PROCESSING', 'DIGESTED', 'FAILED')),
    bytes              BIGINT,
    processed_lines    BIGINT,
    anomaly_count      INT,
    digest_payload_ref TEXT,
    created_at         TIMESTAMPTZ DEFAULT now(),
    updated_at         TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (id),
    UNIQUE (namespace_id, ingest_id)
);

CREATE INDEX IF NOT EXISTS idx_diag_ingestions_namespace_id
    ON diag_ingestions (namespace_id);

COMMENT ON TABLE diag_ingestions IS
'Diagnostic Log Digestion Engine — Phase 1.
Per-ingestion record (upload / API push / ticketing pull).
RLS: tenant_isolation_policy via get_nce_namespace() GUC.
status lifecycle: PENDING → PROCESSING → DIGESTED | FAILED.';

-- ---------------------------------------------------------------------------
-- 2.  diag_anomalies
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS diag_anomalies (
    id             UUID        NOT NULL DEFAULT gen_random_uuid(),
    namespace_id   UUID        NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    ingestion_id   UUID        NOT NULL REFERENCES diag_ingestions(id) ON DELETE CASCADE,
    device_slug    TEXT,
    anomaly_type   TEXT,
    severity       INT,
    first_line     BIGINT,
    occurrences    INT,
    -- sample is truncated to ≤200 chars by the writer before INSERT
    sample         TEXT,
    window_start   TIMESTAMPTZ,
    window_end     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_diag_anomalies_namespace_id
    ON diag_anomalies (namespace_id);

CREATE INDEX IF NOT EXISTS idx_diag_anomalies_ingestion_id
    ON diag_anomalies (ingestion_id);

COMMENT ON TABLE diag_anomalies IS
'Diagnostic Log Digestion Engine — Phase 1.
Anomalies extracted from a single diag_ingestions row.
sample column MUST be truncated to ≤200 chars by the writer (no PII allowed).
RLS: tenant_isolation_policy via get_nce_namespace() GUC.';

-- ---------------------------------------------------------------------------
-- 3.  device_health_rollup
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS device_health_rollup (
    namespace_id      UUID        NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    device_slug       TEXT        NOT NULL,
    health_state      TEXT        CHECK (health_state IN ('HEALTHY', 'DEGRADED', 'CRITICAL')),
    top_anomaly_type  TEXT,
    anomaly_score     FLOAT8,
    last_ingestion_id UUID,
    last_seen_at      TIMESTAMPTZ,
    PRIMARY KEY (namespace_id, device_slug)
);

-- namespace_id is part of the PK so the PK index already covers it, but an
-- explicit single-column index helps the RLS qual push-down on full scans.
CREATE INDEX IF NOT EXISTS idx_device_health_rollup_namespace_id
    ON device_health_rollup (namespace_id);

COMMENT ON TABLE device_health_rollup IS
'Diagnostic Log Digestion Engine — Phase 1.
Latest health aggregate per (namespace_id, device_slug).
Upserted by the digestion worker after each completed ingestion.
RLS: tenant_isolation_policy via get_nce_namespace() GUC.';

-- ---------------------------------------------------------------------------
-- 5.  Apply RLS to the three new diag tables
--     (mirrors the tenant_tables loop pattern in schema.sql)
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    t text;
    diag_tables text[] := ARRAY[
        'diag_ingestions',
        'diag_anomalies',
        'device_health_rollup'
    ];
BEGIN
    FOREACH t IN ARRAY diag_tables
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS namespace_isolation_policy ON public.%I', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_policy ON public.%I', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation_policy ON public.%I '
            'FOR ALL TO nce_app '
            'USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace()) '
            'WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())',
            t
        );
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM nce_app', t);
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO nce_app',
            t
        );
    END LOOP;
END $$;
