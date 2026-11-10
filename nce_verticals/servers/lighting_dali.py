"""
nce_verticals/servers/lighting_dali.py
======================================
Standalone entrypoint for the Relux / DIALux Light Design & IEC 62386 DALI-2 / Glamox
System Design Connector, Reader & Analyser Engine.
"""

from __future__ import annotations

import os

from nce_verticals.lighting_dali.app import create_lighting_dali_standalone_app
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

app = create_lighting_dali_standalone_app()


def main() -> None:
    """CLI / [project.scripts] entrypoint for nce-lighting-dali-server."""
    import uvicorn

    host = os.environ.get("NCE_LIGHTING_HOST", "127.0.0.1")
    port = int(os.environ.get("NCE_LIGHTING_PORT", "8093"))
    uvicorn.run(
        app,
        host=host,
        port=port,
        timeout_keep_alive=30,
        timeout_graceful_shutdown=15,
    )


if __name__ == "__main__":
    main()
