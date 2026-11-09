"""
lighting_dali_server.py
=======================
Standalone entrypoint for the Relux / DIALux Light Design & IEC 62386 DALI-2 / Glamox
System Design Connector, Reader & Analyser Engine.
"""

from __future__ import annotations

import os
import uvicorn
from nce_verticals.lighting_dali.app import create_lighting_dali_standalone_app

app = create_lighting_dali_standalone_app()

if __name__ == "__main__":
    host = os.environ.get("NCE_LIGHTING_HOST", "127.0.0.1")
    port = int(os.environ.get("NCE_LIGHTING_PORT", "8093"))
    uvicorn.run(app, host=host, port=port)
