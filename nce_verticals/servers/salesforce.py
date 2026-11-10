"""
nce_verticals/servers/salesforce.py
===================================
Standalone Salesforce + Entra ID Vertical Engine Server Entry Point.
Run with: `uvicorn nce_verticals.servers.salesforce:app --host 0.0.0.0 --port 8092`
"""

from __future__ import annotations

import os

from nce_verticals.salesforce.app import create_standalone_salesforce_app
from nce_verticals.security.entra_id import (
    EntraIDAuthenticator,
    EntraPrincipal,
    require_entra_identity,
)

__all__ = [
    "EntraIDAuthenticator",
    "EntraPrincipal",
    "app",
    "main",
    "require_entra_identity",
]

app = create_standalone_salesforce_app()


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
