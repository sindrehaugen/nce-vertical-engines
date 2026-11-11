"""
nce_verticals/servers/portal.py
===============================
Dedicated Standalone ASGI Entry Point for Customer Portal (Charter Layer 3).

Features:
  - Connects/disconnects NCEEngine during ASGI lifespan.
  - Exposes `app` for uvicorn (e.g. `uvicorn nce_verticals.servers.portal:app --port 8005`).
  - No internal admin endpoints or tool surfaces mounted.
  - Zero-trust customer principal isolation.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from nce.orchestrator import NCEEngine
from starlette.applications import Starlette

from nce_verticals.customer_portal.app import build_customer_portal_app
from nce_verticals.security.http_guard import verify_entra_id_schema_gate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nce.portal_server")

engine: NCEEngine | None = None


@asynccontextmanager
async def portal_lifespan(app: Starlette):
    global engine
    engine = NCEEngine()
    try:
        await engine.connect()
        app.state.engine = engine
        log.info("Customer Portal server: NCEEngine connected.")
        if getattr(engine, "pg_pool", None) is not None:
            async with engine.pg_pool.acquire(timeout=5.0) as conn:
                await verify_entra_id_schema_gate(conn)
    except Exception as exc:
        log.warning("Customer Portal server: NCEEngine connect failed or offline: %s", exc)
        app.state.engine = engine
    yield
    if engine is not None:
        try:
            await engine.disconnect()
            log.info("Customer Portal server: NCEEngine disconnected.")
        except Exception as exc:
            log.warning("Customer Portal server: NCEEngine disconnect failed: %s", exc)
        engine = None


app = build_customer_portal_app(engine=None, lifespan=portal_lifespan)


def main() -> None:
    """CLI / [project.scripts] entrypoint for nce-portal-server."""
    import uvicorn

    port = int(os.environ.get("PORTAL_PORT", "8005"))
    host = os.environ.get("PORTAL_HOST", "0.0.0.0")
    workers = int(os.environ.get("PORTAL_WORKERS", "1"))
    if workers > 1:
        uvicorn.run(
            "nce_verticals.servers.portal:app",
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
