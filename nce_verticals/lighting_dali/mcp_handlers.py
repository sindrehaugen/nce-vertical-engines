"""
nce_verticals/lighting_dali/mcp_handlers.py
===========================================
MCP tool handlers for the Relux / DIALux Light Design & IEC 62386 DALI-2 / Glamox
System Design Connector, Reader & Analyser Engine.
"""

from __future__ import annotations

import json
import logging
from typing import Any

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
from nce_verticals.lighting_dali.parsers import (
    parse_dali_address_csv,
    parse_eulumdat_ldt,
    parse_iesna_ies,
    parse_relux_or_dialux_project,
)

log = logging.getLogger("nce_verticals.lighting_dali.mcp_handlers")

# In-memory store of analyzed projects for standalone & Admin UI inspection
_RECENT_PROJECTS: list[dict[str, Any]] = []


def get_recent_lighting_projects() -> list[dict[str, Any]]:
    return _RECENT_PROJECTS


async def handle_lighting_parse_photometric(
    engine: Any, arguments: dict[str, Any]
) -> str:
    """Parse an EULUMDAT (`.ldt`) or IESNA (`.ies`) photometric file and decode Glamox specs."""
    content = str(
        arguments.get("content") or arguments.get("file_content") or ""
    ).strip()
    fmt = str(arguments.get("format") or "").strip().lower()
    if not content:
        return json.dumps(
            {"error": "content (EULUMDAT .ldt or IESNA .ies text) is required"}
        )

    try:
        if (
            fmt == "ies"
            or content.upper().startswith("IESNA")
            or "TILT=" in content.upper()
        ):
            parsed = parse_iesna_ies(content)
        else:
            parsed = parse_eulumdat_ldt(content)
        return json.dumps(parsed, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def handle_lighting_analyze_relux_project(
    engine: Any, arguments: dict[str, Any]
) -> str:
    """
    Parse a Relux / DIALux project export (JSON, XML, or CSV schedule) and perform full
    EN 12464-1 room compliance + IEC 62386 DALI-2 subnet & Glamox Ethernet2DALI sizing.
    """
    project_input = arguments.get("project") or arguments.get("content") or arguments
    try:
        parsed_project = parse_relux_or_dialux_project(project_input)
        report = analyze_lighting_project(parsed_project)
        _RECENT_PROJECTS.insert(0, report)
        del _RECENT_PROJECTS[50:]
        return json.dumps(report, default=str)
    except Exception as exc:
        log.exception("handle_lighting_analyze_relux_project failed")
        return json.dumps({"error": str(exc)})


async def handle_lighting_analyze_room(engine: Any, arguments: dict[str, Any]) -> str:
    """Run EN 12464-1 photometric & Glamox luminaire analysis on a single room definition."""
    try:
        report = analyze_room_en12464(arguments)
        return json.dumps(report, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def handle_dali2_analyze_bus(engine: Any, arguments: dict[str, Any]) -> str:
    """
    Validate a DALI-2 bus line per IEC 62386-101/102/103 & NEK 400:
    checks 64 ECG / 64 ECD address limits, 250 mA current budget, <= 2.0 V voltage drop,
    and MCB LED driver inrush current limits.
    """
    try:
        res = analyze_dali2_bus(
            ecg_count=int(arguments.get("ecg_count", 20)),
            ecd_sensor_count=int(arguments.get("ecd_sensor_count", 4)),
            ecd_pushbutton_count=int(arguments.get("ecd_pushbutton_count", 2)),
            dt1_emergency_count=int(arguments.get("dt1_emergency_count", 0)),
            cable_length_m=float(arguments.get("cable_length_m", 120.0)),
            cable_cross_section_mm2=float(
                arguments.get("cable_cross_section_mm2", 1.5)
            ),
            psu_rated_current_ma=float(arguments.get("psu_rated_current_ma", 240.0)),
            topology=str(arguments.get("topology", "line_or_star")),
            total_driver_wattage_w=(
                float(arguments["total_driver_wattage_w"])
                if arguments.get("total_driver_wattage_w") is not None
                else None
            ),
            mcb_rating=str(arguments.get("mcb_rating", "B16")),
        )
        return json.dumps(res, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def handle_glamox_decode_and_recommend(
    engine: Any, arguments: dict[str, Any]
) -> str:
    """
    Decode a Glamox luminaire order code / description or recommend Glamox DALI-2
    luminaires & controls for an EN 12464-1 zone.
    """
    code = str(arguments.get("code") or arguments.get("description") or "").strip()
    zone_code = str(arguments.get("zone_code") or "OFFICE_WRITING").strip().upper()
    tunable_white = bool(arguments.get("require_tunable_white", False))

    result: dict[str, Any] = {}
    if code:
        result["decoded_luminaire"] = decode_glamox_code(code)
    result["recommendation"] = recommend_glamox_luminaires(
        zone_code=zone_code,
        require_tunable_white=tunable_white,
    )
    if arguments.get("dali_level") is not None:
        result["dimming_curve"] = calculate_dali_dimming_level(
            int(arguments["dali_level"])
        )
    if arguments.get("cct_kelvin") is not None:
        result["dt8_mirek"] = calculate_dt8_mirek(float(arguments["cct_kelvin"]))
    if arguments.get("dali_csv"):
        result["dali_schedule"] = parse_dali_address_csv(str(arguments["dali_csv"]))

    return json.dumps(result, default=str)


async def handle_glamox_catalog_list(engine: Any, arguments: dict[str, Any]) -> str:
    """List curated Glamox DALI-2 luminaires, control devices, and EN 12464-1 zones."""
    return json.dumps(
        {
            "luminaires": GLAMOX_LUMINAIRE_CATALOG,
            "dali2_control_devices": GLAMOX_CONTROL_DEVICES,
            "en12464_zones": EN12464_ZONES,
        },
        default=str,
    )
