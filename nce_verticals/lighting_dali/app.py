"""
nce_verticals/lighting_dali/app.py
==================================
Standalone Starlette / FastAPI-compatible ASGI application for the Relux / DIALux
Light Design & IEC 62386 DALI-2 / Glamox System Design Engine.
"""

from __future__ import annotations

import json
from typing import Any

from nce_verticals.admin_handlers import entra_id as entra_admin
from nce_verticals.admin_handlers import lighting_dali as ld_admin
from nce_verticals.lighting_dali import mcp_handlers as ld_mcp

try:
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
except ImportError:
    Starlette = None  # type: ignore[assignment]

    class JSONResponse:  # type: ignore[no-redef]
        def __init__(self, content: Any, status_code: int = 200) -> None:
            self.content = content
            self.status_code = status_code

    class Route:  # type: ignore[no-redef]
        def __init__(self, path: str, endpoint: Any, methods: list[str] | None = None) -> None:
            self.path = path
            self.endpoint = endpoint
            self.methods = methods or ["GET"]


STANDALONE_TOOL_MAP = {
    "lighting_parse_photometric": ld_mcp.handle_lighting_parse_photometric,
    "lighting_analyze_relux_project": ld_mcp.handle_lighting_analyze_relux_project,
    "lighting_analyze_room": ld_mcp.handle_lighting_analyze_room,
    "dali2_analyze_bus": ld_mcp.handle_dali2_analyze_bus,
    "glamox_decode_and_recommend": ld_mcp.handle_glamox_decode_and_recommend,
    "glamox_catalog_list": ld_mcp.handle_glamox_catalog_list,
}


async def api_lighting_health(request: Any) -> JSONResponse:
    return JSONResponse({"status": "ok", "engine": "lighting_dali", "tools": list(STANDALONE_TOOL_MAP.keys())})


async def api_lighting_mcp_call(request: Any) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    tool_name = str(body.get("name") or body.get("tool") or "").strip()
    arguments = body.get("arguments") or {}
    handler = STANDALONE_TOOL_MAP.get(tool_name)
    if handler is None:
        return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=404)
    raw = await handler(None, arguments)
    return JSONResponse(json.loads(raw))


def create_lighting_dali_standalone_app() -> Any:
    routes = [
        Route("/health", endpoint=api_lighting_health, methods=["GET"]),
        Route("/mcp/call", endpoint=api_lighting_mcp_call, methods=["POST"]),
        Route("/api/admin/lighting-dali/catalog", endpoint=ld_admin.api_admin_lighting_catalog, methods=["GET"]),
        Route("/api/admin/lighting-dali/analyze-project", endpoint=ld_admin.api_admin_lighting_analyze_project, methods=["POST"]),
        Route("/api/admin/lighting-dali/analyze-bus", endpoint=ld_admin.api_admin_lighting_analyze_dali_bus, methods=["POST"]),
        Route("/api/admin/lighting-dali/parse-photometric", endpoint=ld_admin.api_admin_lighting_parse_photometric, methods=["POST"]),
        Route("/api/admin/lighting-dali/decode-glamox", endpoint=ld_admin.api_admin_lighting_decode_glamox, methods=["POST"]),
        Route("/api/admin/entra/config", endpoint=entra_admin.api_admin_entra_config, methods=["GET", "POST"]),
    ]
    if Starlette is not None:
        return Starlette(debug=False, routes=routes)
    return routes
