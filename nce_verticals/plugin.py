"""NCE Vertical Engines Plugin Spine.

Implements NCEPlugin for all 20+ business engines and provides the unified
VerticalEnginesPlugin for registering tools, routes, background workers, and cognitive hooks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from starlette.routing import Route
except ImportError:

    class Route:  # type: ignore[no-redef]
        def __init__(self, path: str, endpoint: Any, methods: list[str] | None = None) -> None:
            self.path = path
            self.endpoint = endpoint
            self.methods = methods or ["GET"]


def _h(module: Any, handler_name: str) -> Any:
    async def _call(engine: Any, arguments: dict[str, Any]) -> Any:
        fn = getattr(module, handler_name)
        return await fn(engine, arguments)

    _call.__name__ = handler_name
    _call.__qualname__ = f"{getattr(module, '__name__', 'nce_verticals')}.{handler_name}"
    return _call


@dataclass(frozen=True)
class _FallbackToolSpec:
    handler: Any
    admin_only: bool = False
    mutation: bool = False
    cacheable: bool = False
    migration: bool = False
    engine: str | None = None
    engine_dependencies: tuple[str, ...] | None = None


def ToolSpec(*args: Any, **kwargs: Any) -> Any:
    try:
        from nce.tool_registry import ToolSpec as _CoreToolSpec

        return _CoreToolSpec(*args, **kwargs)
    except Exception:
        return _FallbackToolSpec(*args, **kwargs)


log = logging.getLogger("nce_verticals.plugin")


def _route_key(r: Any) -> tuple[Any, tuple[str, ...]]:
    path = getattr(r, "path", None)
    methods = tuple(sorted(str(m).upper() for m in (getattr(r, "methods", None) or ())))
    return (path, methods)


def _mount_routes(app: Any, routes: list[Route]) -> None:
    if not routes:
        return
    if hasattr(app, "routes"):
        existing = {_route_key(r) for r in app.routes}
        for r in routes:
            rk = _route_key(r)
            if rk not in existing:
                app.routes.append(r)
                existing.add(rk)
    elif isinstance(app, list):
        existing = {_route_key(r) for r in app}
        for r in routes:
            rk = _route_key(r)
            if rk not in existing:
                app.append(r)
                existing.add(rk)


SHARED_SPINE_TENANT_RLS_TABLES: tuple[str, ...] = (
    "node_ownership_registry",
    "entity_merge_queue",
    "source_mode_config",
    "divergence_log",
    "source_mode_heartbeat",
    "decision_feedback",
    "notifications",
    "reminders",
    "notification_subscriptions",
    "documents",
    "document_links",
    "document_shares",
    "legal_entities",
    "sites",
    "bom_line_content",
    "entra_id_audit_log",
    "entra_id_configs",
    "entra_id_sessions",
)

VERTICAL_GLOBAL_TABLES: frozenset[str] = frozenset(
    {
        "product_catalog",
        "geodata_osm_elements",
        "geodata_n50_land_cover",
        "geodata_place_names",
        "pricing_fx_rates",
    }
)


@dataclass(frozen=True)
class _FallbackPluginCapabilities:
    tenant_rls_tables: dict[str, str]
    global_tables: frozenset[str]
    unmanaged_pg_sites: frozenset[str]


class _EngineRLSPluginMixin:
    """Shared RLS and global table capability mixin for vertical engine plugins."""

    TENANT_RLS_TABLES: tuple[str, ...] = ()
    GLOBAL_TABLES: frozenset[str] = frozenset()

    def get_tenant_rls_tables(self) -> dict[str, str]:
        return {tbl: "namespace_id" for tbl in self.TENANT_RLS_TABLES}

    def get_global_tables(self) -> set[str]:
        return set(self.GLOBAL_TABLES)


class AgreementsPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "agreements"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "agreement_review_queue",
        "agreement_extraction_runs",
        "agreements",
        "agreement_parties",
        "agreement_templates",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.agreements import mcp_handlers as agreements_mcp_handlers

        tools = {
            "agreements_lookup_terms": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_lookup_terms"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "agreements_coverage_matrix": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_coverage_matrix"),
                cacheable=True,
                admin_only=False,
                mutation=False,
                engine="agreements",
                engine_dependencies=("agreements", "economy"),
            ),
            "agreements_reconcile_kickback": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_reconcile_kickback"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "agreements_run_compliance_audit": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_run_compliance_audit"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "agreements_extract": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_extract"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "agreements_create": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_create"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "agreements_suggest_revision": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_suggest_revision"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "agreements_request_signature": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_request_signature"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "agreements_record_signature": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_record_signature"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "agreements_review_extraction": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_review_extraction"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "agreements_get_index_series": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_get_index_series"),
                cacheable=True,
                admin_only=False,
                mutation=False,
                engine="agreements",
            ),
            "agreements_calculate_index_adjustment": ToolSpec(
                _h(
                    agreements_mcp_handlers,
                    "handle_agreements_calculate_index_adjustment",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
                engine="agreements",
            ),
            "agreements_get_price_rules": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_get_price_rules"),
                cacheable=True,
                admin_only=False,
                mutation=False,
                engine="agreements",
            ),
            "agreements_evaluate_price_rule": ToolSpec(
                _h(agreements_mcp_handlers, "handle_agreements_evaluate_price_rule"),
                cacheable=True,
                admin_only=False,
                mutation=False,
                engine="agreements",
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import agreements as agreements_handlers

        routes = [
            Route(
                "/api/agreements",
                endpoint=agreements_handlers.api_agreements_list,
                methods=["GET"],
            ),
            Route(
                "/api/agreements/coverage",
                endpoint=agreements_handlers.api_agreements_coverage,
                methods=["GET"],
            ),
            Route(
                "/api/agreements/extract",
                endpoint=agreements_handlers.api_agreements_extract,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/review",
                endpoint=agreements_handlers.api_agreements_review,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/reconcile",
                endpoint=agreements_handlers.api_agreements_reconcile,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/create",
                endpoint=agreements_handlers.api_agreements_create,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/suggest-revision",
                endpoint=agreements_handlers.api_agreements_suggest_revision,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/comment",
                endpoint=agreements_handlers.api_agreements_comment,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/request-signature",
                endpoint=agreements_handlers.api_agreements_request_signature,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/record-signature",
                endpoint=agreements_handlers.api_agreements_record_signature,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/compliance-audit",
                endpoint=agreements_handlers.api_agreements_compliance_audit,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/suggest-terms",
                endpoint=agreements_handlers.api_agreements_suggest_terms,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/sla-coverage",
                endpoint=agreements_handlers.api_agreements_sla_coverage,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/upsert",
                endpoint=agreements_handlers.api_agreements_upsert,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/index-series",
                endpoint=agreements_handlers.api_agreements_get_index_series,
                methods=["GET"],
            ),
            Route(
                "/api/agreements/index-series/calculate",
                endpoint=agreements_handlers.api_agreements_calculate_index_adjustment,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/index-series/{id}",
                endpoint=agreements_handlers.api_agreements_get_index_series,
                methods=["GET"],
            ),
            Route(
                "/api/agreements/price-rules",
                endpoint=agreements_handlers.api_agreements_get_price_rules,
                methods=["GET"],
            ),
            Route(
                "/api/agreements/price-rules/evaluate",
                endpoint=agreements_handlers.api_agreements_evaluate_price_rule,
                methods=["POST"],
            ),
            Route(
                "/api/agreements/price-rules/{id}",
                endpoint=agreements_handlers.api_agreements_get_price_rules,
                methods=["GET"],
            ),
            Route(
                "/api/agreements/{id}",
                endpoint=agreements_handlers.api_agreements_detail,
                methods=["GET"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class AssetsPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "assets"
    TENANT_RLS_TABLES: tuple[str, ...] = ("assets", "telemetry_samples")

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.assets import mcp_handlers as assets_mcp_handlers

        tools = {
            "assets_ping": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_ping"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "assets_get": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_get"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "assets_list": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_list"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "assets_advance_lifecycle": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_advance_lifecycle"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "assets_seed_from_bom": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_seed_from_bom"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "assets_pull_telemetry": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_pull_telemetry"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "assets_attach_sla": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_attach_sla"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "assets_compute_health": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_compute_health"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "assets_check_warranty_eol": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_check_warranty_eol"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "assets_sync_netbox": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_sync_netbox"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "assets_generate_qr": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_generate_qr"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "assets_record_failure_pattern": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_record_failure_pattern"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "assets_service_history": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_service_history"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "assets_assign_person": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_assign_person"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "assets_unassign_person": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_unassign_person"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "assets_list_person_assets": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_list_person_assets"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "assets_link_subcomponent": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_link_subcomponent"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "assets_unlink_subcomponent": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_unlink_subcomponent"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "assets_list_subcomponents": ToolSpec(
                _h(assets_mcp_handlers, "handle_assets_list_subcomponents"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import assets as assets_handlers

        routes = [
            Route(
                "/api/assets/seed-from-bom",
                endpoint=assets_handlers.api_assets_seed_from_bom,
                methods=["POST"],
            ),
            Route(
                "/api/assets/sla/attach",
                endpoint=assets_handlers.api_assets_attach_sla,
                methods=["POST"],
            ),
            Route(
                "/api/assets/health",
                endpoint=assets_handlers.api_assets_health,
                methods=["GET"],
            ),
            Route(
                "/api/assets/warranty-eol",
                endpoint=assets_handlers.api_assets_check_warranty_eol,
                methods=["GET"],
            ),
            Route(
                "/api/assets/sync-netbox",
                endpoint=assets_handlers.api_assets_sync_netbox,
                methods=["POST"],
            ),
            Route(
                "/api/assets/register",
                endpoint=assets_handlers.api_assets_register,
                methods=["GET"],
            ),
            Route(
                "/api/assets/qr",
                endpoint=assets_handlers.api_assets_generate_qr,
                methods=["GET"],
            ),
            Route(
                "/api/assets/merge",
                endpoint=assets_handlers.api_assets_merge_queue,
                methods=["GET"],
            ),
            Route(
                "/api/assets",
                endpoint=assets_handlers.api_assets_list,
                methods=["GET"],
            ),
            Route(
                "/api/assets/{id}",
                endpoint=assets_handlers.api_assets_get,
                methods=["GET"],
            ),
            Route(
                "/api/assets/{id}/move",
                endpoint=assets_handlers.api_assets_move,
                methods=["POST"],
            ),
            Route(
                "/api/assets/{id}/merge",
                endpoint=assets_handlers.api_assets_merge,
                methods=["POST"],
            ),
            Route(
                "/api/assets/{id}/link-product",
                endpoint=assets_handlers.api_assets_link_product,
                methods=["POST"],
            ),
            Route(
                "/api/assets/{id}/assign",
                endpoint=assets_handlers.api_assets_assign_person,
                methods=["POST"],
            ),
            Route(
                "/api/assets/{id}/unassign",
                endpoint=assets_handlers.api_assets_unassign_person,
                methods=["POST"],
            ),
            Route(
                "/api/assets/by-person/{employee_id}",
                endpoint=assets_handlers.api_assets_list_person_assets,
                methods=["GET"],
            ),
            Route(
                "/api/assets/{id}/sub-components",
                endpoint=assets_handlers.api_assets_link_subcomponent,
                methods=["POST"],
            ),
            Route(
                "/api/assets/{id}/sub-components/{sub_id}",
                endpoint=assets_handlers.api_assets_unlink_subcomponent,
                methods=["DELETE"],
            ),
            Route(
                "/api/assets/{id}/sub-components",
                endpoint=assets_handlers.api_assets_list_subcomponents,
                methods=["GET"],
            ),
            Route(
                "/api/assets/{id}/service-history",
                endpoint=assets_handlers.api_assets_service_history,
                methods=["GET"],
            ),
            Route(
                "/api/assets/{id}/qr",
                endpoint=assets_handlers.api_assets_generate_qr,
                methods=["GET"],
            ),
            Route(
                "/api/assets/{id}/lifecycle",
                endpoint=assets_handlers.api_assets_advance_lifecycle,
                methods=["POST"],
            ),
            Route(
                "/api/assets/{id}/telemetry",
                endpoint=assets_handlers.api_assets_pull_telemetry,
                methods=["POST"],
            ),
            Route(
                "/api/assets/{id}/health",
                endpoint=assets_handlers.api_assets_health,
                methods=["GET"],
            ),
            Route(
                "/api/assets/{id}/failure-pattern",
                endpoint=assets_handlers.api_assets_record_failure_pattern,
                methods=["POST"],
            ),
            Route(
                "/api/assets/failure-pattern",
                endpoint=assets_handlers.api_assets_record_failure_pattern,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        try:
            log.debug("Registered assets cognitive hooks")
        except Exception as exc:
            log.warning("Failed registering assets cognitive hooks: %s", exc)

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class BusinessInsightsPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "business_insights"
    TENANT_RLS_TABLES: tuple[str, ...] = ("business_insights_kpi_snapshots",)

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.business_insights import (
            mcp_handlers as business_insights_mcp_handlers,
        )

        tools = {
            "business_insights_morning_brief": ToolSpec(
                _h(
                    business_insights_mcp_handlers,
                    "handle_business_insights_morning_brief",
                ),
                cacheable=True,
                admin_only=True,
                mutation=False,
                engine="business_insights",
                engine_dependencies=(
                    "business_insights",
                    "economy",
                    "project",
                    "support",
                    "sales",
                    "resources",
                    "inventory",
                ),
            ),
            "business_insights_risk_radar": ToolSpec(
                _h(
                    business_insights_mcp_handlers,
                    "handle_business_insights_risk_radar",
                ),
                cacheable=True,
                admin_only=True,
                mutation=False,
                engine="business_insights",
                engine_dependencies=(
                    "business_insights",
                    "economy",
                    "project",
                    "support",
                    "sales",
                    "resources",
                    "inventory",
                    "assets",
                    "agreements",
                ),
            ),
            "business_insights_run_scenario": ToolSpec(
                _h(
                    business_insights_mcp_handlers,
                    "handle_business_insights_run_scenario",
                ),
                cacheable=False,
                admin_only=True,
                mutation=False,
                engine="business_insights",
            ),
            "business_insights_generate_board_pack": ToolSpec(
                _h(
                    business_insights_mcp_handlers,
                    "handle_business_insights_generate_board_pack",
                ),
                cacheable=False,
                admin_only=True,
                mutation=False,
                engine="business_insights",
            ),
            "business_insights_kpi_dashboard": ToolSpec(
                _h(
                    business_insights_mcp_handlers,
                    "handle_business_insights_kpi_dashboard",
                ),
                cacheable=False,
                admin_only=True,
                mutation=True,
                engine="business_insights",
                engine_dependencies=(
                    "business_insights",
                    "economy",
                    "project",
                    "support",
                    "sales",
                    "resources",
                    "inventory",
                    "assets",
                ),
            ),
            "business_insights_ask_business": ToolSpec(
                _h(
                    business_insights_mcp_handlers,
                    "handle_business_insights_ask_business",
                ),
                cacheable=False,
                admin_only=True,
                mutation=False,
                engine="business_insights",
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import (
            business_insights as business_insights_handlers,
        )

        routes = [
            Route(
                "/api/business-insights/morning-brief",
                endpoint=business_insights_handlers.api_business_insights_morning_brief,
                methods=["GET"],
            ),
            Route(
                "/api/business-insights/risk-radar",
                endpoint=business_insights_handlers.api_business_insights_risk_radar,
                methods=["GET"],
            ),
            Route(
                "/api/business-insights/run-scenario",
                endpoint=business_insights_handlers.api_business_insights_run_scenario,
                methods=["POST"],
            ),
            Route(
                "/api/business-insights/board-pack",
                endpoint=business_insights_handlers.api_business_insights_board_pack,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/business-insights/kpi-dashboard",
                endpoint=business_insights_handlers.api_business_insights_kpi_dashboard,
                methods=["GET"],
            ),
            Route(
                "/api/business-insights/ask",
                endpoint=business_insights_handlers.api_business_insights_ask,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class CustomerPortalPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "customer_portal"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "portal_users",
        "portal_document_shares",
        "portal_service_requests",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.customer_portal import (
            mcp_handlers as customer_portal_mcp_handlers,
        )

        tools = {
            "customer_portal_room_tracker": ToolSpec(
                _h(customer_portal_mcp_handlers, "handle_customer_portal_room_tracker"),
                cacheable=True,
                engine="customer_portal",
                engine_dependencies=(
                    "customer_portal",
                    "system_design",
                    "inventory",
                    "assets",
                ),
                admin_only=True,
            ),
            "customer_portal_room_overview": ToolSpec(
                _h(customer_portal_mcp_handlers, "handle_customer_portal_room_overview"),
                cacheable=True,
                engine="customer_portal",
                engine_dependencies=(
                    "customer_portal",
                    "system_design",
                    "inventory",
                    "assets",
                ),
                admin_only=True,
            ),
            "customer_portal_asset_register": ToolSpec(
                _h(
                    customer_portal_mcp_handlers,
                    "handle_customer_portal_asset_register",
                ),
                cacheable=True,
                engine="customer_portal",
                engine_dependencies=("customer_portal", "assets"),
                admin_only=True,
            ),
            "customer_portal_list_documents": ToolSpec(
                _h(
                    customer_portal_mcp_handlers,
                    "handle_customer_portal_list_documents",
                ),
                cacheable=True,
                engine="customer_portal",
                admin_only=True,
            ),
            "customer_portal_sla_status": ToolSpec(
                _h(customer_portal_mcp_handlers, "handle_customer_portal_sla_status"),
                cacheable=True,
                engine="customer_portal",
                engine_dependencies=("customer_portal", "support", "agreements"),
                admin_only=True,
            ),
            "customer_portal_list_invoices": ToolSpec(
                _h(customer_portal_mcp_handlers, "handle_customer_portal_list_invoices"),
                cacheable=True,
                engine="customer_portal",
                engine_dependencies=("customer_portal", "economy"),
                admin_only=True,
            ),
            "customer_portal_advisor_answer": ToolSpec(
                _h(
                    customer_portal_mcp_handlers,
                    "handle_customer_portal_advisor_answer",
                ),
                cacheable=False,
                engine="customer_portal",
                admin_only=True,
            ),
            "customer_portal_raise_service_request": ToolSpec(
                _h(
                    customer_portal_mcp_handlers,
                    "handle_customer_portal_raise_service_request",
                ),
                cacheable=False,
                mutation=True,
                engine="customer_portal",
                admin_only=True,
            ),
            "customer_portal_register_expansion_interest": ToolSpec(
                _h(
                    customer_portal_mcp_handlers,
                    "handle_customer_portal_register_expansion_interest",
                ),
                cacheable=False,
                mutation=True,
                engine="customer_portal",
                admin_only=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        pass

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class DiagnosticsPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "diagnostics"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "diag_ingestions",
        "diag_anomalies",
        "device_health_rollup",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.diagnostics import mcp_handlers as diag_mcp_handlers

        tools = {
            "diag_ingest_bundle": ToolSpec(
                _h(diag_mcp_handlers, "handle_diag_ingest_bundle"),
                mutation=True,
            ),
            "diag_commit_bundle": ToolSpec(
                _h(diag_mcp_handlers, "handle_diag_commit_bundle"),
                mutation=True,
            ),
            "diag_digest_status": ToolSpec(
                _h(diag_mcp_handlers, "handle_diag_digest_status"),
                cacheable=True,
            ),
            "diag_device_health": ToolSpec(
                _h(diag_mcp_handlers, "handle_diag_device_health"),
                cacheable=True,
            ),
            "diag_list_anomalies": ToolSpec(
                _h(diag_mcp_handlers, "handle_diag_list_anomalies"),
                cacheable=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        pass

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class Dynamics365Plugin(_EngineRLSPluginMixin):
    plugin_id: str = "dynamics365"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "d365_integrations",
        "d365_netbox_mappings",
        "d365_sync_runs",
        "d365_delta_tokens",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.dynamics365 import mcp_handlers as d365_mcp_handlers

        tools = {
            "d365_query_case": ToolSpec(
                _h(d365_mcp_handlers, "handle_d365_query_case"),
                cacheable=True,
            ),
            "d365_sync_now": ToolSpec(
                _h(d365_mcp_handlers, "handle_d365_sync_now"),
                admin_only=True,
                mutation=True,
            ),
            "d365_case_stress_report": ToolSpec(
                _h(d365_mcp_handlers, "handle_d365_case_stress_report"),
                cacheable=True,
            ),
            "d365_list_sla_breaches": ToolSpec(
                _h(d365_mcp_handlers, "handle_d365_list_sla_breaches"),
                admin_only=True,
            ),
            "d365_netbox_mappings": ToolSpec(
                _h(d365_mcp_handlers, "handle_d365_netbox_mappings"),
                cacheable=True,
            ),
            "d365_sync_status": ToolSpec(
                _h(d365_mcp_handlers, "handle_d365_sync_status"),
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        pass

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class EconomyPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "economy"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "economy_bom_actual_costs",
        "economy_postings",
        "economy_contracts",
        "economy_billing_runs",
        "economy_billing_candidates",
        "economy_billing_candidate_lines",
        "economy_customer_invoices",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.economy import mcp_handlers as economy_mcp_handlers

        tools = {
            "economy_match_invoice": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_match_invoice"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_compute_periodisering": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_compute_periodisering"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_emit_event": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_emit_event"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_forecast_cashflow": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_forecast_cashflow"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_snapshot_mrr_arr_churn": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_snapshot_mrr_arr_churn"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_compute_dunning": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_compute_dunning"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_compute_recognition_schedule": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_compute_recognition_schedule"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_gl_sync_status": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_gl_sync_status"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_generate_close_narrative": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_generate_close_narrative"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_approve_invoice": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_approve_invoice"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "economy_generate_kid": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_generate_kid"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_validate_kid": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_validate_kid"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_generate_ehf": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_generate_ehf"),
                cacheable=False,
                admin_only=True,
                mutation=False,
            ),
            "economy_validate_contract": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_validate_contract"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_get_gl_records": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_get_gl_records"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "economy_reconcile_agreements": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_reconcile_agreements"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "economy_generate_billing_run": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_generate_billing_run"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "economy_propose_customer_invoice": ToolSpec(
                _h(economy_mcp_handlers, "handle_economy_propose_customer_invoice"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import economy as economy_handlers

        routes = [
            Route(
                "/api/economy/match-invoice",
                endpoint=economy_handlers.api_economy_match_invoice,
                methods=["POST"],
            ),
            Route(
                "/api/economy/periodisering",
                endpoint=economy_handlers.api_economy_periodisering,
                methods=["POST"],
            ),
            Route(
                "/api/economy/emit-event",
                endpoint=economy_handlers.api_economy_emit_event,
                methods=["POST"],
            ),
            Route(
                "/api/economy/forecast",
                endpoint=economy_handlers.api_economy_forecast,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/economy/mrr-arr-churn",
                endpoint=economy_handlers.api_economy_mrr_arr_churn,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/economy/dunning",
                endpoint=economy_handlers.api_economy_dunning,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/economy/recognition-schedule",
                endpoint=economy_handlers.api_economy_recognition_schedule,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/economy/gl-sync-status",
                endpoint=economy_handlers.api_economy_gl_sync_status,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/economy/close-narrative",
                endpoint=economy_handlers.api_economy_close_narrative,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/economy/kid/generate",
                endpoint=economy_handlers.api_economy_generate_kid,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/economy/kid/validate",
                endpoint=economy_handlers.api_economy_validate_kid,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/economy/ehf/generate",
                endpoint=economy_handlers.api_economy_generate_ehf,
                methods=["POST"],
            ),
            Route(
                "/api/economy/contracts/validate",
                endpoint=economy_handlers.api_economy_validate_contract,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class FieldTechPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "field_tech"
    TENANT_RLS_TABLES: tuple[str, ...] = ("work_orders", "checklists", "time_entries")

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.field_tech import mcp_handlers as field_tech_mcp_handlers

        tools = {
            "field_tech_dispatch": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_dispatch"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "field_tech_partner_view": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_partner_view"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "field_tech_create_work_order": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_create_work_order"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "field_tech_assign": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_assign"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "field_tech_complete_checklist": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_complete_checklist"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "field_tech_scan_serial": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_scan_serial"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "field_tech_log_time": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_log_time"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "field_tech_attach_photo": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_attach_photo"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "field_tech_sync": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_sync"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "field_tech_record_outcome": ToolSpec(
                _h(field_tech_mcp_handlers, "handle_field_tech_record_outcome"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import field_tech as field_tech_handlers

        routes = [
            Route(
                "/api/field-tech/dispatch",
                endpoint=field_tech_handlers.api_field_tech_dispatch,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/work-orders",
                endpoint=field_tech_handlers.api_field_tech_create_work_order,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/work-orders",
                endpoint=field_tech_handlers.api_field_tech_query_work_orders,
                methods=["GET"],
            ),
            Route(
                "/api/field-tech/work-orders/{id}",
                endpoint=field_tech_handlers.api_field_tech_work_order,
                methods=["GET"],
            ),
            Route(
                "/api/field-tech/work-orders/{id}/assign",
                endpoint=field_tech_handlers.api_field_tech_assign,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/checklists",
                endpoint=field_tech_handlers.api_field_tech_complete_checklist,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/scans",
                endpoint=field_tech_handlers.api_field_tech_scan_serial,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/time-entries",
                endpoint=field_tech_handlers.api_field_tech_log_time,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/time-entries/{id}/approve",
                endpoint=field_tech_handlers.api_field_tech_approve_time_entry,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/photos",
                endpoint=field_tech_handlers.api_field_tech_attach_photo,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/sync",
                endpoint=field_tech_handlers.api_field_tech_sync,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/outcomes",
                endpoint=field_tech_handlers.api_field_tech_record_outcome,
                methods=["POST"],
            ),
            Route(
                "/api/field-tech/partner-view",
                endpoint=field_tech_handlers.api_field_tech_partner_view,
                methods=["GET"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        try:
            from nce_verticals.field_tech.work_orders import (
                register_field_tech_subscribers,
            )

            register_field_tech_subscribers()
        except Exception as exc:
            log.warning("Failed registering field_tech workers: %s", exc)

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        try:
            log.debug("Registered field_tech cognitive hooks")
        except Exception as exc:
            log.warning("Failed registering field_tech cognitive hooks: %s", exc)

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class GeodataPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "geodata"
    TENANT_RLS_TABLES: tuple[str, ...] = ()
    GLOBAL_TABLES: frozenset[str] = frozenset(
        {"geodata_osm_elements", "geodata_n50_land_cover", "geodata_place_names"}
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.geodata import mcp_handlers as geodata_mcp_handlers

        tools = {
            "geodata_import_osm_elements": ToolSpec(
                _h(geodata_mcp_handlers, "handle_geodata_import_osm_elements"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "geodata_query_osm_elements": ToolSpec(
                _h(geodata_mcp_handlers, "handle_geodata_query_osm_elements"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "geodata_import_n50_land_cover": ToolSpec(
                _h(geodata_mcp_handlers, "handle_geodata_import_n50_land_cover"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "geodata_query_n50_land_cover": ToolSpec(
                _h(geodata_mcp_handlers, "handle_geodata_query_n50_land_cover"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "geodata_import_place_names": ToolSpec(
                _h(geodata_mcp_handlers, "handle_geodata_import_place_names"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "geodata_query_nearest_place_name": ToolSpec(
                _h(geodata_mcp_handlers, "handle_geodata_query_nearest_place_name"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "geodata_get_weather": ToolSpec(
                _h(geodata_mcp_handlers, "handle_geodata_get_weather"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        pass

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class HRPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "hr"
    TENANT_RLS_TABLES: tuple[str, ...] = ("employees", "skills", "certifications", "absences")

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.hr import mcp_handlers as hr_mcp_handlers

        tools = {
            "hr_get_employee": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_get_employee"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "hr_match_skills": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_match_skills"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "hr_capacity": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_capacity"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "hr_cert_status": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_cert_status"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "hr_register_absence": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_register_absence"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "hr_build_onboarding_quest": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_build_onboarding_quest"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "hr_log_one_on_one": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_log_one_on_one"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "hr_coach": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_coach"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "hr_record_skill": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_record_skill"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "hr_query_absences": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_query_absences"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "hr_compliance_deadlines": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_compliance_deadlines"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "hr_update_absence_compliance": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_update_absence_compliance"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "hr_get_onboarding_progress": ToolSpec(
                _h(hr_mcp_handlers, "handle_hr_get_onboarding_progress"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import hr as hr_handlers

        routes = [
            Route(
                "/api/hr/employees",
                endpoint=hr_handlers.api_hr_employees,
                methods=["GET"],
            ),
            Route(
                "/api/hr/employees",
                endpoint=hr_handlers.api_hr_create_employee,
                methods=["POST"],
            ),
            Route(
                "/api/hr/employees/{id}",
                endpoint=hr_handlers.api_hr_employee,
                methods=["GET"],
            ),
            Route(
                "/api/hr/match-skills",
                endpoint=hr_handlers.api_hr_match_skills,
                methods=["POST"],
            ),
            Route(
                "/api/hr/capacity",
                endpoint=hr_handlers.api_hr_capacity,
                methods=["GET"],
            ),
            Route(
                "/api/hr/cert-status",
                endpoint=hr_handlers.api_hr_cert_status,
                methods=["GET"],
            ),
            Route(
                "/api/hr/absences",
                endpoint=hr_handlers.api_hr_register_absence,
                methods=["POST"],
            ),
            Route(
                "/api/hr/onboarding/{id}",
                endpoint=hr_handlers.api_hr_onboarding_get,
                methods=["GET"],
            ),
            Route(
                "/api/hr/onboarding/{id}",
                endpoint=hr_handlers.api_hr_onboarding_build,
                methods=["POST"],
            ),
            Route(
                "/api/hr/coach",
                endpoint=hr_handlers.api_hr_coach,
                methods=["POST"],
            ),
            Route(
                "/api/hr/sync/status",
                endpoint=hr_handlers.api_hr_sync_status,
                methods=["GET"],
            ),
            Route(
                "/api/hr/sync/now",
                endpoint=hr_handlers.api_hr_sync_now,
                methods=["POST"],
            ),
            Route(
                "/api/hr/skills",
                endpoint=hr_handlers.api_hr_record_skill,
                methods=["POST"],
            ),
            Route(
                "/api/hr/absences",
                endpoint=hr_handlers.api_hr_absences,
                methods=["GET"],
            ),
            Route(
                "/api/hr/compliance/deadlines",
                endpoint=hr_handlers.api_hr_compliance_deadlines,
                methods=["GET"],
            ),
            Route(
                "/api/hr/compliance/milestones",
                endpoint=hr_handlers.api_hr_update_absence_compliance,
                methods=["POST"],
            ),
            Route(
                "/api/hr/onboarding/{id}/progress",
                endpoint=hr_handlers.api_hr_onboarding_progress,
                methods=["GET"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        try:
            from nce_verticals.hr.compliance import register_hr_compliance_subscribers

            register_hr_compliance_subscribers()
        except Exception as exc:
            log.warning("Failed registering hr workers: %s", exc)

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class InventoryPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "inventory"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "stock_locations",
        "inventory_items",
        "inventory_transactions",
        "goods_receipts",
        "inventory_rma",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.inventory import mcp_handlers as inventory_mcp_handlers

        tools = {
            "inventory_stock_levels": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_stock_levels"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "inventory_transfer_stock": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_transfer_stock"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_record_consumption": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_record_consumption"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_record_goods_receipt": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_record_goods_receipt"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_recommend_restock": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_recommend_restock"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "inventory_forecast_demand": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_forecast_demand"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "inventory_reserve_stock": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_reserve_stock"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_release_stock": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_release_stock"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_reserve_kit": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_reserve_kit"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_release_kit": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_release_kit"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_record_rma": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_record_rma"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_valuation": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_valuation"),
                cacheable=False,
                admin_only=True,
                mutation=False,
            ),
            "inventory_record_goods_receipt_and_match": ToolSpec(
                _h(
                    inventory_mcp_handlers,
                    "handle_inventory_record_goods_receipt_and_match",
                ),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_reconcile_dead_stock": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_reconcile_dead_stock"),
                cacheable=False,
                admin_only=True,
                mutation=False,
            ),
            "inventory_restock_from_rma": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_restock_from_rma"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_dispose_rma_weee": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_dispose_rma_weee"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "inventory_create_restock_po": ToolSpec(
                _h(inventory_mcp_handlers, "handle_inventory_create_restock_po"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import inventory as inventory_handlers

        routes = [
            Route(
                "/api/inventory/stock-levels",
                endpoint=inventory_handlers.api_inventory_stock_levels,
                methods=["GET"],
            ),
            Route(
                "/api/inventory/transfer-stock",
                endpoint=inventory_handlers.api_inventory_transfer_stock,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/record-consumption",
                endpoint=inventory_handlers.api_inventory_record_consumption,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/record-goods-receipt",
                endpoint=inventory_handlers.api_inventory_record_goods_receipt,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/recommend-restock",
                endpoint=inventory_handlers.api_inventory_recommend_restock,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/forecast-demand",
                endpoint=inventory_handlers.api_inventory_forecast_demand,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/reserve-stock",
                endpoint=inventory_handlers.api_inventory_reserve_stock,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/release-stock",
                endpoint=inventory_handlers.api_inventory_release_stock,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/reserve-kit",
                endpoint=inventory_handlers.api_inventory_reserve_kit,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/release-kit",
                endpoint=inventory_handlers.api_inventory_release_kit,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/record-rma",
                endpoint=inventory_handlers.api_inventory_record_rma,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/valuation",
                endpoint=inventory_handlers.api_inventory_valuation,
                methods=["GET"],
            ),
            Route(
                "/api/inventory/record-goods-receipt-and-match",
                endpoint=inventory_handlers.api_inventory_record_goods_receipt_and_match,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/reconcile-dead-stock",
                endpoint=inventory_handlers.api_inventory_reconcile_dead_stock,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/restock-from-rma",
                endpoint=inventory_handlers.api_inventory_restock_from_rma,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/dispose-rma-weee",
                endpoint=inventory_handlers.api_inventory_dispose_rma_weee,
                methods=["POST"],
            ),
            Route(
                "/api/inventory/create-restock-po",
                endpoint=inventory_handlers.api_inventory_create_restock_po,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class LegalEntitiesPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "legal_entities"
    TENANT_RLS_TABLES: tuple[str, ...] = ("legal_entities",)

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.legal_entities import (
            mcp_handlers as legal_entities_mcp_handlers,
        )

        tools = {
            "legal_entities_enrich_from_registry": ToolSpec(
                _h(
                    legal_entities_mcp_handlers,
                    "handle_legal_entities_enrich_from_registry",
                ),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        pass

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class MarketingPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "marketing"
    TENANT_RLS_TABLES: tuple[str, ...] = ("case_studies", "testimonials", "content_assets")

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.marketing import mcp_handlers as marketing_mcp_handlers

        tools = {
            "marketing_find_case_study_candidates": ToolSpec(
                _h(
                    marketing_mcp_handlers,
                    "handle_marketing_find_case_study_candidates",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "marketing_draft_case_study": ToolSpec(
                _h(marketing_mcp_handlers, "handle_marketing_draft_case_study"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "marketing_request_testimonial": ToolSpec(
                _h(marketing_mcp_handlers, "handle_marketing_request_testimonial"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "marketing_capture_testimonial": ToolSpec(
                _h(marketing_mcp_handlers, "handle_marketing_capture_testimonial"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "marketing_suggest_content": ToolSpec(
                _h(marketing_mcp_handlers, "handle_marketing_suggest_content"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "marketing_audit_seo": ToolSpec(
                _h(marketing_mcp_handlers, "handle_marketing_audit_seo"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "marketing_approve_content": ToolSpec(
                _h(marketing_mcp_handlers, "handle_marketing_approve_content"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "marketing_publish_content": ToolSpec(
                _h(marketing_mcp_handlers, "handle_marketing_publish_content"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "marketing_retract_testimonial": ToolSpec(
                _h(marketing_mcp_handlers, "handle_marketing_retract_testimonial"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import marketing as marketing_handlers

        routes = [
            Route(
                "/api/marketing/candidates",
                endpoint=marketing_handlers.api_marketing_candidates,
                methods=["GET"],
            ),
            Route(
                "/api/marketing/draft",
                endpoint=marketing_handlers.api_marketing_draft_case_study,
                methods=["POST"],
            ),
            Route(
                "/api/marketing/testimonials",
                endpoint=marketing_handlers.api_marketing_testimonials,
                methods=["GET"],
            ),
            Route(
                "/api/marketing/testimonials/capture",
                endpoint=marketing_handlers.api_marketing_capture_testimonial,
                methods=["POST"],
            ),
            Route(
                "/api/marketing/testimonials/retract",
                endpoint=marketing_handlers.api_marketing_retract_testimonial,
                methods=["POST"],
            ),
            Route(
                "/api/marketing/suggest-content",
                endpoint=marketing_handlers.api_marketing_suggest_content,
                methods=["POST"],
            ),
            Route(
                "/api/marketing/audit-seo",
                endpoint=marketing_handlers.api_marketing_audit_seo,
                methods=["POST"],
            ),
            Route(
                "/api/marketing/approve",
                endpoint=marketing_handlers.api_marketing_approve_content,
                methods=["POST"],
            ),
            Route(
                "/api/marketing/assets",
                endpoint=marketing_handlers.api_marketing_assets,
                methods=["GET"],
            ),
            Route(
                "/api/marketing/publish",
                endpoint=marketing_handlers.api_marketing_publish_content,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class NetboxPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "netbox"
    TENANT_RLS_TABLES: tuple[str, ...] = ("d365_netbox_mappings",)

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.netbox import circuits as netbox_circuits

        tools = {
            "evaluate_circuit_impact": ToolSpec(
                _h(netbox_circuits, "handle_evaluate_circuit_impact"),
                cacheable=False,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        pass

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class NotificationsPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "notifications"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "notifications",
        "reminders",
        "notification_subscriptions",
    )

    def register_tools(self, registry: Any) -> None:
        pass

    def register_routes(self, app: Any) -> None:
        pass

    def register_workers(self, worker_registry: Any) -> None:
        try:
            from nce_verticals.notifications.subscribers import (
                register_notifications_subscribers,
            )

            register_notifications_subscribers()
        except Exception as exc:
            log.warning("Failed registering notifications workers: %s", exc)

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class ProcurementPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "procurement"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "procurement_bid_prices",
        "procurement_po_lines",
        "procurement_deal_registrations",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.procurement import mcp_handlers as procurement_mcp_handlers

        tools = {
            "procurement_aggregate_savings": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_aggregate_savings"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "procurement_resolve_bids": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_resolve_bids"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "procurement_calculate_tco": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_calculate_tco"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "procurement_rank_suppliers": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_rank_suppliers"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "procurement_evaluate_match": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_evaluate_match"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "procurement_forecast_rebate": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_forecast_rebate"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "procurement_recommend_move_spend": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_recommend_move_spend"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "procurement_whatif_spend": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_whatif_spend"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "procurement_generate_po": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_generate_po"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "procurement_submit_po": ToolSpec(
                _h(procurement_mcp_handlers, "handle_procurement_submit_po"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import procurement as procurement_handlers

        routes = [
            Route(
                "/api/procurement/savings",
                endpoint=procurement_handlers.api_procurement_aggregate_savings,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/procurement/bids/resolve",
                endpoint=procurement_handlers.api_procurement_resolve_bids,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/procurement/tco",
                endpoint=procurement_handlers.api_procurement_calculate_tco,
                methods=["POST"],
            ),
            Route(
                "/api/procurement/rank",
                endpoint=procurement_handlers.api_procurement_rank_suppliers,
                methods=["POST"],
            ),
            Route(
                "/api/procurement/match",
                endpoint=procurement_handlers.api_procurement_evaluate_match,
                methods=["POST"],
            ),
            Route(
                "/api/procurement/sync",
                endpoint=procurement_handlers.api_procurement_sync_now,
                methods=["POST"],
            ),
            Route(
                "/api/procurement/sync/status",
                endpoint=procurement_handlers.api_procurement_sync_status,
                methods=["GET"],
            ),
            Route(
                "/api/procurement/frontier/forecast-rebate",
                endpoint=procurement_handlers.api_procurement_forecast_rebate,
                methods=["POST"],
            ),
            Route(
                "/api/procurement/frontier/recommend-move-spend",
                endpoint=procurement_handlers.api_procurement_recommend_move_spend,
                methods=["POST"],
            ),
            Route(
                "/api/procurement/frontier/whatif-spend",
                endpoint=procurement_handlers.api_procurement_whatif_spend,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        try:
            log.debug("Registered procurement cognitive hooks")
        except Exception as exc:
            log.warning("Failed registering procurement cognitive hooks: %s", exc)

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class ProductPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "product"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "product_prices",
        "product_match_feedback",
        "product_enrichment_log",
        "product_packages",
    )
    GLOBAL_TABLES: frozenset[str] = frozenset({"product_catalog", "pricing_fx_rates"})

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.product import mcp_handlers as product_mcp_handlers

        tools = {
            "product_search": ToolSpec(
                _h(product_mcp_handlers, "handle_product_search"),
                cacheable=True,
            ),
            "product_get": ToolSpec(
                _h(product_mcp_handlers, "handle_product_get"),
                cacheable=True,
            ),
            "product_price": ToolSpec(
                _h(product_mcp_handlers, "handle_product_price"),
                cacheable=True,
            ),
            "product_related": ToolSpec(
                _h(product_mcp_handlers, "handle_product_related"),
                cacheable=True,
            ),
            "product_match_bom_line": ToolSpec(
                _h(product_mcp_handlers, "handle_product_match_bom_line"),
                cacheable=False,
                mutation=False,
                admin_only=False,
            ),
            "product_enrich": ToolSpec(
                _h(product_mcp_handlers, "handle_product_enrich"),
                mutation=True,
                cacheable=False,
                admin_only=False,
            ),
            "product_ingest_spec": ToolSpec(
                _h(product_mcp_handlers, "handle_product_ingest_spec"),
                mutation=True,
                cacheable=False,
                admin_only=False,
            ),
            "product_golden_record": ToolSpec(
                _h(product_mcp_handlers, "handle_product_golden_record"),
                cacheable=True,
                mutation=False,
                admin_only=False,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import product as product_handlers

        routes = [
            Route(
                "/api/product/search",
                endpoint=product_handlers.api_product_search,
                methods=["GET"],
            ),
            Route(
                "/api/product/enrichment/review",
                endpoint=product_handlers.api_product_enrichment_review,
                methods=["GET"],
            ),
            Route(
                "/api/product/quality",
                endpoint=product_handlers.api_product_quality,
                methods=["GET"],
            ),
            Route(
                "/api/product/{id}",
                endpoint=product_handlers.api_product_get,
                methods=["GET"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class ProjectPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "project"
    TENANT_RLS_TABLES: tuple[str, ...] = ()

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.project import mcp_handlers as project_mcp_handlers

        tools = {
            "project_can_enter_phase": ToolSpec(
                _h(project_mcp_handlers, "handle_project_can_enter_phase"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "project_convert_signed_quote": ToolSpec(
                _h(project_mcp_handlers, "handle_project_convert_signed_quote"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "project_advance_phase": ToolSpec(
                _h(project_mcp_handlers, "handle_project_advance_phase"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "project_suggest_pl": ToolSpec(
                _h(project_mcp_handlers, "handle_project_suggest_pl"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "project_record_outcome": ToolSpec(
                _h(project_mcp_handlers, "handle_project_record_outcome"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "project_generate_case_study_edge": ToolSpec(
                _h(project_mcp_handlers, "handle_project_generate_case_study_edge"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "project_recall_similar": ToolSpec(
                _h(project_mcp_handlers, "handle_project_recall_similar"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "project_my_day": ToolSpec(
                _h(project_mcp_handlers, "handle_project_my_day"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "project_capacity": ToolSpec(
                _h(project_mcp_handlers, "handle_project_capacity"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "project_detect_scope_creep": ToolSpec(
                _h(project_mcp_handlers, "handle_project_detect_scope_creep"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "project_status_report": ToolSpec(
                _h(project_mcp_handlers, "handle_project_status_report"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import project as project_handlers

        routes = [
            Route(
                "/api/project/convert-signed-quote",
                endpoint=project_handlers.api_project_convert_signed_quote,
                methods=["POST"],
            ),
            Route(
                "/api/project/similar",
                endpoint=project_handlers.api_project_recall_similar,
                methods=["GET", "POST"],
            ),
            Route(
                "/api/project/{id}/similar",
                endpoint=project_handlers.api_project_recall_similar,
                methods=["GET"],
            ),
            Route(
                "/api/project/{id}/phase",
                endpoint=project_handlers.api_project_get_phase,
                methods=["GET"],
            ),
            Route(
                "/api/project/{id}/bom-lines",
                endpoint=project_handlers.api_project_get_bom_lines,
                methods=["GET"],
            ),
            Route(
                "/api/project/{id}/phase",
                endpoint=project_handlers.api_project_advance_phase,
                methods=["POST"],
            ),
            Route(
                "/api/project/my-day",
                endpoint=project_handlers.api_admin_project_my_day,
                methods=["GET"],
            ),
            Route(
                "/api/project/capacity",
                endpoint=project_handlers.api_admin_project_capacity,
                methods=["GET"],
            ),
            Route(
                "/api/project/{id}/scope-creep",
                endpoint=project_handlers.api_admin_project_scope_creep,
                methods=["GET"],
            ),
            Route(
                "/api/project/{id}/status-report",
                endpoint=project_handlers.api_admin_project_status_report,
                methods=["GET"],
            ),
            Route(
                "/api/project/{id}/case-study",
                endpoint=project_handlers.api_project_generate_case_study,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        try:
            from nce_verticals.project import (
                automation as project_automation,
            )
            from nce_verticals.project import (
                tasks as project_tasks,
            )

            if worker_registry is not None:
                try:
                    project_tasks.register_engine(worker_registry)
                    project_automation.register_engine(worker_registry)
                except Exception:
                    pass
            project_tasks.register_bom_task_subscriber()
            project_automation.register_automation_subscribers()
        except Exception as exc:
            log.warning("Failed registering project workers: %s", exc)

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class ResourcesPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "resources"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "resources",
        "allocations",
        "travel_legs",
        "stays",
        "per_diems",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.resources import mcp_handlers as resources_mcp_handlers

        tools = {
            "resources_resolve_capacity": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_resolve_capacity"),
                cacheable=True,
            ),
            "resources_plan_allocation": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_plan_allocation"),
                cacheable=False,
            ),
            "resources_detect_conflicts": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_detect_conflicts"),
                cacheable=True,
            ),
            "resources_forecast_demand": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_forecast_demand"),
                cacheable=True,
            ),
            "resources_field_schedule": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_field_schedule"),
                cacheable=True,
            ),
            "resources_reserve": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_reserve"),
                cacheable=False,
                mutation=True,
            ),
            "resources_release": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_release"),
                cacheable=False,
                mutation=True,
            ),
            "resources_plan_material_flow": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_plan_material_flow"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "resources_plan_travel": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_plan_travel"),
                cacheable=False,
                mutation=True,
            ),
            "resources_record_allocation_outcome": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_record_allocation_outcome"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "resources_create": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_create"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "resources_update": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_update"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "resources_get_resource": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_get_resource"),
                cacheable=True,
            ),
            "resources_list_resources": ToolSpec(
                _h(resources_mcp_handlers, "handle_resources_list_resources"),
                cacheable=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import resources as resources_handlers

        routes = [
            Route(
                "/api/resources/capacity",
                endpoint=resources_handlers.api_resources_resolve_capacity,
                methods=["GET"],
            ),
            Route(
                "/api/resources/plan-allocation",
                endpoint=resources_handlers.api_resources_plan_allocation,
                methods=["POST"],
            ),
            Route(
                "/api/resources/reserve",
                endpoint=resources_handlers.api_resources_reserve,
                methods=["POST"],
            ),
            Route(
                "/api/resources/release",
                endpoint=resources_handlers.api_resources_release,
                methods=["POST"],
            ),
            Route(
                "/api/resources/conflicts",
                endpoint=resources_handlers.api_resources_detect_conflicts,
                methods=["GET"],
            ),
            Route(
                "/api/resources/material-flow",
                endpoint=resources_handlers.api_resources_plan_material_flow,
                methods=["POST"],
            ),
            Route(
                "/api/resources/travel",
                endpoint=resources_handlers.api_resources_plan_travel,
                methods=["POST"],
            ),
            Route(
                "/api/resources/field-schedule",
                endpoint=resources_handlers.api_resources_field_schedule,
                methods=["GET"],
            ),
            Route(
                "/api/resources/forecast",
                endpoint=resources_handlers.api_resources_forecast_demand,
                methods=["GET"],
            ),
            Route(
                "/api/resources/pulse",
                endpoint=resources_handlers.api_resources_capacity_pulse,
                methods=["GET"],
            ),
            Route(
                "/api/resources",
                endpoint=resources_handlers.api_resources_list,
                methods=["GET"],
            ),
            Route(
                "/api/resources",
                endpoint=resources_handlers.api_resources_create,
                methods=["POST"],
            ),
            Route(
                "/api/resources/{id}",
                endpoint=resources_handlers.api_resources_get,
                methods=["GET"],
            ),
            Route(
                "/api/resources/{id}",
                endpoint=resources_handlers.api_resources_update,
                methods=["POST", "PATCH"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        try:
            from nce_verticals.resources import watcher as resources_watcher

            if worker_registry is not None:
                try:
                    resources_watcher.register_engine(worker_registry)
                except Exception:
                    pass
            resources_watcher.register_resources_event_subscribers()
        except Exception as exc:
            log.warning("Failed registering resources workers: %s", exc)

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class SalesPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "sales"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "sales_read_model",
        "sales_targets",
        "sales_signed_baselines",
        "sales_customers",
        "sales_leads",
        "sales_deals",
        "sales_quotes",
        "sales_contacts",
        "sales_quote_templates",
        "sales_deal_participants",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.sales import mcp_handlers as sales_mcp_handlers

        tools = {
            "sales_ping": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_ping"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "sales_get_signed_baseline": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_get_signed_baseline"),
                cacheable=False,
                admin_only=False,
                mutation=False,
            ),
            "sales_get_quote_lines": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_get_quote_lines"),
                cacheable=False,
                admin_only=False,
                mutation=False,
            ),
            "sales_add_quote_line": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_add_quote_line"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "sales_import_quote_lines": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_import_quote_lines"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "sales_clone_quote": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_clone_quote"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "sales_request_signature": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_request_signature"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "sales_create_customer": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_create_customer"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "sales_create_lead": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_create_lead"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "sales_create_deal": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_create_deal"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "sales_edit_deal": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_edit_deal"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "sales_calculate_commission": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_calculate_commission"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "sales_divergence_log": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_divergence_log"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "sales_morning_brief_slice": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_morning_brief_slice"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "sales_score_lead": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_score_lead"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "sales_draft_quote": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_draft_quote"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "sales_open_dealroom": ToolSpec(
                _h(sales_mcp_handlers, "handle_sales_open_dealroom"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import sales as sales_handlers
        from nce_verticals.admin_handlers import sales_public as sales_public_handlers
        from nce_verticals.admin_handlers import source_mode as source_mode_handlers

        routes = [
            Route(
                "/public-api/sales/quotes/{id}",
                endpoint=sales_public_handlers.api_sales_quote_public,
                methods=["GET"],
            ),
            Route(
                "/api/admin/source-mode",
                endpoint=source_mode_handlers.api_source_mode_get,
                methods=["GET"],
            ),
            Route(
                "/api/admin/source-mode",
                endpoint=source_mode_handlers.api_source_mode_put,
                methods=["PUT"],
            ),
            Route(
                "/api/admin/sales/source-mode",
                endpoint=sales_handlers.api_sales_source_mode_get,
                methods=["GET"],
            ),
            Route(
                "/api/admin/sales/source-mode",
                endpoint=sales_handlers.api_sales_source_mode_put,
                methods=["PUT"],
            ),
            Route(
                "/api/sales/customers",
                endpoint=sales_handlers.api_admin_sales_customers,
                methods=["GET"],
            ),
            Route(
                "/api/sales/customers/{id}",
                endpoint=sales_handlers.api_admin_sales_customer_profile,
                methods=["GET"],
            ),
            Route(
                "/api/sales/overview",
                endpoint=sales_handlers.api_admin_sales_overview,
                methods=["GET"],
            ),
            Route(
                "/api/sales/seller-detail/{user}",
                endpoint=sales_handlers.api_admin_sales_seller_detail,
                methods=["GET"],
            ),
            Route(
                "/api/sales/dashboard",
                endpoint=sales_handlers.api_admin_sales_dashboard,
                methods=["GET"],
            ),
            Route(
                "/api/sales/stats",
                endpoint=sales_handlers.api_admin_sales_stats,
                methods=["GET"],
            ),
            Route(
                "/api/sales/manager",
                endpoint=sales_handlers.api_admin_sales_manager,
                methods=["GET"],
            ),
            Route(
                "/api/sales/agreements",
                endpoint=sales_handlers.api_admin_sales_agreements,
                methods=["GET"],
            ),
            Route(
                "/api/sales/agreements/{id}",
                endpoint=sales_handlers.api_admin_sales_agreement_detail,
                methods=["GET"],
            ),
            Route(
                "/api/sales/quotes/{id}",
                endpoint=sales_handlers.api_admin_sales_quote_detail,
                methods=["GET"],
            ),
            Route(
                "/api/sales/targets",
                endpoint=sales_handlers.api_admin_sales_targets_get,
                methods=["GET"],
            ),
            Route(
                "/api/sales/targets",
                endpoint=sales_handlers.api_admin_sales_targets_put,
                methods=["PUT"],
            ),
            Route(
                "/api/sales/customers",
                endpoint=sales_handlers.api_admin_sales_create_customer,
                methods=["POST"],
            ),
            Route(
                "/api/sales/leads",
                endpoint=sales_handlers.api_admin_sales_create_lead,
                methods=["POST"],
            ),
            Route(
                "/api/sales/deals",
                endpoint=sales_handlers.api_admin_sales_create_deal,
                methods=["POST"],
            ),
            Route(
                "/api/sales/deals/edit",
                endpoint=sales_handlers.api_admin_sales_edit_deal,
                methods=["POST"],
            ),
            Route(
                "/api/sales/commission",
                endpoint=sales_handlers.api_admin_sales_calculate_commission,
                methods=["GET"],
            ),
            Route(
                "/api/sales/divergences",
                endpoint=sales_handlers.api_admin_sales_divergences,
                methods=["GET"],
            ),
            Route(
                "/api/sales/morning-brief",
                endpoint=sales_handlers.api_admin_sales_morning_brief_slice,
                methods=["GET"],
            ),
            Route(
                "/api/sales/lead-score",
                endpoint=sales_handlers.api_admin_sales_lead_score,
                methods=["POST"],
            ),
            Route(
                "/api/sales/quote-draft",
                endpoint=sales_handlers.api_admin_sales_quote_draft,
                methods=["POST"],
            ),
            Route(
                "/api/sales/dealroom",
                endpoint=sales_handlers.api_admin_sales_dealroom,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class SitesPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "sites"
    TENANT_RLS_TABLES: tuple[str, ...] = ("sites",)

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.sites import mcp_handlers as sites_mcp_handlers

        tools = {
            "sites_enrich_address_from_registry": ToolSpec(
                _h(sites_mcp_handlers, "handle_sites_enrich_address_from_registry"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        pass

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class SupportPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "support"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "service_tickets",
        "sla_clocks",
        "customer_health",
        "support_ticket_actions",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.support import mcp_handlers as support_mcp_handlers

        tools = {
            "support_query_ticket": ToolSpec(
                _h(support_mcp_handlers, "handle_support_query_ticket"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "support_open_ticket": ToolSpec(
                _h(support_mcp_handlers, "handle_support_open_ticket"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "support_sla_clock": ToolSpec(
                _h(support_mcp_handlers, "handle_support_sla_clock"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "support_health_score": ToolSpec(
                _h(support_mcp_handlers, "handle_support_health_score"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "support_troubleshoot": ToolSpec(
                _h(support_mcp_handlers, "handle_support_troubleshoot"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "support_resolve_ticket": ToolSpec(
                _h(support_mcp_handlers, "handle_support_resolve_ticket"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "support_triage_ticket": ToolSpec(
                _h(support_mcp_handlers, "handle_support_triage_ticket"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "support_record_touchpoint": ToolSpec(
                _h(support_mcp_handlers, "handle_support_record_touchpoint"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "support_dispatch_work_order": ToolSpec(
                _h(support_mcp_handlers, "handle_support_dispatch_work_order"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "support_sync_now": ToolSpec(
                _h(support_mcp_handlers, "handle_support_sync_now"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "support_failure_pattern": ToolSpec(
                _h(support_mcp_handlers, "handle_support_failure_pattern"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "support_upsell_signal": ToolSpec(
                _h(support_mcp_handlers, "handle_support_upsell_signal"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "support_at_risk_aggregate": ToolSpec(
                _h(support_mcp_handlers, "handle_support_at_risk_aggregate"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "support_log_ticket_action": ToolSpec(
                _h(support_mcp_handlers, "handle_support_log_ticket_action"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "support_ticket_timeline": ToolSpec(
                _h(support_mcp_handlers, "handle_support_ticket_timeline"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "support_get_on_call": ToolSpec(
                _h(support_mcp_handlers, "handle_support_get_on_call"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "support_summarise_ticket": ToolSpec(
                _h(support_mcp_handlers, "handle_support_summarise_ticket"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "support_get_ticket_links": ToolSpec(
                _h(support_mcp_handlers, "handle_support_get_ticket_links"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "support_link_ticket": ToolSpec(
                _h(support_mcp_handlers, "handle_support_link_ticket"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import support as support_handlers

        routes = [
            Route(
                "/api/support/tickets",
                endpoint=support_handlers.api_support_tickets_list,
                methods=["GET"],
            ),
            Route(
                "/api/support/tickets",
                endpoint=support_handlers.api_support_tickets_open,
                methods=["POST"],
            ),
            Route(
                "/api/support/tickets/{id}",
                endpoint=support_handlers.api_support_tickets_get,
                methods=["GET"],
            ),
            Route(
                "/api/support/tickets/{id}/sla-clock",
                endpoint=support_handlers.api_support_ticket_sla_clock,
                methods=["GET"],
            ),
            Route(
                "/api/support/customers/{id}/health",
                endpoint=support_handlers.api_support_customer_health,
                methods=["GET"],
            ),
            Route(
                "/api/support/troubleshoot",
                endpoint=support_handlers.api_support_troubleshoot,
                methods=["POST"],
            ),
            Route(
                "/api/support/tickets/{id}/resolve",
                endpoint=support_handlers.api_support_tickets_resolve,
                methods=["POST"],
            ),
            Route(
                "/api/support/tickets/{id}/triage",
                endpoint=support_handlers.api_support_tickets_triage,
                methods=["POST"],
            ),
            Route(
                "/api/support/touchpoints",
                endpoint=support_handlers.api_support_touchpoints_record,
                methods=["POST"],
            ),
            Route(
                "/api/support/tickets/{id}/dispatch",
                endpoint=support_handlers.api_support_tickets_dispatch,
                methods=["POST"],
            ),
            Route(
                "/api/support/sync/now",
                endpoint=support_handlers.api_support_sync_now,
                methods=["POST"],
            ),
            Route(
                "/api/support/sync/status",
                endpoint=support_handlers.api_support_sync_status,
                methods=["GET"],
            ),
            Route(
                "/api/support/tickets/{id}/failure-pattern",
                endpoint=support_handlers.api_support_tickets_failure_pattern,
                methods=["POST"],
            ),
            Route(
                "/api/support/tickets/{id}/upsell-signal",
                endpoint=support_handlers.api_support_tickets_upsell_signal,
                methods=["POST"],
            ),
            Route(
                "/api/support/at-risk-aggregate",
                endpoint=support_handlers.api_support_at_risk_aggregate,
                methods=["GET"],
            ),
            Route(
                "/api/support/tickets/{id}/actions",
                endpoint=support_handlers.api_support_tickets_log_action,
                methods=["POST"],
            ),
            Route(
                "/api/support/tickets/{id}/timeline",
                endpoint=support_handlers.api_support_tickets_timeline,
                methods=["GET"],
            ),
            Route(
                "/api/support/on-call",
                endpoint=support_handlers.api_support_on_call,
                methods=["GET"],
            ),
            Route(
                "/api/support/tickets/{id}/summary",
                endpoint=support_handlers.api_support_ticket_summary,
                methods=["GET"],
            ),
            Route(
                "/api/support/tickets/{id}/links",
                endpoint=support_handlers.api_support_tickets_links,
                methods=["GET"],
            ),
            Route(
                "/api/support/tickets/{id}/links",
                endpoint=support_handlers.api_support_tickets_link,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class SystemDesignPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "system_design"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "system_design_device_capabilities",
        "system_design_geometry",
        "system_design_node_state",
        "system_design_design_requests",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.system_design import (
            mcp_handlers as system_design_mcp_handlers,
        )

        tools = {
            "system_design_ping": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_ping"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_publish_design_docs": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_publish_design_docs",
                ),
                mutation=True,
                cacheable=False,
                admin_only=False,
            ),
            "system_design_get_topology": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_topology"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_inspect_signal_flow": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_inspect_signal_flow",
                ),
                cacheable=False,
                admin_only=False,
                mutation=False,
            ),
            "system_design_procurement_view": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_procurement_view"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_author_topology": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_author_topology"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_author_functional_location": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_author_functional_location",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_validate_design_graph": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_validate_design_graph",
                ),
                cacheable=False,
                admin_only=False,
                mutation=False,
            ),
            "system_design_from_quote": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_from_quote"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_to_quote": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_to_quote"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_generate_sow": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_generate_sow"),
                cacheable=False,
                admin_only=False,
                mutation=False,
            ),
            "system_design_enrich_design_lines": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_enrich_design_lines",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_propose_design": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_propose_design"),
                cacheable=False,
                admin_only=False,
                mutation=False,
            ),
            "system_design_delete_planned": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_delete_planned"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "system_design_get_standards": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_standards"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_get_signal_rules": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_signal_rules"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_sync_device_capabilities": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_sync_device_capabilities",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_list_functional_locations": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_list_functional_locations",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_get_functional_location": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_get_functional_location",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_get_fl_children": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_fl_children"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_get_fl_ancestors": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_fl_ancestors"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_get_fl_path": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_fl_path"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_move_functional_location": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_move_functional_location",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_merge_functional_locations": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_merge_functional_locations",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_promote_functional_location": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_promote_functional_location",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_list_room_categories": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_list_room_categories",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_get_room_category": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_room_category"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_set_fl_room_category": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_set_fl_room_category",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_get_fl_room_category": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_get_fl_room_category",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_assign_fl_responsible": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_assign_fl_responsible",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_unassign_fl_responsible": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_unassign_fl_responsible",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_list_fl_responsible": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_list_fl_responsible",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_list_my_responsible_fls": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_list_my_responsible_fls",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_list_designs": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_list_designs"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_get_design": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_design"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_create_design": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_create_design"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_update_design": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_update_design"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_set_active_design": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_set_active_design"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_get_active_design": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_active_design"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_get_room_spec": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_get_room_spec"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_set_room_spec": ToolSpec(
                _h(system_design_mcp_handlers, "handle_system_design_set_room_spec"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_create_design_request": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_create_design_request",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_get_design_request": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_get_design_request",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_list_design_requests": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_list_design_requests",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "system_design_update_design_request": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_update_design_request",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_assign_design_request": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_assign_design_request",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_complete_design_request": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_complete_design_request",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "system_design_fulfill_request_from_quote": ToolSpec(
                _h(
                    system_design_mcp_handlers,
                    "handle_system_design_fulfill_request_from_quote",
                ),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import system_design as system_design_handlers

        routes = [
            Route(
                "/api/system-design/publish-design-docs",
                endpoint=system_design_handlers.api_system_design_publish_design_docs,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/topology",
                endpoint=system_design_handlers.api_system_design_get_topology,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/signal-flow",
                endpoint=system_design_handlers.api_system_design_inspect_signal_flow,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/procurement-view",
                endpoint=system_design_handlers.api_system_design_procurement_view,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/topology",
                endpoint=system_design_handlers.api_system_design_author_topology,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/functional-location",
                endpoint=system_design_handlers.api_system_design_author_functional_location,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/validate",
                endpoint=system_design_handlers.api_system_design_validate_design_graph,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/planned",
                endpoint=system_design_handlers.api_system_design_delete_planned,
                methods=["DELETE"],
            ),
            Route(
                "/api/system-design/from-quote",
                endpoint=system_design_handlers.api_system_design_from_quote,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/to-quote",
                endpoint=system_design_handlers.api_system_design_to_quote,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/sow",
                endpoint=system_design_handlers.api_system_design_generate_sow,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/enrich-design-lines",
                endpoint=system_design_handlers.api_system_design_enrich_design_lines,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/standards",
                endpoint=system_design_handlers.api_system_design_get_standards,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/signal-rules",
                endpoint=system_design_handlers.api_system_design_get_signal_rules,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/capabilities/sync",
                endpoint=system_design_handlers.api_system_design_sync_device_capabilities,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/room-categories",
                endpoint=system_design_handlers.api_system_design_list_room_categories,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/room-categories/{id}",
                endpoint=system_design_handlers.api_system_design_get_room_category,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations",
                endpoint=system_design_handlers.api_system_design_list_functional_locations,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations/my-responsible",
                endpoint=system_design_handlers.api_system_design_my_responsible_fls,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}",
                endpoint=system_design_handlers.api_system_design_get_functional_location,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/children",
                endpoint=system_design_handlers.api_system_design_get_fl_children,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/ancestors",
                endpoint=system_design_handlers.api_system_design_get_fl_ancestors,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/path",
                endpoint=system_design_handlers.api_system_design_get_fl_path,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/move",
                endpoint=system_design_handlers.api_system_design_move_functional_location,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/merge",
                endpoint=system_design_handlers.api_system_design_merge_functional_locations,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/promote",
                endpoint=system_design_handlers.api_system_design_promote_functional_location,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/room-category",
                endpoint=system_design_handlers.api_system_design_get_fl_room_category,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/room-category",
                endpoint=system_design_handlers.api_system_design_set_fl_room_category,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/responsible",
                endpoint=system_design_handlers.api_system_design_list_fl_responsible,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/responsible",
                endpoint=system_design_handlers.api_system_design_assign_fl_responsible,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/responsible/{employee_id}",
                endpoint=system_design_handlers.api_system_design_unassign_fl_responsible,
                methods=["DELETE"],
            ),
            Route(
                "/api/system-design/designs",
                endpoint=system_design_handlers.api_system_design_list_designs,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/designs",
                endpoint=system_design_handlers.api_system_design_create_design,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/designs/{id}",
                endpoint=system_design_handlers.api_system_design_get_design,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/designs/{id}",
                endpoint=system_design_handlers.api_system_design_update_design,
                methods=["PATCH"],
            ),
            Route(
                "/api/system-design/designs/{id}/set-active",
                endpoint=system_design_handlers.api_system_design_set_active_design,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/designs/{id}/room-spec",
                endpoint=system_design_handlers.api_system_design_get_room_spec,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/designs/{id}/room-spec",
                endpoint=system_design_handlers.api_system_design_set_room_spec,
                methods=["PUT"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/designs",
                endpoint=system_design_handlers.api_system_design_list_fl_designs,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/functional-locations/{id}/active-design",
                endpoint=system_design_handlers.api_system_design_get_fl_active_design,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/requests",
                endpoint=system_design_handlers.api_system_design_list_requests,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/requests",
                endpoint=system_design_handlers.api_system_design_create_request,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/requests/{id}",
                endpoint=system_design_handlers.api_system_design_get_request,
                methods=["GET"],
            ),
            Route(
                "/api/system-design/requests/{id}",
                endpoint=system_design_handlers.api_system_design_update_request,
                methods=["PATCH"],
            ),
            Route(
                "/api/system-design/requests/{id}/assign",
                endpoint=system_design_handlers.api_system_design_assign_request,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/requests/{id}/complete",
                endpoint=system_design_handlers.api_system_design_complete_request,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/requests/{id}/fulfill",
                endpoint=system_design_handlers.api_system_design_fulfill_request,
                methods=["POST"],
            ),
            Route(
                "/api/system-design/requests/{id}/cancel",
                endpoint=system_design_handlers.api_system_design_cancel_request,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        try:
            from nce_verticals.system_design.subscribers import (
                register_system_design_subscribers,
            )

            register_system_design_subscribers()
        except Exception as exc:
            log.warning("Failed registering system_design workers: %s", exc)

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        try:
            log.debug("Registered system_design cognitive hooks")
        except Exception as exc:
            log.warning("Failed registering system_design cognitive hooks: %s", exc)

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class VendorsPlugin(_EngineRLSPluginMixin):
    plugin_id: str = "vendors"
    TENANT_RLS_TABLES: tuple[str, ...] = ("vendor_scorecards", "contractor_profiles")

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.vendors import mcp_handlers as vendors_mcp_handlers

        tools = {
            "vendors_get_vendor": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_get_vendor"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "vendors_compute_scorecard": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_compute_scorecard"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "vendors_get_tier_status": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_get_tier_status"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "vendors_detect_reliability_degradation": ToolSpec(
                _h(
                    vendors_mcp_handlers,
                    "handle_vendors_detect_reliability_degradation",
                ),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "vendors_check_tier_at_risk": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_check_tier_at_risk"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "vendors_match_contractor": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_match_contractor"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "vendors_compute_performance": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_compute_performance"),
                cacheable=False,
                admin_only=False,
                mutation=True,
            ),
            "vendors_recall_similar_jobs": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_recall_similar_jobs"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "vendors_reliability_radar": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_reliability_radar"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "vendors_calibrate_weights": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_calibrate_weights"),
                cacheable=True,
                # Q-41 (ruled 2026-09-20, option 3): the function reads namespace-scoped
                # ledger data but writes one shared, un-namespaced weights file every
                # namespace's scorecard reads from -- so a tenant caller was silently
                # tuning every other tenant's vendor rankings. Ruling: not per-tenant
                # (that's a migration for a function with no named consumer), just
                # remove the tenant-triggered write by making calibration an operator
                # action. The shared model itself stays global by design.
                admin_only=True,
                mutation=False,
            ),
            "vendors_upsert_vendor": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_upsert_vendor"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "vendors_upsert_contractor": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_upsert_contractor"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
            "vendors_get_contractor": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_get_contractor"),
                cacheable=True,
                admin_only=False,
                mutation=False,
            ),
            "vendors_upsert_cert": ToolSpec(
                _h(vendors_mcp_handlers, "handle_vendors_upsert_cert"),
                cacheable=False,
                admin_only=True,
                mutation=True,
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import vendors as vendors_handlers

        routes = [
            Route(
                "/api/vendors/scorecard",
                endpoint=vendors_handlers.api_vendors_scorecard,
                methods=["GET"],
            ),
            Route(
                "/api/vendors/upsert",
                endpoint=vendors_handlers.api_vendors_upsert,
                methods=["POST"],
            ),
            Route(
                "/api/vendors/contractors/upsert",
                endpoint=vendors_handlers.api_vendors_upsert_contractor,
                methods=["POST"],
            ),
            Route(
                "/api/vendors/contractors/{id}",
                endpoint=vendors_handlers.api_vendors_get_contractor,
                methods=["GET"],
            ),
            Route(
                "/api/vendors/certs/upsert",
                endpoint=vendors_handlers.api_vendors_upsert_cert,
                methods=["POST"],
            ),
            Route(
                "/api/vendors/seed",
                endpoint=vendors_handlers.api_vendors_seed,
                methods=["POST"],
            ),
            Route(
                "/api/vendors/{id}",
                endpoint=vendors_handlers.api_vendors_get_vendor,
                methods=["GET"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class EntraIDPlugin(_EngineRLSPluginMixin):
    """Microsoft Entra ID Identification Point & Company Allowlist Gate Plugin."""

    plugin_id: str = "entra_id"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "entra_id_audit_log",
        "entra_id_configs",
        "entra_id_sessions",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.entra_id import mcp_handlers as entra_mcp_handlers

        tools = {
            "entra_whoami": ToolSpec(
                _h(entra_mcp_handlers, "handle_entra_whoami"),
                cacheable=False,
                admin_only=False,
                mutation=False,
                engine="entra_id",
            ),
            "entra_login_device_code": ToolSpec(
                _h(entra_mcp_handlers, "handle_entra_login_device_code"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="entra_id",
            ),
            "entra_complete_device_login": ToolSpec(
                _h(entra_mcp_handlers, "handle_entra_complete_device_login"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="entra_id",
            ),
            "entra_verify_access": ToolSpec(
                _h(entra_mcp_handlers, "handle_entra_verify_access"),
                cacheable=False,
                admin_only=False,
                mutation=False,
                engine="entra_id",
            ),
            "entra_logout": ToolSpec(
                _h(entra_mcp_handlers, "handle_entra_logout"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="entra_id",
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import entra_id as entra_handlers

        routes = [
            Route(
                "/api/admin/entra/config",
                endpoint=entra_handlers.api_admin_entra_config,
                methods=["GET"],
            ),
            Route(
                "/api/admin/entra/config",
                endpoint=entra_handlers.api_admin_entra_config_save,
                methods=["POST"],
            ),
            Route(
                "/api/admin/entra/sessions",
                endpoint=entra_handlers.api_admin_entra_sessions,
                methods=["GET"],
            ),
            Route(
                "/api/admin/entra/sessions/revoke",
                endpoint=entra_handlers.api_admin_entra_revoke_session,
                methods=["POST"],
            ),
            Route(
                "/api/admin/entra/verify-user",
                endpoint=entra_handlers.api_admin_entra_verify_user,
                methods=["POST"],
            ),
            Route(
                "/api/admin/entra/audit",
                endpoint=entra_handlers.api_admin_entra_audit,
                methods=["GET"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class SalesforcePlugin(_EngineRLSPluginMixin):
    """Standalone & Integrated Salesforce Vertical Engine Plugin."""

    plugin_id: str = "salesforce"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "salesforce_integrations",
        "salesforce_read_model",
        "salesforce_webhook_events",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.salesforce import mcp_handlers as sf_mcp_handlers

        tools = {
            "sf_query_soql": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_query_soql"),
                cacheable=True,
                admin_only=False,
                mutation=False,
                engine="salesforce",
            ),
            "sf_get_record": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_get_record"),
                cacheable=True,
                admin_only=False,
                mutation=False,
                engine="salesforce",
            ),
            "sf_create_record": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_create_record"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="salesforce",
            ),
            "sf_update_record": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_update_record"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="salesforce",
            ),
            "sf_delete_record": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_delete_record"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="salesforce",
            ),
            "sf_manage_account": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_manage_account"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="salesforce",
            ),
            "sf_manage_contact": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_manage_contact"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="salesforce",
            ),
            "sf_manage_lead": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_manage_lead"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="salesforce",
            ),
            "sf_manage_opportunity": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_manage_opportunity"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="salesforce",
            ),
            "sf_manage_case": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_manage_case"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="salesforce",
            ),
            "sf_log_activity": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_log_activity"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="salesforce",
            ),
            "sf_sync_now": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_sync_now"),
                cacheable=False,
                admin_only=True,
                mutation=True,
                engine="salesforce",
            ),
            "sf_sync_status": ToolSpec(
                _h(sf_mcp_handlers, "handle_sf_sync_status"),
                cacheable=False,
                admin_only=False,
                mutation=False,
                engine="salesforce",
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import salesforce as sf_handlers

        routes = [
            Route(
                "/api/admin/salesforce/config",
                endpoint=sf_handlers.api_admin_salesforce_config,
                methods=["GET"],
            ),
            Route(
                "/api/admin/salesforce/config",
                endpoint=sf_handlers.api_admin_salesforce_config_save,
                methods=["POST"],
            ),
            Route(
                "/api/admin/salesforce/records",
                endpoint=sf_handlers.api_admin_salesforce_records,
                methods=["GET"],
            ),
            Route(
                "/api/admin/salesforce/records",
                endpoint=sf_handlers.api_admin_salesforce_mutate,
                methods=["POST"],
            ),
            Route(
                "/api/admin/salesforce/sync",
                endpoint=sf_handlers.api_admin_salesforce_sync_now,
                methods=["POST"],
            ),
            Route(
                "/api/admin/salesforce/webhooks",
                endpoint=sf_handlers.api_admin_salesforce_webhooks,
                methods=["GET"],
            ),
            Route(
                "/api/webhooks/salesforce",
                endpoint=sf_handlers.api_salesforce_webhook_ingest,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class OdooPlugin(_EngineRLSPluginMixin):
    """Standalone & Integrated Super-Intelligent Odoo Vertical Engine + LLM Cross-Talker Plugin."""

    plugin_id: str = "odoo"
    TENANT_RLS_TABLES: tuple[str, ...] = (
        "odoo_integrations",
        "odoo_read_model",
        "odoo_crosstalk_messages",
    )

    def register_tools(self, registry: Any) -> None:
        from nce_verticals.odoo import mcp_handlers as odoo_mcp_handlers

        tools = {
            "odoo_execute_kw": ToolSpec(
                _h(odoo_mcp_handlers, "handle_odoo_execute_kw"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="odoo",
            ),
            "odoo_workflow_action": ToolSpec(
                _h(odoo_mcp_handlers, "handle_odoo_workflow_action"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="odoo",
            ),
            "odoo_super_intelligence": ToolSpec(
                _h(odoo_mcp_handlers, "handle_odoo_super_intelligence"),
                cacheable=True,
                admin_only=False,
                mutation=False,
                engine="odoo",
            ),
            "odoo_llm_crosstalk": ToolSpec(
                _h(odoo_mcp_handlers, "handle_odoo_llm_crosstalk"),
                cacheable=False,
                admin_only=False,
                mutation=True,
                engine="odoo",
                engine_dependencies=("odoo", "salesforce"),
            ),
            "odoo_sync_now": ToolSpec(
                _h(odoo_mcp_handlers, "handle_odoo_sync_now"),
                cacheable=False,
                admin_only=True,
                mutation=True,
                engine="odoo",
            ),
            "odoo_status": ToolSpec(
                _h(odoo_mcp_handlers, "handle_odoo_status"),
                cacheable=False,
                admin_only=False,
                mutation=False,
                engine="odoo",
            ),
        }
        for k, v in tools.items():
            registry[k] = v

    def register_routes(self, app: Any) -> None:
        from nce_verticals.admin_handlers import odoo as odoo_handlers

        routes = [
            Route(
                "/api/admin/odoo/config",
                endpoint=odoo_handlers.api_admin_odoo_config,
                methods=["GET"],
            ),
            Route(
                "/api/admin/odoo/config",
                endpoint=odoo_handlers.api_admin_odoo_config_save,
                methods=["POST"],
            ),
            Route(
                "/api/admin/odoo/records",
                endpoint=odoo_handlers.api_admin_odoo_records,
                methods=["GET"],
            ),
            Route(
                "/api/admin/odoo/execute",
                endpoint=odoo_handlers.api_admin_odoo_execute,
                methods=["POST"],
            ),
            Route(
                "/api/admin/odoo/intelligence",
                endpoint=odoo_handlers.api_admin_odoo_intelligence,
                methods=["GET"],
            ),
            Route(
                "/api/admin/odoo/crosstalk",
                endpoint=odoo_handlers.api_admin_odoo_crosstalk_history,
                methods=["GET"],
            ),
            Route(
                "/api/admin/odoo/crosstalk",
                endpoint=odoo_handlers.api_admin_odoo_crosstalk,
                methods=["POST"],
            ),
            Route(
                "/api/admin/odoo/sync",
                endpoint=odoo_handlers.api_admin_odoo_sync_now,
                methods=["POST"],
            ),
            Route(
                "/api/webhooks/odoo",
                endpoint=odoo_handlers.api_odoo_webhook_ingest,
                methods=["POST"],
            ),
        ]
        _mount_routes(app, routes)

    def register_workers(self, worker_registry: Any) -> None:
        pass

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        pass

    def get_migration_dir(self) -> Path | None:
        mdir = Path(__file__).parent / "migrations"
        return mdir if mdir.is_dir() else None

    async def verify_schema_prerequisites(self, conn: Any) -> bool:
        from nce_verticals.security.http_guard import verify_entra_id_schema_gate

        return await verify_entra_id_schema_gate(conn)


class VerticalEnginesPlugin:
    """Unified NCE Plugin aggregating the 22 modular vertical engines with Dual-Axis filtering."""

    plugin_id: str = "nce_verticals"
    name: str = "nce_verticals"
    version: str = "3.0.0"

    def __init__(
        self,
        enabled_engines: str | None = None,
        type_filter: str | None = None,
        category_filter: str | None = None,
    ) -> None:
        import importlib

        from nce_verticals.registry import (
            ENGINE_REGISTRY,
            is_engine_installed,
            resolve_enabled_engines,
            resolve_schema_dependencies,
        )

        self._enabled_raw = enabled_engines
        self._type_filter = type_filter
        self._category_filter = category_filter
        self._resolved_specs = resolve_enabled_engines(
            enabled_raw=enabled_engines,
            type_filter=type_filter,
            category_filter=category_filter,
        )
        self._enabled_slugs = {spec.slug for spec in self._resolved_specs}

        sub_plugins: list[Any] = []
        g = globals()
        for spec in self._resolved_specs:
            cls = g.get(spec.plugin_class)
            if cls is None:
                pkg_mod = importlib.import_module(spec.package)
                cls = getattr(pkg_mod, spec.plugin_class)
            inst = cls()
            inst.name = spec.slug
            inst.plugin_id = spec.slug
            inst.version = self.version
            inst.types = sorted(spec.types)
            inst.categories = sorted(spec.categories)
            inst.installed = is_engine_installed(spec.slug)
            inst.enabled = True
            inst.requires_schemas = list(spec.requires_schemas)
            sub_plugins.append(inst)

        self.sub_plugins: list[Any] = sub_plugins
        self.plugins: list[Any] = sub_plugins
        self.types: list[str] = sorted({t for spec in self._resolved_specs for t in spec.types})
        self.categories: list[str] = sorted(
            {c for spec in self._resolved_specs for c in spec.categories}
        )
        self.installed: bool = True
        self.enabled: bool = bool(self.sub_plugins)
        self._schema_Order = resolve_schema_dependencies(
            [spec.slug for spec in self._resolved_specs]
        )
        self._all_specs = ENGINE_REGISTRY

    def get_required_schema_engines(self) -> list[str]:
        """Return topologically ordered engine slugs including prerequisite SQL schemas."""
        from nce_verticals.registry import resolve_schema_dependencies

        return resolve_schema_dependencies([spec.slug for spec in self._resolved_specs])

    def get_plugin_descriptors(
        self,
        type_filter: str | None = None,
        category_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return metadata descriptors for engines, optionally filtered by type and/or category."""
        from nce_verticals.registry import is_engine_installed, resolve_enabled_engines

        active_set = self._enabled_slugs
        specs = resolve_enabled_engines(
            enabled_raw="all",
            type_filter=type_filter,
            category_filter=category_filter,
        )
        descriptors: list[dict[str, Any]] = []
        for spec in specs:
            installed = is_engine_installed(spec.slug)
            optional_deps = list(
                getattr(spec, "optional_dependencies", None)
                or getattr(spec, "optional_deps", ())
                or ()
            )
            descriptors.append(
                {
                    "slug": spec.slug,
                    "id": spec.slug,
                    "plugin_id": self.plugin_id,
                    "name": getattr(spec, "name", None) or spec.title,
                    "description": getattr(spec, "description", None) or spec.title,
                    "title": spec.title,
                    "version": "3.1.0",
                    "types": list(spec.types),
                    "categories": list(spec.categories),
                    "requires_schemas": list(spec.requires_schemas),
                    "optional_dependencies": optional_deps,
                    "optional_deps": optional_deps,
                    "installed": installed,
                    "enabled_by_env": spec.slug in active_set,
                    "enabled": spec.slug in active_set,
                    "tool_count": spec.tool_count,
                    "route_count": spec.route_count,
                    "install_extra": f"nce-vertical-engines[{spec.slug}]",
                }
            )

        return descriptors

    get_engine_descriptors = get_plugin_descriptors

    def register_tools(self, registry: Any) -> None:
        for p in self.sub_plugins:
            p.register_tools(registry)

    def register_routes(self, app: Any) -> None:
        for p in self.sub_plugins:
            p.register_routes(app)

    def register_workers(self, worker_registry: Any) -> None:
        for p in self.sub_plugins:
            p.register_workers(worker_registry)

    def register_cognitive_hooks(self, cognitive_engine: Any) -> None:
        for p in self.sub_plugins:
            p.register_cognitive_hooks(cognitive_engine)

    def get_migrations_dir(self) -> Path:
        import importlib.resources

        res = importlib.resources.files("nce_verticals").joinpath("migrations")
        p = Path(str(res))
        if p.is_dir():
            return p
        return Path(__file__).resolve().parent / "migrations"

    def get_migration_dir(self) -> Path | None:
        mdir = self.get_migrations_dir()
        return mdir if mdir.is_dir() else None

    def get_unmanaged_pg_sites(self) -> frozenset[str]:
        """Audited global reference-table call sites owned by Vertical Engines."""
        return frozenset(
            {
                "geodata.n50.import",
                "geodata.n50.bbox_query",
                "geodata.osm.import",
                "geodata.osm.bbox_query",
                "geodata.place_names.import",
                "geodata.place_names.nearest",
            }
        )

    def get_active_engine_rls_tables(self) -> dict[str, str]:
        """Return forced-RLS tenant tables for active sub-plugins plus shared vertical spine."""
        tables: dict[str, str] = {tbl: "namespace_id" for tbl in SHARED_SPINE_TENANT_RLS_TABLES}
        for sub in self.sub_plugins:
            getter = getattr(sub, "get_tenant_rls_tables", None)
            if callable(getter):
                tables.update(getter())
        return tables

    def get_tenant_rls_tables(self) -> dict[str, str]:
        """Return all 96 forced-RLS tenant tables provisioned by nce_verticals/migrations."""
        tables: dict[str, str] = {tbl: "namespace_id" for tbl in SHARED_SPINE_TENANT_RLS_TABLES}
        for plugin_cls in ALL_ENGINE_PLUGINS:
            for tbl in getattr(plugin_cls, "TENANT_RLS_TABLES", ()):
                tables[tbl] = "namespace_id"
        for sub in self.sub_plugins:
            getter = getattr(sub, "get_tenant_rls_tables", None)
            if callable(getter):
                tables.update(getter())
        return tables

    def get_global_tables(self) -> set[str]:
        """Return the 5 global non-RLS tables provisioned by nce_verticals/migrations."""
        return set(VERTICAL_GLOBAL_TABLES)

    def get_capabilities(self) -> Any:
        """Return structured PluginCapabilities for Core dynamic RLS and PG governance."""
        try:
            from nce.plugins import PluginCapabilities as _CapCls
        except Exception:
            _CapCls = _FallbackPluginCapabilities  # type: ignore[assignment]
        return _CapCls(
            tenant_rls_tables=self.get_tenant_rls_tables(),
            global_tables=VERTICAL_GLOBAL_TABLES,
            unmanaged_pg_sites=self.get_unmanaged_pg_sites(),
        )

    async def on_namespace_created(self, conn: Any, namespace_id: Any) -> None:
        """Seed node_ownership_registry for newly created namespaces when vertical schema exists."""
        try:
            from nce_verticals.entity_resolution.ownership_seed import (  # type: ignore[import-not-found]
                seed_node_ownership_registry,
            )
        except ImportError:
            from nce.entity_resolution.ownership_seed import seed_node_ownership_registry

        try:
            tx_factory = getattr(conn, "transaction", None)
            tx = tx_factory() if callable(tx_factory) else None
            if tx is not None and hasattr(tx, "__aenter__"):
                async with tx:
                    await seed_node_ownership_registry(conn, namespace_id)
            else:
                await seed_node_ownership_registry(conn, namespace_id)
        except Exception as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            if exc.__class__.__name__ == "UndefinedTableError" or sqlstate == "42P01":
                log.debug(
                    "Skipping node_ownership_registry seed for namespace %s (table not created yet)",
                    namespace_id,
                )
                return
            raise


ALL_ENGINE_PLUGINS: tuple[type[_EngineRLSPluginMixin], ...] = (
    AgreementsPlugin,
    AssetsPlugin,
    BusinessInsightsPlugin,
    CustomerPortalPlugin,
    DiagnosticsPlugin,
    Dynamics365Plugin,
    EconomyPlugin,
    FieldTechPlugin,
    GeodataPlugin,
    HRPlugin,
    InventoryPlugin,
    LegalEntitiesPlugin,
    MarketingPlugin,
    NetboxPlugin,
    NotificationsPlugin,
    ProcurementPlugin,
    ProductPlugin,
    ProjectPlugin,
    ResourcesPlugin,
    SalesPlugin,
    SitesPlugin,
    SupportPlugin,
    SystemDesignPlugin,
    VendorsPlugin,
    EntraIDPlugin,
    SalesforcePlugin,
    OdooPlugin,
)
