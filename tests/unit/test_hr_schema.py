"""Unit tests for Module 13 HR Engine schema and RLS configuration."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from nce_verticals.plugin import HRPlugin, VerticalEnginesPlugin
from tests.expected_tenant_rls_table_count import EXPECTED_TENANT_RLS_TABLE_COUNT


def test_hr_tables_registered_in_expected_tenant_rls_tables():
    """All 4 HR Engine tables must be registered in VerticalEnginesPlugin RLS tables."""
    plugin_tables = VerticalEnginesPlugin().get_tenant_rls_tables()
    engine_tables = HRPlugin().get_tenant_rls_tables()
    expected_hr_tables = {
        "employees": "namespace_id",
        "skills": "namespace_id",
        "certifications": "namespace_id",
        "absences": "namespace_id",
    }
    for table, col in expected_hr_tables.items():
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


@pytest.mark.asyncio
async def test_vertical_engines_plugin_capabilities_and_namespace_created_savepoint():
    """VerticalEnginesPlugin exposes active/full RLS tables, global tables, and SAVEPOINT hook."""
    plugin_odoo = VerticalEnginesPlugin(enabled_engines="odoo")
    active = plugin_odoo.get_active_engine_rls_tables()
    assert "odoo_integrations" in active
    assert "node_ownership_registry" in active
    assert "employees" not in active
    assert len(plugin_odoo.get_tenant_rls_tables()) == 96

    expected_globals = {
        "product_catalog",
        "geodata_osm_elements",
        "geodata_n50_land_cover",
        "geodata_place_names",
        "pricing_fx_rates",
    }
    assert plugin_odoo.get_global_tables() == expected_globals
    caps = plugin_odoo.get_capabilities()
    assert len(caps.tenant_rls_tables) == 96
    assert caps.global_tables == frozenset(expected_globals)

    entered_savepoint = False

    class _SavepointCtx:
        async def __aenter__(self) -> Any:
            nonlocal entered_savepoint
            entered_savepoint = True
            return self

        async def __aexit__(self, *_: Any) -> bool:
            return False

    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_SavepointCtx())

    class UndefinedTableError(Exception):
        sqlstate = "42P01"

    with patch(
        "nce.entity_resolution.ownership_seed.seed_node_ownership_registry",
        AsyncMock(
            side_effect=UndefinedTableError("relation node_ownership_registry does not exist")
        ),
    ):
        await plugin_odoo.on_namespace_created(conn, uuid4())

    assert entered_savepoint is True
