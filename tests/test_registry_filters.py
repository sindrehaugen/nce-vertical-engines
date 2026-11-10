"""Comprehensive unit and clean-room wheel tests for the 23-engine Dual-Axis Registry,
Type Filter + Business Category Filter resolution, topological SQL schema dependency graph,
lazy plugin loading, CLI, packaged config_data/migrations, and Workplace Telemetry opt-in gate.
"""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

import pytest

from nce_verticals.cli import main as cli_main
from nce_verticals.dynamics365.ingestion import (
    DataverseIngestionWorker,
)
from nce_verticals.dynamics365.ingestion import (
    is_workplace_telemetry_enabled as d365_telemetry_enabled,
)
from nce_verticals.dynamics365.mcp_handlers import handle_d365_case_stress_report
from nce_verticals.netbox.contacts import (
    NetBoxContactSync,
)
from nce_verticals.netbox.contacts import (
    is_workplace_telemetry_enabled as netbox_telemetry_enabled,
)
from nce_verticals.plugin import VerticalEnginesPlugin
from nce_verticals.registry import (
    ENGINE_ALIASES,
    ENGINE_REGISTRY,
    VALID_CATEGORIES,
    VALID_TYPES,
    normalize_engine_slug,
    resolve_enabled_engines,
    resolve_schema_dependencies,
)


def test_registry_has_all_23_engines_and_exact_dual_axis_taxonomy() -> None:
    assert len(ENGINE_REGISTRY) == 23
    expected_23 = {
        "product",
        "procurement",
        "agreements",
        "vendors",
        "sales",
        "system_design",
        "project",
        "economy",
        "inventory",
        "assets",
        "support",
        "resources",
        "field_tech",
        "hr",
        "marketing",
        "business_insights",
        "customer_portal",
        "netbox",
        "dynamics365",
        "diagnostics",
        "odoo",
        "salesforce",
        "lighting_dali",
    }
    assert set(ENGINE_REGISTRY.keys()) == expected_23

    # Axis 1: 5 Type filters
    assert VALID_TYPES == {
        "core-domain",
        "erp-crm",
        "infra-iot",
        "observability",
        "portal",
    }
    type_counts = {
        t: [s for s, spec in ENGINE_REGISTRY.items() if t in spec.types] for t in VALID_TYPES
    }
    assert len(type_counts["core-domain"]) == 15
    assert sorted(type_counts["erp-crm"]) == ["dynamics365", "odoo", "salesforce"]
    assert sorted(type_counts["infra-iot"]) == ["assets", "lighting_dali", "netbox"]
    assert sorted(type_counts["observability"]) == ["business_insights", "diagnostics"]
    assert sorted(type_counts["portal"]) == ["customer_portal"]

    # Axis 2: 7 Business Category filters
    assert VALID_CATEGORIES == {
        "commercial",
        "operations-delivery",
        "finance-governance",
        "service-support",
        "av-it-integrator",
        "enterprise-erp",
        "field-service-ops",
    }
    cat_counts = {
        c: [s for s, spec in ENGINE_REGISTRY.items() if c in spec.categories]
        for c in VALID_CATEGORIES
    }
    assert len(cat_counts["commercial"]) == 9
    assert len(cat_counts["operations-delivery"]) == 6
    assert len(cat_counts["finance-governance"]) == 4
    assert len(cat_counts["service-support"]) == 4
    assert len(cat_counts["av-it-integrator"]) == 12
    assert len(cat_counts["enterprise-erp"]) == 8
    assert len(cat_counts["field-service-ops"]) == 6


def test_legacy_slug_aliases() -> None:
    assert ENGINE_ALIASES["warehouse"] == "inventory"
    assert ENGINE_ALIASES["staff"] == "resources"
    assert ENGINE_ALIASES["d365"] == "dynamics365"
    assert ENGINE_ALIASES["diag"] == "diagnostics"

    assert normalize_engine_slug("warehouse") == "inventory"
    assert normalize_engine_slug("staff") == "resources"
    assert normalize_engine_slug("d365") == "dynamics365"
    assert normalize_engine_slug("diag") == "diagnostics"

    resolved = resolve_enabled_engines("warehouse,staff,d365,diag")
    assert [s.slug for s in resolved] == [
        "inventory",
        "resources",
        "dynamics365",
        "diagnostics",
    ]


def test_five_installation_and_resolution_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NCE_ENABLED_ENGINES", raising=False)
    monkeypatch.delenv("NCE_ENGINE_TYPE_FILTER", raising=False)
    monkeypatch.delenv("NCE_ENGINE_CATEGORY_FILTER", raising=False)

    # Mode 1: Single engine
    single = resolve_enabled_engines("odoo")
    assert [s.slug for s in single] == ["odoo"]

    # Mode 2: Type filter (env / arg and inline)
    by_type = resolve_enabled_engines(type_filter="erp-crm")
    assert sorted(s.slug for s in by_type) == ["dynamics365", "odoo", "salesforce"]
    by_type_inline = resolve_enabled_engines("type:erp-crm")
    assert sorted(s.slug for s in by_type_inline) == ["dynamics365", "odoo", "salesforce"]

    # Mode 3: Business Category filter (env / arg and inline)
    by_cat = resolve_enabled_engines(category_filter="commercial")
    assert len(by_cat) == 9
    assert sorted(s.slug for s in by_cat) == sorted(
        [
            "product",
            "procurement",
            "agreements",
            "vendors",
            "sales",
            "salesforce",
            "dynamics365",
            "odoo",
            "marketing",
        ]
    )
    assert [s.slug for s in resolve_enabled_engines("category:commercial")] == [
        s.slug for s in by_cat
    ]
    assert [s.slug for s in resolve_enabled_engines("cat:commercial")] == [s.slug for s in by_cat]

    # Mode 4: Combined Type + Category Intersection
    intersect = resolve_enabled_engines(type_filter="infra-iot", category_filter="av-it-integrator")
    assert sorted(s.slug for s in intersect) == ["assets", "lighting_dali", "netbox"]

    intersect_inline = resolve_enabled_engines("type:infra-iot+category:av-it-integrator")
    assert sorted(s.slug for s in intersect_inline) == [
        "assets",
        "lighting_dali",
        "netbox",
    ]

    disjoint = resolve_enabled_engines(type_filter="portal", category_filter="commercial")
    assert disjoint == []

    # Mode 5: All 23 engines
    all_engines = resolve_enabled_engines("all")
    assert len(all_engines) == 23


def test_unknown_slug_type_or_category_raises_informative_value_error() -> None:
    with pytest.raises(ValueError, match="Valid slugs"):
        resolve_enabled_engines("nonexistent_engine")

    with pytest.raises(ValueError, match="core-domain"):
        resolve_enabled_engines(type_filter="bogus-type")

    with pytest.raises(ValueError, match="av-it-integrator"):
        resolve_enabled_engines(category_filter="bogus-category")

    with pytest.raises(ValueError, match="Valid types"):
        resolve_enabled_engines("type:bogus-type")

    with pytest.raises(ValueError, match="Valid categories"):
        resolve_enabled_engines("category:bogus-category")


def test_topological_requires_schemas_resolution() -> None:
    # support -> assets -> (product, inventory)
    support_chain = resolve_schema_dependencies(["support"])
    assert set(support_chain) == {"product", "inventory", "assets", "support"}
    assert support_chain.index("product") < support_chain.index("assets")
    assert support_chain.index("inventory") < support_chain.index("assets")
    assert support_chain.index("assets") < support_chain.index("support")

    # project -> sales
    project_chain = resolve_schema_dependencies(["project"])
    assert project_chain == ["sales", "project"]

    # economy -> sales, agreements (where agreements -> sales)
    economy_chain = resolve_schema_dependencies(["economy"])
    assert economy_chain == ["sales", "agreements", "economy"]


def test_lazy_plugin_instantiation_and_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NCE_ENABLED_ENGINES", raising=False)
    monkeypatch.delenv("NCE_ENGINE_TYPE_FILTER", raising=False)
    monkeypatch.delenv("NCE_ENGINE_CATEGORY_FILTER", raising=False)

    p_odoo = VerticalEnginesPlugin(enabled_engines="odoo")
    assert [sp.name for sp in p_odoo.sub_plugins] == ["odoo"]
    assert p_odoo.sub_plugins[0].types == ["erp-crm"]
    assert sorted(p_odoo.sub_plugins[0].categories) == ["commercial", "enterprise-erp"]

    p_erp = VerticalEnginesPlugin(type_filter="erp-crm")
    assert sorted(sp.name for sp in p_erp.sub_plugins) == [
        "dynamics365",
        "odoo",
        "salesforce",
    ]

    p_intersect = VerticalEnginesPlugin(type_filter="infra-iot", category_filter="av-it-integrator")
    assert sorted(sp.name for sp in p_intersect.sub_plugins) == [
        "assets",
        "lighting_dali",
        "netbox",
    ]

    p_support = VerticalEnginesPlugin(enabled_engines="support")
    assert p_support.get_required_schema_engines() == [
        "product",
        "inventory",
        "assets",
        "support",
    ]

    descriptors = p_erp.get_plugin_descriptors(type_filter="erp-crm")
    assert len(descriptors) == 3
    assert {d["slug"] for d in descriptors} == {"dynamics365", "odoo", "salesforce"}
    for d in descriptors:
        assert "erp-crm" in d["types"]
        assert d["enabled"] is True

    all_descriptors = p_erp.get_engine_descriptors()
    assert len(all_descriptors) == 23
    for d in all_descriptors:
        assert d["tool_count"] > 0
        assert d["route_count"] > 0
        assert d["install_extra"] == f"nce-vertical-engines[{d['slug']}]"
    by_slug = {d["slug"]: d for d in all_descriptors}
    assert by_slug["agreements"]["tool_count"] == 14
    assert by_slug["agreements"]["route_count"] == 14
    assert by_slug["sales"]["tool_count"] == 28
    assert by_slug["sales"]["route_count"] == 29
    assert by_slug["economy"]["tool_count"] == 19
    assert by_slug["economy"]["route_count"] == 22


def test_packaged_config_data_and_sql_migrations_chain() -> None:
    cfg_root = importlib.resources.files("nce_verticals").joinpath("config_data")
    assert cfg_root.joinpath("sales-commission.json").is_file()
    assert cfg_root.joinpath("product-quality.json").is_file()
    assert cfg_root.joinpath("redaction", "public-quote-redaction.json").is_file()

    mig_dir = VerticalEnginesPlugin(enabled_engines="odoo").get_migrations_dir()
    assert isinstance(mig_dir, Path)
    assert mig_dir.is_dir()
    sql_files = sorted(mig_dir.glob("*.sql"))
    assert len(sql_files) >= 40
    for sql_file in sql_files:
        content = sql_file.read_text(encoding="utf-8")
        assert content.strip(), f"Empty SQL migration: {sql_file.name}"


def test_cli_list_filters_and_json_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cli_main(["list", "--type", "erp-crm", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert sorted(item["slug"] for item in data) == [
        "dynamics365",
        "odoo",
        "salesforce",
    ]

    rc2 = cli_main(["list", "--type", "infra-iot", "--category", "av-it-integrator", "--json"])
    assert rc2 == 0
    data2 = json.loads(capsys.readouterr().out)
    assert sorted(item["slug"] for item in data2) == [
        "assets",
        "lighting_dali",
        "netbox",
    ]


@pytest.mark.asyncio
async def test_workplace_telemetry_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NCE_ENABLE_WORKPLACE_TELEMETRY", raising=False)
    assert netbox_telemetry_enabled() is False
    assert d365_telemetry_enabled() is False

    sync = NetBoxContactSync(pg_pool=None, netbox_client=None)  # type: ignore[arg-type]
    stress_report = await sync.evaluate_contact_stress_report(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        "alice",
        "alice@company.no",
        None,  # type: ignore[arg-type]
    )
    assert stress_report["telemetry_enabled"] is False
    assert stress_report["status"] == "telemetry_disabled"

    tensor = DataverseIngestionWorker._compute_empathic_tensor(
        None,  # type: ignore[arg-type]
        "critical outage urgent broken unacceptable",
    )
    assert tensor == [5.0, 0.0, 5.0, 0.0, 0.0, 0.0]

    d365_raw = await handle_d365_case_stress_report(
        None,  # type: ignore[arg-type]
        {
            "namespace_id": "00000000-0000-0000-0000-000000000001",
            "account_name": "Acme Corp",
        },
    )
    d365_report = json.loads(d365_raw) if isinstance(d365_raw, str) else d365_raw
    assert d365_report["telemetry_enabled"] is False
    assert d365_report["burnout_alert"] is False
