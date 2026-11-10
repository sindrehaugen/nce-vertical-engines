"""
nce_verticals/registry.py
=========================
Dual-Axis Taxonomy & Engine Registry for NCE Vertical Engines.

Axes:
- Axis 1 (Type): core-domain, erp-crm, infra-iot, observability, portal
- Axis 2 (Business Category): commercial, operations-delivery, finance-governance,
  service-support, av-it-integrator, enterprise-erp, field-service-ops

Cross-Engine Schema Dependencies (requires_schemas):
- support -> assets
- assets -> product, inventory
- project -> sales
- agreements -> sales
- economy -> sales, agreements
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class EngineSpec:
    """Specification of an engine registered in NCE Vertical Engines."""

    slug: str
    title: str
    package: str
    plugin_class: str
    types: frozenset[str]
    categories: frozenset[str]
    optional_deps: tuple[str, ...] = ()
    requires_schemas: tuple[str, ...] = ()
    migration_prefixes: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    tool_count: int = 0
    route_count: int = 0
    description: str | None = None
    name: str | None = None
    optional_dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        deps = self.optional_dependencies or self.optional_deps
        if self.optional_dependencies != deps:
            object.__setattr__(self, "optional_dependencies", deps)
        if self.optional_deps != deps:
            object.__setattr__(self, "optional_deps", deps)
        if self.name is None:
            object.__setattr__(self, "name", self.title)
        if self.description is None:
            object.__setattr__(self, "description", self.title)


VALID_TYPES: frozenset[str] = frozenset(
    {
        "core-domain",
        "erp-crm",
        "infra-iot",
        "observability",
        "portal",
    }
)

VALID_CATEGORIES: frozenset[str] = frozenset(
    {
        "commercial",
        "operations-delivery",
        "finance-governance",
        "service-support",
        "av-it-integrator",
        "enterprise-erp",
        "field-service-ops",
    }
)

ENGINE_ALIASES: dict[str, str] = {
    "warehouse": "inventory",
    "staff": "resources",
    "d365": "dynamics365",
    "diag": "diagnostics",
}

# 23 Canonical Engines
ENGINE_REGISTRY: dict[str, EngineSpec] = {
    "product": EngineSpec(
        slug="product",
        title="Product Master Catalog & Survivorship Engine",
        package="nce_verticals.product",
        plugin_class="ProductPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"commercial", "av-it-integrator"}),
        requires_schemas=(),
        aliases=(),
        tool_count=19,
        route_count=18,
    ),
    "procurement": EngineSpec(
        slug="procurement",
        title="Procurement, PO Lines & Deal Registration Engine",
        package="nce_verticals.procurement",
        plugin_class="ProcurementPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"commercial", "enterprise-erp"}),
        requires_schemas=(),
        aliases=(),
        tool_count=18,
        route_count=15,
    ),
    "agreements": EngineSpec(
        slug="agreements",
        title="Contract, SLA & Service Agreements Engine",
        package="nce_verticals.agreements",
        plugin_class="AgreementsPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"commercial", "finance-governance"}),
        requires_schemas=("sales",),
        aliases=(),
        tool_count=14,
        route_count=14,
    ),
    "vendors": EngineSpec(
        slug="vendors",
        title="Vendor, Supplier & Contractor Scoring Engine",
        package="nce_verticals.vendors",
        plugin_class="VendorsPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"commercial"}),
        requires_schemas=(),
        aliases=(),
        tool_count=12,
        route_count=11,
    ),
    "sales": EngineSpec(
        slug="sales",
        title="Sales, Quotes, Pipelines & Baselines Engine",
        package="nce_verticals.sales",
        plugin_class="SalesPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"commercial", "av-it-integrator", "enterprise-erp"}),
        requires_schemas=(),
        aliases=(),
        tool_count=28,
        route_count=29,
    ),
    "system_design": EngineSpec(
        slug="system_design",
        title="System Design, CAD & Topology Engineering Engine",
        package="nce_verticals.system_design",
        plugin_class="SystemDesignPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"operations-delivery", "av-it-integrator"}),
        requires_schemas=(),
        aliases=(),
        tool_count=18,
        route_count=17,
    ),
    "project": EngineSpec(
        slug="project",
        title="Project Management, Phase Gates & Automation Engine",
        package="nce_verticals.project",
        plugin_class="ProjectPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"operations-delivery", "av-it-integrator"}),
        requires_schemas=("sales",),
        aliases=(),
        tool_count=23,
        route_count=27,
    ),
    "economy": EngineSpec(
        slug="economy",
        title="Financial Accounting, Invoicing & Economy Postings Engine",
        package="nce_verticals.economy",
        plugin_class="EconomyPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"finance-governance", "enterprise-erp"}),
        requires_schemas=("sales", "agreements"),
        aliases=(),
        tool_count=19,
        route_count=22,
    ),
    "inventory": EngineSpec(
        slug="inventory",
        title="Inventory, RMA, Reorder Points & Valuation Engine",
        package="nce_verticals.inventory",
        plugin_class="InventoryPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset(
            {"operations-delivery", "av-it-integrator", "enterprise-erp", "field-service-ops"}
        ),
        requires_schemas=(),
        aliases=("warehouse",),
        tool_count=15,
        route_count=16,
    ),
    "assets": EngineSpec(
        slug="assets",
        title="Asset Tracking, Telemetry & Lifecycle Engine",
        package="nce_verticals.assets",
        plugin_class="AssetsPlugin",
        types=frozenset({"infra-iot"}),
        categories=frozenset({"service-support", "av-it-integrator", "field-service-ops"}),
        requires_schemas=("product", "inventory"),
        aliases=(),
        tool_count=12,
        route_count=13,
    ),
    "support": EngineSpec(
        slug="support",
        title="Customer Support, Tickets & SLA Engine",
        package="nce_verticals.support",
        plugin_class="SupportPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"service-support", "av-it-integrator", "field-service-ops"}),
        requires_schemas=("assets",),
        aliases=(),
        tool_count=25,
        route_count=22,
    ),
    "resources": EngineSpec(
        slug="resources",
        title="Staff & Resource Allocations Engine",
        package="nce_verticals.resources",
        plugin_class="ResourcesPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"operations-delivery", "field-service-ops"}),
        requires_schemas=(),
        aliases=("staff",),
        tool_count=16,
        route_count=19,
    ),
    "field_tech": EngineSpec(
        slug="field_tech",
        title="Field Tech Work Orders & Checklist Engine",
        package="nce_verticals.field_tech",
        plugin_class="FieldTechPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"operations-delivery", "av-it-integrator", "field-service-ops"}),
        requires_schemas=(),
        aliases=(),
        tool_count=14,
        route_count=11,
    ),
    "hr": EngineSpec(
        slug="hr",
        title="Human Resources & Employee Onboarding Engine",
        package="nce_verticals.hr",
        plugin_class="HRPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"finance-governance", "enterprise-erp"}),
        requires_schemas=(),
        aliases=(),
        tool_count=12,
        route_count=14,
    ),
    "marketing": EngineSpec(
        slug="marketing",
        title="Marketing Campaigns & Taxonomy Engine",
        package="nce_verticals.marketing",
        plugin_class="MarketingPlugin",
        types=frozenset({"core-domain"}),
        categories=frozenset({"commercial"}),
        requires_schemas=(),
        aliases=(),
        tool_count=12,
        route_count=14,
    ),
    "business_insights": EngineSpec(
        slug="business_insights",
        title="Executive Business Intelligence & Reporting Engine",
        package="nce_verticals.business_insights",
        plugin_class="BusinessInsightsPlugin",
        types=frozenset({"core-domain", "observability"}),
        categories=frozenset({"finance-governance"}),
        requires_schemas=(),
        aliases=(),
        tool_count=6,
        route_count=5,
    ),
    "customer_portal": EngineSpec(
        slug="customer_portal",
        title="Zero-Trust Customer Portal Engine",
        package="nce_verticals.customer_portal",
        plugin_class="CustomerPortalPlugin",
        types=frozenset({"portal"}),
        categories=frozenset({"service-support", "av-it-integrator"}),
        requires_schemas=(),
        aliases=(),
        tool_count=6,
        route_count=3,
    ),
    "netbox": EngineSpec(
        slug="netbox",
        title="NetBox Infrastructure & IPAM Synchronization Engine",
        package="nce_verticals.netbox",
        plugin_class="NetboxPlugin",
        types=frozenset({"infra-iot"}),
        categories=frozenset({"av-it-integrator"}),
        requires_schemas=(),
        aliases=(),
        tool_count=9,
        route_count=4,
    ),
    "dynamics365": EngineSpec(
        slug="dynamics365",
        title="Microsoft Dynamics 365 Integration Engine",
        package="nce_verticals.dynamics365",
        plugin_class="Dynamics365Plugin",
        types=frozenset({"erp-crm"}),
        categories=frozenset({"commercial", "enterprise-erp"}),
        requires_schemas=(),
        aliases=("d365",),
        tool_count=4,
        route_count=5,
    ),
    "diagnostics": EngineSpec(
        slug="diagnostics",
        title="System Diagnostics & Queue Observability Engine",
        package="nce_verticals.diagnostics",
        plugin_class="DiagnosticsPlugin",
        types=frozenset({"observability"}),
        categories=frozenset({"service-support", "av-it-integrator"}),
        requires_schemas=(),
        aliases=("diag",),
        tool_count=13,
        route_count=9,
    ),
    "odoo": EngineSpec(
        slug="odoo",
        title="Odoo ERP & LLM Cross-Talker Engine",
        package="nce_verticals.odoo",
        plugin_class="OdooPlugin",
        types=frozenset({"erp-crm"}),
        categories=frozenset({"commercial", "enterprise-erp"}),
        requires_schemas=(),
        aliases=(),
        tool_count=6,
        route_count=9,
    ),
    "salesforce": EngineSpec(
        slug="salesforce",
        title="Salesforce CRM & Integration Engine",
        package="nce_verticals.salesforce",
        plugin_class="SalesforcePlugin",
        types=frozenset({"erp-crm"}),
        categories=frozenset({"commercial", "enterprise-erp"}),
        requires_schemas=(),
        aliases=(),
        tool_count=10,
        route_count=7,
    ),
    "lighting_dali": EngineSpec(
        slug="lighting_dali",
        title="Relux/DIALux Lighting & IEC 62386 DALI-2 Engine",
        package="nce_verticals.lighting_dali",
        plugin_class="LightingDaliPlugin",
        types=frozenset({"infra-iot"}),
        categories=frozenset({"operations-delivery", "av-it-integrator", "field-service-ops"}),
        requires_schemas=(),
        aliases=(),
        tool_count=9,
        route_count=8,
    ),
}

ENGINE_CATALOG: dict[str, EngineSpec] = ENGINE_REGISTRY


def normalize_engine_slug(slug: str) -> str:
    """Resolve canonical slug from alias or canonical name.

    Raises ValueError listing valid slugs and aliases if not found.
    """
    s = slug.strip().lower()
    if s in ENGINE_REGISTRY:
        return s
    if s in ENGINE_ALIASES:
        return ENGINE_ALIASES[s]
    valid_slugs = sorted(ENGINE_REGISTRY.keys())
    valid_aliases = sorted(ENGINE_ALIASES.keys())
    raise ValueError(
        f"Unknown engine slug '{slug}'. Valid slugs: {valid_slugs}. Valid aliases: {valid_aliases}."
    )


def is_engine_installed(slug: str) -> bool:
    """Check if all spec.optional_dependencies can be found and spec.package succeeds find_spec."""
    canonical = normalize_engine_slug(slug)
    spec = ENGINE_REGISTRY[canonical]

    try:
        if importlib.util.find_spec(spec.package) is None:
            return False
    except (ImportError, ValueError, AttributeError):
        return False

    deps = getattr(spec, "optional_dependencies", None) or getattr(spec, "optional_deps", ()) or ()
    for dep in deps:
        try:
            if importlib.util.find_spec(dep) is None:
                return False
        except (ImportError, ValueError, AttributeError):
            return False

    return True


def resolve_schema_dependencies(slugs: Iterable[str]) -> list[str]:
    """Return topologically ordered list of engine slugs.

    Every engine's `requires_schemas` prerequisites appear BEFORE the dependent engine.
    Example:
      resolve_schema_dependencies(["support"]) -> ["product", "inventory", "assets", "support"]
      resolve_schema_dependencies(["project"]) -> ["sales", "project"]
    """
    result: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    canonical_slugs = [normalize_engine_slug(s) for s in slugs]

    def visit(slug: str) -> None:
        if slug in visiting:
            raise ValueError(f"Cyclic schema dependency detected at '{slug}'")
        if slug in visited:
            return
        visiting.add(slug)

        spec = ENGINE_REGISTRY.get(slug)
        if spec is not None:
            for req in spec.requires_schemas:
                req_canonical = normalize_engine_slug(req)
                visit(req_canonical)

        visiting.remove(slug)
        visited.add(slug)
        result.append(slug)

    for s in canonical_slugs:
        visit(s)

    return result


def _parse_filter_set(filter_raw: str | None, valid_set: frozenset[str], name: str) -> set[str]:
    """Parse comma-separated filter items and validate against allowed set."""
    if not filter_raw:
        return set()
    items = set()
    for item in filter_raw.split(","):
        cleaned = item.strip().lower()
        if not cleaned:
            continue
        if cleaned not in valid_set:
            raise ValueError(
                f"Unknown {name} filter '{cleaned}'. Valid options: {sorted(valid_set)}."
            )
        items.add(cleaned)
    return items


def resolve_enabled_engines(
    enabled_raw: str | None = None,
    type_filter: str | None = None,
    category_filter: str | None = None,
    *,
    include_schema_deps: bool = False,
) -> list[EngineSpec]:
    """Resolve active engine specifications across dual-axis filters and schema dependencies.

    Reads defaults from NCE_ENABLED_ENGINES, NCE_ENGINE_TYPE_FILTER, and
    NCE_ENGINE_CATEGORY_FILTER when arguments are None.
    """
    if enabled_raw is None:
        enabled_raw = os.environ.get("NCE_ENABLED_ENGINES")
    if type_filter is None:
        type_filter = os.environ.get("NCE_ENGINE_TYPE_FILTER")
    if category_filter is None:
        category_filter = os.environ.get("NCE_ENGINE_CATEGORY_FILTER")

    # Validate active axes
    active_types = _parse_filter_set(type_filter, VALID_TYPES, "type")
    active_categories = _parse_filter_set(category_filter, VALID_CATEGORIES, "category")

    raw_val = (enabled_raw or "").strip()

    # Determine base candidate engines
    if raw_val.lower() == "none":
        return []

    if not raw_val or raw_val.lower() in ("all", "*"):
        candidate_slugs = set(ENGINE_REGISTRY.keys())
    else:
        candidate_slugs = set()
        tokens = [t.strip() for t in raw_val.split(",") if t.strip()]
        for token in tokens:
            token_lower = token.lower()

            # Check for inline intersection: type:X+category:Y or category:Y+type:X
            if "+" in token_lower:
                subparts = token_lower.split("+")
                part_types: set[str] = set()
                part_cats: set[str] = set()
                for sub in subparts:
                    sub = sub.strip()
                    if sub.startswith("type:"):
                        t_name = sub[len("type:") :]
                        if t_name not in VALID_TYPES:
                            raise ValueError(
                                f"Unknown type '{t_name}' in selector '{token}'. "
                                f"Valid types: {sorted(VALID_TYPES)}."
                            )
                        part_types.add(t_name)
                    elif sub.startswith("category:") or sub.startswith("cat:"):
                        c_name = (
                            sub[len("category:") :]
                            if sub.startswith("category:")
                            else sub[len("cat:") :]
                        )
                        if c_name not in VALID_CATEGORIES:
                            raise ValueError(
                                f"Unknown category '{c_name}' in selector '{token}'. "
                                f"Valid categories: {sorted(VALID_CATEGORIES)}."
                            )
                        part_cats.add(c_name)
                    else:
                        raise ValueError(
                            f"Invalid selector combination '{token}'. "
                            f"Expected 'type:<t>+category:<c>'."
                        )
                # Matches engines having any/all specified
                matched = {
                    s
                    for s, spec in ENGINE_REGISTRY.items()
                    if (not part_types or any(t in spec.types for t in part_types))
                    and (not part_cats or any(c in spec.categories for c in part_cats))
                }
                candidate_slugs.update(matched)

            elif token_lower.startswith("type:"):
                t_name = token_lower[len("type:") :]
                if t_name not in VALID_TYPES:
                    raise ValueError(
                        f"Unknown type '{t_name}' in selector '{token}'. "
                        f"Valid types: {sorted(VALID_TYPES)}."
                    )
                candidate_slugs.update(
                    s for s, spec in ENGINE_REGISTRY.items() if t_name in spec.types
                )
            elif token_lower.startswith("category:") or token_lower.startswith("cat:"):
                c_name = (
                    token_lower[len("category:") :]
                    if token_lower.startswith("category:")
                    else token_lower[len("cat:") :]
                )
                if c_name not in VALID_CATEGORIES:
                    raise ValueError(
                        f"Unknown category '{c_name}' in selector '{token}'. "
                        f"Valid categories: {sorted(VALID_CATEGORIES)}."
                    )
                candidate_slugs.update(
                    s for s, spec in ENGINE_REGISTRY.items() if c_name in spec.categories
                )
            else:
                # Canonical slug or alias
                canonical = normalize_engine_slug(token_lower)
                candidate_slugs.add(canonical)

    # Filter candidate engines by active_types and active_categories (intersection across axes)
    filtered_slugs = set()
    for s in candidate_slugs:
        spec = ENGINE_REGISTRY[s]
        if active_types and not any(t in spec.types for t in active_types):
            continue
        if active_categories and not any(c in spec.categories for c in active_categories):
            continue
        filtered_slugs.add(s)

    if include_schema_deps:
        ordered_slugs = resolve_schema_dependencies(filtered_slugs)
    else:
        # Preserve consistent canonical registry order
        ordered_slugs = [s for s in ENGINE_REGISTRY if s in filtered_slugs]

    return [ENGINE_REGISTRY[s] for s in ordered_slugs]
