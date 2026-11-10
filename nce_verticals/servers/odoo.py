"""
nce_verticals/servers/odoo.py
=============================
Standalone Super-Intelligent Odoo + LLM Cross-Talker Server Entry Point.
Run with: `uvicorn nce_verticals.servers.odoo:app --host 0.0.0.0 --port 8093`
"""

from __future__ import annotations

import os

from nce_verticals.odoo.app import create_standalone_odoo_app
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

app = create_standalone_odoo_app()


def main() -> None:
    """CLI / [project.scripts] entrypoint for nce-odoo-server."""
    import uvicorn

    host = os.environ.get("NCE_ODOO_HOST", os.environ.get("ODOO_HOST", "0.0.0.0"))
    port = int(os.environ.get("NCE_ODOO_PORT", os.environ.get("ODOO_PORT", "8093")))
    workers = int(os.environ.get("NCE_ODOO_WORKERS", "1"))
    if workers > 1:
        uvicorn.run("nce_verticals.servers.odoo:app", host=host, port=port, workers=workers)
    else:
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
