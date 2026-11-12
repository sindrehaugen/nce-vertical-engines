"""Unit tests for Module 15 Staff & Resources Engine schema and RLS configuration."""

from __future__ import annotations

from pathlib import Path

from nce_verticals.plugin import ResourcesPlugin, VerticalEnginesPlugin
from tests.expected_tenant_rls_table_count import EXPECTED_TENANT_RLS_TABLE_COUNT

REPO_ROOT = Path(__file__).resolve().parents[2]

M15_TABLES = [
    "resources",
    "allocations",
    "travel_legs",
    "stays",
    "per_diems",
]


def test_resources_tables_registered_in_expected_tenant_rls_tables():
    """All M15 tables must be registered in VerticalEnginesPlugin RLS tables."""
    plugin_tables = VerticalEnginesPlugin().get_tenant_rls_tables()
    engine_tables = ResourcesPlugin().get_tenant_rls_tables()
    for table in M15_TABLES:
        assert table in plugin_tables, (
            f"Table {table!r} missing from VerticalEnginesPlugin().get_tenant_rls_tables()"
        )
        assert plugin_tables[table] == "namespace_id", (
            f"Table {table!r} has namespace column {plugin_tables[table]!r}, expected 'namespace_id'"
        )
        assert engine_tables.get(table) == "namespace_id"


def test_expected_tenant_rls_tables_total_count():
    """Total vertical tenant RLS table count -- see tests/expected_tenant_rls_table_count.py."""
    plugin_tables = VerticalEnginesPlugin().get_tenant_rls_tables()
    assert len(plugin_tables) == EXPECTED_TENANT_RLS_TABLE_COUNT, (
        f"Expected {EXPECTED_TENANT_RLS_TABLE_COUNT} vertical tenant RLS tables, "
        f"got {len(plugin_tables)}"
    )


def test_migrations_and_schema_sql_contain_all_resources_tables():
    """Vertical migrations (043, 044) must define all M15 tables with RLS and tenant policy."""
    mig_043 = REPO_ROOT / "nce_verticals" / "migrations" / "043_resources_registry.sql"
    mig_044 = REPO_ROOT / "nce_verticals" / "migrations" / "044_allocations_btree_gist.sql"

    assert mig_043.exists(), f"Migration file missing: {mig_043}"
    assert mig_044.exists(), f"Migration file missing: {mig_044}"

    mig_043_text = mig_043.read_text(encoding="utf-8")
    mig_044_text = mig_044.read_text(encoding="utf-8")

    # 043 checks
    assert "CREATE TABLE IF NOT EXISTS resources" in mig_043_text
    assert "ALTER TABLE resources ENABLE ROW LEVEL SECURITY" in mig_043_text
    assert "ALTER TABLE resources FORCE ROW LEVEL SECURITY" in mig_043_text
    assert "tenant_isolation_policy" in mig_043_text

    # 044 checks
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in mig_044_text
    for table in ["allocations", "travel_legs", "stays", "per_diems"]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in mig_044_text
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in mig_044_text
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in mig_044_text
        assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nce_app" in mig_044_text

    # Exclusion constraint check in 044
    assert "EXCLUDE USING gist" in mig_044_text
    assert "exclude_resource_double_booking" in mig_044_text
