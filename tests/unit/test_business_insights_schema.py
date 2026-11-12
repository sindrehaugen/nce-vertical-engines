"""Unit tests for Module 16 Business Insights Engine schema and RLS configuration."""

from __future__ import annotations

from pathlib import Path

from nce_verticals.plugin import BusinessInsightsPlugin, VerticalEnginesPlugin
from tests.expected_tenant_rls_table_count import EXPECTED_TENANT_RLS_TABLE_COUNT

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_business_insights_tables_registered_in_expected_tenant_rls_tables():
    """business_insights_kpi_snapshots must be registered in VerticalEnginesPlugin RLS tables."""
    plugin_tables = VerticalEnginesPlugin().get_tenant_rls_tables()
    engine_tables = BusinessInsightsPlugin().get_tenant_rls_tables()
    expected_tables = {
        "business_insights_kpi_snapshots": "namespace_id",
    }
    for table, col in expected_tables.items():
        assert table in plugin_tables, (
            f"Table {table!r} missing from VerticalEnginesPlugin().get_tenant_rls_tables()"
        )
        assert plugin_tables[table] == col, (
            f"Table {table!r} has namespace column {plugin_tables[table]!r}, expected {col!r}"
        )
        assert engine_tables.get(table) == col


def test_expected_tenant_rls_tables_total_count():
    """Total vertical tenant RLS table count -- see tests/expected_tenant_rls_table_count.py."""
    plugin_tables = VerticalEnginesPlugin().get_tenant_rls_tables()
    assert len(plugin_tables) == EXPECTED_TENANT_RLS_TABLE_COUNT, (
        f"Expected {EXPECTED_TENANT_RLS_TABLE_COUNT} vertical tenant RLS tables, "
        f"got {len(plugin_tables)}"
    )


def test_migration_and_schema_sql_contain_business_insights_tables():
    """Migration 045 must define business_insights_kpi_snapshots with RLS and tenant policy."""
    migration_file = REPO_ROOT / "nce_verticals" / "migrations" / "045_business_insights_engine.sql"

    assert migration_file.exists(), f"Migration file missing: {migration_file}"

    mig_text = migration_file.read_text(encoding="utf-8")

    table = "business_insights_kpi_snapshots"
    assert f"CREATE TABLE IF NOT EXISTS {table}" in mig_text
    assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in mig_text
    assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in mig_text
    assert f"CREATE POLICY tenant_isolation_policy ON {table}" in mig_text
