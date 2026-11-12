"""
nce_verticals/servers/salesforce.py
===================================
Standalone Salesforce + Entra ID Vertical Engine Server Entry Point.
Run with: `uvicorn nce_verticals.servers.salesforce:app --host 0.0.0.0 --port 8092`
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from nce_verticals.salesforce.app import create_standalone_salesforce_app
from nce_verticals.security.entra_id import (
    EntraIDAuthenticator,
    EntraIDHttpMiddleware,
    EntraPrincipal,
    EntraSecurityGate,
    require_entra_identity,
)
from nce_verticals.security.http_guard import verify_entra_id_schema_gate

log = logging.getLogger("nce_verticals.servers.salesforce")

__all__ = [
    "EntraIDAuthenticator",
    "EntraIDHttpMiddleware",
    "EntraPrincipal",
    "EntraSecurityGate",
    "app",
    "create_standalone_salesforce_app",
    "main",
    "require_entra_identity",
    "verify_entra_id_schema_gate",
]


@asynccontextmanager
async def salesforce_lifespan(app: Any):
    try:
        from nce.orchestrator import NCEEngine

        engine = NCEEngine()
        await engine.connect()
        if getattr(engine, "pg_pool", None) is not None:
            async with engine.pg_pool.acquire(timeout=5.0) as conn:
                await verify_entra_id_schema_gate(conn)
        await engine.disconnect()
    except Exception as exc:
        log.debug("Salesforce server startup schema gate check: %s", exc)
    yield


app = create_standalone_salesforce_app(lifespan=salesforce_lifespan)


def main() -> None:
    """CLI / [project.scripts] entrypoint for nce-salesforce-server."""
    import uvicorn

    host = os.environ.get("NCE_SALESFORCE_HOST", os.environ.get("SALESFORCE_HOST", "0.0.0.0"))
    port = int(os.environ.get("NCE_SALESFORCE_PORT", os.environ.get("SALESFORCE_PORT", "8092")))
    workers = int(os.environ.get("NCE_SALESFORCE_WORKERS", "1"))
    if workers > 1:
        uvicorn.run(
            "nce_verticals.servers.salesforce:app",
            host=host,
            port=port,
            workers=workers,
            timeout_keep_alive=30,
            timeout_graceful_shutdown=15,
        )
    else:
        uvicorn.run(
            app,
            host=host,
            port=port,
            timeout_keep_alive=30,
            timeout_graceful_shutdown=15,
        )


if __name__ == "__main__":
    main()
