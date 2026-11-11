"""
nce_verticals/odoo/app.py
=========================
Standalone ASGI Application for the Super-Intelligent Odoo Vertical Engine +
Full LLM Cross-Talker + Microsoft Entra ID Security Gate.
Can run completely standalone via `odoo_server.py` or mounted inside NCE.
"""

from __future__ import annotations

from typing import Any

from nce_verticals.admin_handlers import entra_id as entra_handlers
from nce_verticals.admin_handlers import odoo as odoo_handlers
from nce_verticals.admin_handlers.odoo import JSONResponse
from nce_verticals.plugin import Route
from nce_verticals.security.http_guard import BoundedBodyMiddleware

try:
    from starlette.applications import Starlette
except ImportError:

    class Starlette:  # type: ignore[no-redef]
        def __init__(self, debug: bool = False, routes: list[Any] | None = None) -> None:
            self.debug = debug
            self.routes = routes or []


async def healthz(request: Any) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "engine": "odoo_super_intelligent_standalone",
            "llm_crosstalker": "active",
            "entra_gate": "enabled",
        }
    )


def create_standalone_odoo_app(lifespan: Any = None) -> Starlette:
    routes = [
        Route("/healthz", endpoint=healthz, methods=["GET"]),
        Route("/api/admin/entra/config", endpoint=entra_handlers.api_admin_entra_config, methods=["GET"]),
        Route("/api/admin/entra/config", endpoint=entra_handlers.api_admin_entra_config_save, methods=["POST"]),
        Route("/api/admin/entra/sessions", endpoint=entra_handlers.api_admin_entra_sessions, methods=["GET"]),
        Route("/api/admin/entra/sessions/revoke", endpoint=entra_handlers.api_admin_entra_revoke_session, methods=["POST"]),
        Route("/api/admin/entra/verify-user", endpoint=entra_handlers.api_admin_entra_verify_user, methods=["POST"]),
        Route("/api/admin/entra/audit", endpoint=entra_handlers.api_admin_entra_audit, methods=["GET"]),
        Route("/api/admin/odoo/config", endpoint=odoo_handlers.api_admin_odoo_config, methods=["GET"]),
        Route("/api/admin/odoo/config", endpoint=odoo_handlers.api_admin_odoo_config_save, methods=["POST"]),
        Route("/api/admin/odoo/records", endpoint=odoo_handlers.api_admin_odoo_records, methods=["GET"]),
        Route("/api/admin/odoo/execute", endpoint=odoo_handlers.api_admin_odoo_execute, methods=["POST"]),
        Route("/api/admin/odoo/intelligence", endpoint=odoo_handlers.api_admin_odoo_intelligence, methods=["GET"]),
        Route("/api/admin/odoo/crosstalk", endpoint=odoo_handlers.api_admin_odoo_crosstalk_history, methods=["GET"]),
        Route("/api/admin/odoo/crosstalk", endpoint=odoo_handlers.api_admin_odoo_crosstalk, methods=["POST"]),
        Route("/api/webhooks/odoo", endpoint=odoo_handlers.api_odoo_webhook_ingest, methods=["POST"]),
    ]
    app = Starlette(debug=False, routes=routes, lifespan=lifespan)
    if hasattr(app, "add_middleware"):
        app.add_middleware(BoundedBodyMiddleware)
    return app
