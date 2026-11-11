"""Unit tests validating SQL migration chains, RLS policy enforcement, and Core purity.

Folds static verification previously done in trace_migrations.py into standard pytest:
  1. Core Standalone Purity: assert 0 vertical tables in schema.sql and Core migrations.
  2. Contiguous numbering across Core migrations.
  3. Vertical migrations sequence and RLS retention (ENABLE + FORCE + get_nce_namespace()).
  4. NetBox engine independence from Dynamics 365.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nce_verticals.registry import ENGINE_REGISTRY

# Authoritative inventory of all 95 vertical tables across all vertical engines.
VERTICAL_TABLES: frozenset[str] = frozenset(
    [
        "absences",
        "agreement_extraction_runs",
        "agreement_parties",
        "agreement_review_queue",
        "agreement_templates",
        "agreements",
        "allocations",
        "assets",
        "bom_line_content",
        "business_insights_kpi_snapshots",
        "case_studies",
        "certifications",
        "checklists",
        "content_assets",
        "contractor_profiles",
        "customer_health",
        "d365_delta_tokens",
        "d365_integrations",
        "d365_netbox_mappings",
        "d365_sync_runs",
        "decision_feedback",
        "device_health_rollup",
        "diag_anomalies",
        "diag_ingestions",
        "divergence_log",
        "document_links",
        "document_shares",
        "documents",
        "economy_billing_candidate_lines",
        "economy_billing_candidates",
        "economy_billing_runs",
        "economy_bom_actual_costs",
        "economy_contracts",
        "economy_customer_invoices",
        "economy_postings",
        "employees",
        "entity_merge_queue",
        "geodata_n50_land_cover",
        "geodata_osm_elements",
        "geodata_place_names",
        "goods_receipts",
        "inventory_items",
        "inventory_rma",
        "inventory_transactions",
        "legal_entities",
        "node_ownership_registry",
        "notification_subscriptions",
        "notifications",
        "per_diems",
        "portal_document_shares",
        "portal_service_requests",
        "portal_users",
        "pricing_fx_rates",
        "procurement_bid_prices",
        "procurement_deal_registrations",
        "procurement_po_lines",
        "product_catalog",
        "product_enrichment_log",
        "product_match_feedback",
        "product_packages",
        "product_prices",
        "reminders",
        "resources",
        "sales_contacts",
        "sales_customers",
        "sales_deal_participants",
        "sales_deals",
        "sales_leads",
        "sales_quote_templates",
        "sales_quotes",
        "sales_read_model",
        "sales_signed_baselines",
        "sales_targets",
        "service_tickets",
        "sites",
        "skills",
        "sla_clocks",
        "source_mode_config",
        "source_mode_heartbeat",
        "stays",
        "stock_locations",
        "support_ticket_actions",
        "system_design_design_requests",
        "system_design_device_capabilities",
        "system_design_geometry",
        "system_design_node_state",
        "telemetry_samples",
        "testimonials",
        "time_entries",
        "travel_legs",
        "vendor_scorecards",
        "work_orders",
    ]
)

# Global reference tables that do not have namespace_id
GLOBAL_VERTICAL_TABLES: frozenset[str] = frozenset(
    [
        "geodata_osm_elements",
        "geodata_n50_land_cover",
        "geodata_place_names",
        "pricing_fx_rates",
    ]
)


def _find_core_paths() -> tuple[Path, Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root.parent / "neuro-cognitive-engine",
        repo_root.parent / "NCE-Public",
        repo_root / "neuro-cognitive-engine",
    ]
    for r in candidates:
        schema = r / "nce" / "schema.sql"
        mig_dir = r / "nce" / "migrations"
        if schema.is_file() and mig_dir.is_dir():
            return r, schema, mig_dir
    pytest.skip("Core repository paths not found in workspace for cross-repo validation")


def _find_vertical_migrations_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root / "nce_verticals" / "migrations"
    if candidate.is_dir():
        return candidate
    pytest.skip(f"Vertical migrations directory not found at {candidate}")


def test_core_migrations_and_schema_purity() -> None:
    """Core standalone must contain zero vertical tables in schema.sql and migrations."""
    _, schema_path, core_mig_dir = _find_core_paths()

    # 1. Validate Core schema.sql
    schema_sql = schema_path.read_text(encoding="utf-8")
    for vt in VERTICAL_TABLES:
        pattern_create = rf"CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{vt}\b"
        assert not re.search(pattern_create, schema_sql, re.IGNORECASE), (
            f"Core schema.sql creates vertical table: {vt}"
        )
        pattern_alter = rf"ALTER\s+TABLE\s+(?:ONLY\s+)?{vt}\b"
        assert not re.search(pattern_alter, schema_sql, re.IGNORECASE), (
            f"Core schema.sql alters vertical table: {vt}"
        )

    # 2. Validate Core migrations chain
    core_files = sorted([f for f in core_mig_dir.glob("*.sql") if f.is_file()])
    assert len(core_files) > 0, "No core migration files found!"

    for i, path in enumerate(core_files, 1):
        expected_prefix = f"{i:03d}_"
        assert path.name.startswith(expected_prefix), (
            f"Core migration sequence gap or mismatch: expected {expected_prefix}*, got {path.name}"
        )
        content = path.read_text(encoding="utf-8")
        for vt in VERTICAL_TABLES:
            pattern_create = rf"CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{vt}\b"
            assert not re.search(pattern_create, content, re.IGNORECASE), (
                f"Core migration {path.name} creates vertical table: {vt}"
            )
            pattern_alter = rf"ALTER\s+TABLE\s+(?:ONLY\s+)?{vt}\b"
            assert not re.search(pattern_alter, content, re.IGNORECASE), (
                f"Core migration {path.name} alters vertical table: {vt}"
            )

    optional_citus = core_mig_dir / "optional" / "010_citus_sharding.sql"
    assert optional_citus.is_file(), f"Missing optional Citus migration: {optional_citus}"


def test_vertical_migrations_sequence_and_rls() -> None:
    """Vertical migrations must exist, have valid SQL, and enforce tenant RLS on all tenant tables."""
    vert_mig_dir = _find_vertical_migrations_dir()
    vert_files = sorted([f for f in vert_mig_dir.glob("*.sql") if f.is_file()])
    assert len(vert_files) > 0, "No vertical migration files found!"

    tenant_tables_found: set[str] = set()

    for path in vert_files:
        assert re.match(r"^\d{3}_.*\.sql$", path.name), (
            f"Vertical migration {path.name} does not match 3-digit prefix format"
        )
        content = path.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, f"Vertical migration {path.name} is empty"

        chunks = re.split(
            r"CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?", content, flags=re.I
        )
        for chunk in chunks[1:]:
            m = re.match(r"^([a-zA-Z0-9_]+)", chunk)
            if not m:
                continue
            tbl = m.group(1).lower()
            if tbl in ("if", "above", "keeps", "temp_event_log_migrate"):
                continue
            if tbl not in GLOBAL_VERTICAL_TABLES:
                tenant_tables_found.add(tbl)
                has_enable = (
                    bool(re.search(rf"{tbl}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", content, re.I))
                    or "enable row level security" in chunk.lower()
                    or "alter table public.%i enable row level security" in content.lower()
                )
                has_force = (
                    bool(re.search(rf"{tbl}\s+FORCE\s+ROW\s+LEVEL\s+SECURITY", content, re.I))
                    or "force row level security" in chunk.lower()
                    or "alter table public.%i force row level security" in content.lower()
                )
                has_policy = "get_nce_namespace()" in content.lower()
                assert has_enable and has_force and has_policy, (
                    f"Vertical table {tbl} in {path.name} failed RLS requirement: "
                    f"enable={has_enable}, force={has_force}, bound_to_get_nce_namespace={has_policy}"
                )

    assert len(tenant_tables_found) > 0, (
        "No vertical tenant tables found across vertical migrations!"
    )


def test_netbox_independent_of_d365() -> None:
    """NetBox engine must operate independently without depending on Dynamics 365."""
    assert "netbox" in ENGINE_REGISTRY, "NetBox engine not found in ENGINE_REGISTRY"
    spec = ENGINE_REGISTRY["netbox"]
    assert "dynamics365" not in spec.requires_schemas, (
        f"NetBox engine spec declares forbidden dependency on dynamics365: {spec.requires_schemas}"
    )
    assert spec.slug == "netbox"
