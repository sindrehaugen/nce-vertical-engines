"""
nce_verticals/admin_handlers/lighting_dali.py
=============================================
Admin HTTP handlers for the Relux / DIALux Light Design & IEC 62386 DALI-2 / Glamox
System Design Connector, Reader & Analyser Engine.
"""

from __future__ import annotations

from typing import Any

try:
    from starlette.responses import JSONResponse
except ImportError:
    import json as _json

    class JSONResponse:  # type: ignore[no-redef]
        def __init__(self, content: Any, status_code: int = 200) -> None:
            self.content = content
            self.status_code = status_code
            self.body = _json.dumps(content, default=str).encode("utf-8")

from nce_verticals.lighting_dali.analyser import (
    EN12464_ZONES,
    analyze_dali2_bus,
    analyze_lighting_project,
    analyze_room_en12464,
    calculate_dali_dimming_level,
    calculate_dt8_mirek,
)
from nce_verticals.lighting_dali.glamox_catalog import (
    GLAMOX_CONTROL_DEVICES,
    GLAMOX_LUMINAIRE_CATALOG,
    decode_glamox_code,
    recommend_glamox_luminaires,
)
from nce_verticals.lighting_dali.mcp_handlers import get_recent_lighting_projects
from nce_verticals.lighting_dali.parsers import (
    parse_eulumdat_ldt,
    parse_iesna_ies,
    parse_relux_or_dialux_project,
)


async def api_admin_lighting_catalog(request: Any) -> JSONResponse:
    """GET /api/admin/lighting-dali/catalog — return Glamox luminaire & DALI-2 catalog + zones."""
    projects = get_recent_lighting_projects()
    return JSONResponse(
        {
            "luminaires": GLAMOX_LUMINAIRE_CATALOG,
            "dali2_control_devices": GLAMOX_CONTROL_DEVICES,
            "en12464_zones": EN12464_ZONES,
            "recent_projects_count": len(projects),
            "recent_projects": projects[:20],
        }
    )


async def api_admin_lighting_analyze_project(request: Any) -> JSONResponse:
    """POST /api/admin/lighting-dali/analyze-project — parse Relux/DIALux & run EN 12464-1 + DALI-2 analysis."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    try:
        content = body.get("content") or body
        parsed = parse_relux_or_dialux_project(content)
        report = analyze_lighting_project(parsed)
        projects = get_recent_lighting_projects()
        projects.insert(0, report)
        del projects[50:]
        return JSONResponse({"status": "ok", "report": report})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_admin_lighting_analyze_dali_bus(request: Any) -> JSONResponse:
    """POST /api/admin/lighting-dali/analyze-bus — run IEC 62386 DALI-2 & NEK 400 bus engineering check."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    try:
        res = analyze_dali2_bus(
            ecg_count=int(body.get("ecg_count", 24)),
            ecd_sensor_count=int(body.get("ecd_sensor_count", 4)),
            ecd_pushbutton_count=int(body.get("ecd_pushbutton_count", 2)),
            dt1_emergency_count=int(body.get("dt1_emergency_count", 0)),
            cable_length_m=float(body.get("cable_length_m", 120.0)),
            cable_cross_section_mm2=float(body.get("cable_cross_section_mm2", 1.5)),
            psu_rated_current_ma=float(body.get("psu_rated_current_ma", 240.0)),
            topology=str(body.get("topology", "line_or_star")),
            total_driver_wattage_w=(
                float(body["total_driver_wattage_w"])
                if body.get("total_driver_wattage_w") is not None
                else None
            ),
            mcb_rating=str(body.get("mcb_rating", "B16")),
        )
        return JSONResponse({"status": "ok", "bus_analysis": res})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_admin_lighting_parse_photometric(request: Any) -> JSONResponse:
    """POST /api/admin/lighting-dali/parse-photometric — parse EULUMDAT (.ldt) or IESNA (.ies) file."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    content = str(body.get("content") or "").strip()
    fmt = str(body.get("format") or "").strip().lower()
    if not content:
        return JSONResponse({"error": "content is required"}, status_code=422)

    try:
        if fmt == "ies" or content.upper().startswith("IESNA") or "TILT=" in content.upper():
            res = parse_iesna_ies(content)
        else:
            res = parse_eulumdat_ldt(content)
        return JSONResponse({"status": "ok", "photometric": res})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_admin_lighting_decode_glamox(request: Any) -> JSONResponse:
    """POST /api/admin/lighting-dali/decode-glamox — decode Glamox luminaire code & recommend controls."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    code = str(body.get("code") or "Glamox C95-R 600x600 4000 DALI 840 MP EM 3H")
    zone_code = str(body.get("zone_code") or "OFFICE_WRITING")
    dali_level = body.get("dali_level")
    cct_kelvin = body.get("cct_kelvin")

    out: dict[str, Any] = {
        "decoded": decode_glamox_code(code),
        "recommendation": recommend_glamox_luminaires(zone_code),
    }
    if dali_level is not None:
        out["dimming_curve"] = calculate_dali_dimming_level(int(dali_level))
    if cct_kelvin is not None:
        out["dt8_mirek"] = calculate_dt8_mirek(float(cct_kelvin))

    return JSONResponse(out)
