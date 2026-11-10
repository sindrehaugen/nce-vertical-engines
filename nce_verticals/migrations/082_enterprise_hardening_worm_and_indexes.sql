-- =============================================================================
-- Migration 082: Enterprise Hardening — WORM Trigger on Signed Baselines &
--                Composite Multi-Tenant Lookup Indexes
-- =============================================================================
-- 1. Enforces trigger-level WORM immutability on sales_signed_baselines so that
--    signed quote baselines cannot be mutated or deleted even by privileged
--    maintenance roles.
-- 2. Adds composite indexes on high-cardinality tenant/status/entity predicates
--    across vertical engine tables.
-- =============================================================================

CREATE OR REPLACE FUNCTION nce_prevent_signed_baseline_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'WORM violation: sales_signed_baselines rows are immutable once signed (operation=%, quote_id=%)',
        TG_OP, OLD.quote_id
        USING ERRCODE = '55000';
END;
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'sales_signed_baselines'
    ) THEN
        DROP TRIGGER IF EXISTS trg_sales_signed_baselines_worm ON sales_signed_baselines;
        CREATE TRIGGER trg_sales_signed_baselines_worm
            BEFORE UPDATE OR DELETE ON sales_signed_baselines
            FOR EACH ROW
            EXECUTE FUNCTION nce_prevent_signed_baseline_mutation();

        CREATE INDEX IF NOT EXISTS idx_sales_signed_baselines_ns_quote
            ON sales_signed_baselines (namespace_id, quote_id);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'field_tech_work_orders'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_field_tech_work_orders_ns_status
            ON field_tech_work_orders (namespace_id, status);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'sales_read_model'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_sales_read_model_ns_entity_deleted
            ON sales_read_model (namespace_id, entity, is_deleted);
    END IF;

    -- High-frequency composite tenant indexes (support, agreements, assets, projects)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'support_service_tickets' AND column_name = 'namespace_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'support_service_tickets' AND column_name = 'status'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_support_service_tickets_ns_status
            ON support_service_tickets (namespace_id, status);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'support_tickets' AND column_name = 'namespace_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'support_tickets' AND column_name = 'status'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_support_tickets_ns_status
            ON support_tickets (namespace_id, status);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'agreements_contracts' AND column_name = 'namespace_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'agreements_contracts' AND column_name = 'status'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_agreements_contracts_ns_status
            ON agreements_contracts (namespace_id, status);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'assets_registry' AND column_name = 'namespace_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'assets_registry' AND column_name = 'status'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_assets_registry_ns_status
            ON assets_registry (namespace_id, status);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'assets' AND column_name = 'namespace_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'assets' AND column_name = 'status'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_assets_ns_status
            ON assets (namespace_id, status);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'project_projects' AND column_name = 'namespace_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'project_projects' AND column_name = 'status'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_project_projects_ns_status
            ON project_projects (namespace_id, status);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'namespace_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'status'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_projects_ns_status
            ON projects (namespace_id, status);
    END IF;
END;
$$;
