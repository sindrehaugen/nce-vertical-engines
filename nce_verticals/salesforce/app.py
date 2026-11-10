"""
nce_verticals/salesforce/app.py
===============================
Standalone ASGI Application for the Salesforce Vertical Engine and Microsoft Entra ID Identification Gate.
Can run completely independently via `salesforce_server.py` or mounted into NCE.
"""

from __future__ import annotations

from typing import Any

from nce_verticals.admin_handlers import entra_id as entra_handlers
from nce_verticals.admin_handlers import salesforce as sf_handlers
from nce_verticals.admin_handlers.salesforce import JSONResponse
from nce_verticals.plugin import Route

try:
    from starlette.applications import Starlette
except ImportError:

    class Starlette:  # type: ignore[no-redef]
        def __init__(
            self, debug: bool = False, routes: list[Any] | None = None
        ) -> None:
            self.debug = debug
            self.routes = routes or []


async def healthz(request: Any) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "engines": ["entra_id", "salesforce"],
            "entra_gate": "enabled",
        }
    )


def create_standalone_salesforce_app() -> Starlette:
    routes = [
        Route("/healthz", endpoint=healthz, methods=["GET"]),
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
    return Starlette(debug=False, routes=routes)
