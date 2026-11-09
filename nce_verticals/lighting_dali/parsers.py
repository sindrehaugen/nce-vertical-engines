"""
nce_verticals/lighting_dali/parsers.py
======================================
Deterministic file parsers & connectors for:
1. EULUMDAT (`.ldt`) photometric files
2. IESNA LM-63 (`.ies`) photometric files
3. Relux (`.rdf` / `.rolf` / XML / JSON / CSV) and DIALux (`.evo` / XML / JSON) room projects
4. DALI-2 Addressing & Topology schedules (CSV / JSON)
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import xml.etree.ElementTree as ET
from typing import Any

from nce_verticals.lighting_dali.glamox_catalog import decode_glamox_code


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(str(val).strip().replace(",", "."))
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(float(str(val).strip().replace(",", ".")))
    except (ValueError, TypeError):
        return default


def parse_eulumdat_ldt(ldt_content: str) -> dict[str, Any]:
    """
    Parse an EULUMDAT (`.ldt`) photometric file and compute key photometric metrics:
    - Manufacturer, Luminaire Name, Luminaire Number
    - Symmetry indicator Isym (0..4), Mc (C-planes), Mg (gamma angles)
    - Luminaire dimensions (L, W, H in mm) and luminous area (L1, W1)
    - Downward Flux Fraction (DFF %), Light Output Ratio (LORL %)
    - Total lamp flux (lm), total system wattage (W), luminous efficacy (lm/W)
    - Peak intensity Imax (cd/klm), nadir intensity I(0°), beam angle FWHM (deg)
    - Glamox variant decoding if manufacturer/name matches Glamox
    """
    lines = [ln.strip() for ln in str(ldt_content or "").splitlines()]
    if len(lines) < 26:
        raise ValueError(
            f"EULUMDAT (.ldt) file requires at least 26 header lines (got {len(lines)})"
        )

    company = lines[0]
    ityp = _safe_int(lines[1], 1)
    isym = _safe_int(lines[2], 0)
    mc = _safe_int(lines[3], 1)
    dc = _safe_float(lines[4], 0.0)
    mg = _safe_int(lines[5], 1)
    dg = _safe_float(lines[6], 0.0)
    report_number = lines[7]
    luminaire_name = lines[8]
    luminaire_number = lines[9]
    file_name = lines[10]
    date_user = lines[11]

    length_mm = _safe_float(lines[12], 600.0)
    width_mm = _safe_float(lines[13], 600.0)
    height_mm = _safe_float(lines[14], 60.0)
    lum_length_mm = _safe_float(lines[15], length_mm)
    lum_width_mm = _safe_float(lines[16], width_mm)

    dff_pct = _safe_float(lines[21], 100.0)
    lorl_pct = _safe_float(lines[22], 100.0)
    conversion_factor = _safe_float(lines[23], 1.0)
    tilt_deg = _safe_float(lines[24], 0.0)
    num_lamp_sets = max(1, _safe_int(lines[25], 1))

    idx = 26
    total_flux_lm = 0.0
    total_wattage_w = 0.0
    cct_raw = ""
    cri_raw = ""

    for _ in range(num_lamp_sets):
        if idx + 5 >= len(lines):
            break
        n_lamps = max(1, abs(_safe_int(lines[idx], 1)))
        lamp_type = lines[idx + 1]
        lamp_flux = _safe_float(lines[idx + 2], 4000.0)
        cct_raw = lines[idx + 3] or cct_raw
        cri_raw = lines[idx + 4] or cri_raw
        wattage = _safe_float(lines[idx + 5], 30.0)
        total_flux_lm += lamp_flux if lamp_flux > 0 else (n_lamps * 4000.0)
        total_wattage_w += wattage
        idx += 6

    # 10 Direct ratios for room indices k = 0.60 .. 5.00
    direct_ratios: list[float] = []
    for _ in range(10):
        if idx < len(lines):
            direct_ratios.append(_safe_float(lines[idx], 0.8))
            idx += 1

    # Remaining values: C-plane angles, gamma angles, and intensity values (cd/klm)
    remaining_nums: list[float] = []
    for ln in lines[idx:]:
        for tok in ln.split():
            remaining_nums.append(_safe_float(tok, 0.0))

    # Determine number of stored C-planes based on Isym
    if isym == 1:
        mc_stored = 1
    elif isym in (2, 3):
        mc_stored = (mc // 2) + 1 if mc > 0 else 1
    elif isym == 4:
        mc_stored = (mc // 4) + 1 if mc > 0 else 1
    else:
        mc_stored = max(1, mc)

    c_angles = remaining_nums[:mc] if len(remaining_nums) >= mc else [0.0]
    g_start = mc
    g_angles = (
        remaining_nums[g_start : g_start + mg]
        if len(remaining_nums) >= g_start + mg
        else []
    )
    i_start = g_start + mg
    intensities = remaining_nums[i_start:] if len(remaining_nums) > i_start else []

    nadir_cd_klm = intensities[0] if intensities else 350.0
    max_cd_klm = max(intensities) if intensities else nadir_cd_klm

    # Estimate beam angle (FWHM) along first C-plane
    first_plane = intensities[:mg] if mg and len(intensities) >= mg else intensities
    half_peak = max_cd_klm * 0.5
    half_angle = 45.0
    if g_angles and len(first_plane) == len(g_angles):
        for g_ang, cd_val in zip(g_angles, first_plane):
            if cd_val <= half_peak and g_ang > 0:
                half_angle = g_ang
                break
    beam_angle_fwhm_deg = round(half_angle * 2.0, 1)

    # Estimate high-angle glare ratio (intensity at gamma=65° vs nadir)
    cd_65 = 0.0
    if g_angles and len(first_plane) == len(g_angles):
        for g_ang, cd_val in zip(g_angles, first_plane):
            if abs(g_ang - 65.0) <= 5.0:
                cd_65 = max(cd_65, cd_val)
    estimated_ugr = 16.0 if cd_65 < 80.0 else (19.0 if cd_65 < 200.0 else 22.0)

    luminaire_flux_lm = round(total_flux_lm * (lorl_pct / 100.0), 1)
    efficacy = round(luminaire_flux_lm / max(1.0, total_wattage_w), 1)
    glamox_info = decode_glamox_code(f"{company} {luminaire_name} {luminaire_number}")

    return {
        "format": "EULUMDAT_LDT",
        "company": company,
        "luminaire_name": luminaire_name,
        "luminaire_number": luminaire_number,
        "report_number": report_number,
        "symmetry_isym": isym,
        "c_planes_count": mc,
        "c_planes_stored": mc_stored,
        "gamma_angles_count": mg,
        "dimensions_mm": {"length": length_mm, "width": width_mm, "height": height_mm},
        "luminous_area_mm": {"length": lum_length_mm, "width": lum_width_mm},
        "downward_flux_fraction_pct": dff_pct,
        "lorl_pct": lorl_pct,
        "total_lamp_flux_lm": round(total_flux_lm, 1),
        "luminaire_output_flux_lm": luminaire_flux_lm,
        "total_wattage_w": round(total_wattage_w, 1),
        "efficacy_lm_w": efficacy,
        "cct_raw": cct_raw,
        "cri_raw": cri_raw,
        "direct_ratios": direct_ratios,
        "nadir_cd_per_klm": round(nadir_cd_klm, 1),
        "max_cd_per_klm": round(max_cd_klm, 1),
        "beam_angle_fwhm_deg": beam_angle_fwhm_deg,
        "estimated_ugr_ceiling": estimated_ugr,
        "glamox_decoded": glamox_info,
    }


def parse_iesna_ies(ies_content: str) -> dict[str, Any]:
    """
    Parse an IESNA LM-63 (`.ies`) photometric file into normalized photometric metrics.
    """
    lines = [ln.strip() for ln in str(ies_content or "").splitlines() if ln.strip()]
    if not lines:
        raise ValueError("Empty IESNA (.ies) content")

    header_version = (
        lines[0] if lines[0].upper().startswith("IESNA") else "IESNA:LM-63-2002"
    )
    keywords: dict[str, str] = {}
    tilt_idx = -1

    for i, ln in enumerate(lines):
        if ln.upper().startswith("TILT="):
            tilt_idx = i
            break
        m = re.match(r"^\[([A-Za-z0-9_]+)\]\s*(.*)$", ln)
        if m:
            key = m.group(1).upper()
            val = m.group(2).strip()
            keywords[key] = f"{keywords[key]} {val}".strip() if key in keywords else val

    if tilt_idx == -1:
        raise ValueError("Invalid IESNA (.ies) file: missing 'TILT=' marker")

    nums: list[float] = []
    for ln in lines[tilt_idx + 1 :]:
        for tok in ln.split():
            nums.append(_safe_float(tok, 0.0))

    if len(nums) < 13:
        raise ValueError(
            f"IESNA (.ies) numeric block requires at least 13 header numbers (got {len(nums)})"
        )

    num_lamps = max(1, int(nums[0]))
    lumens_per_lamp = nums[1]
    multiplier = nums[2]
    n_vertical = max(1, int(nums[3]))
    n_horizontal = max(1, int(nums[4]))
    photometric_type = int(nums[5])
    units_type = int(nums[6])  # 1 = feet, 2 = meters
    scale_to_mm = 304.8 if units_type == 1 else 1000.0
    width_mm = round(nums[7] * scale_to_mm, 1)
    length_mm = round(nums[8] * scale_to_mm, 1)
    height_mm = round(nums[9] * scale_to_mm, 1)
    wattage_w = nums[12] if nums[12] > 0 else 30.0

    v_start = 13
    v_angles = nums[v_start : v_start + n_vertical]
    h_start = v_start + n_vertical
    h_angles = nums[h_start : h_start + n_horizontal]
    c_start = h_start + n_horizontal
    candelas = [c * multiplier for c in nums[c_start:]]

    total_flux_lm = (
        lumens_per_lamp * num_lamps
        if lumens_per_lamp > 0
        else (max(candelas, default=1200.0) * math.pi)
    )
    max_cd = max(candelas, default=0.0)
    nadir_cd = candelas[0] if candelas else 0.0

    first_plane = candelas[:n_vertical] if len(candelas) >= n_vertical else candelas
    half_peak = max_cd * 0.5
    half_angle = 45.0
    if v_angles and len(first_plane) == len(v_angles):
        for v_ang, cd_val in zip(v_angles, first_plane):
            if cd_val <= half_peak and v_ang > 0:
                half_angle = v_ang
                break

    manufac = keywords.get("MANUFAC", "Unknown")
    lumcat = keywords.get("LUMCAT", "")
    luminaire_desc = keywords.get("LUMINAIRE", "")
    glamox_info = decode_glamox_code(f"{manufac} {lumcat} {luminaire_desc}")

    return {
        "format": "IESNA_IES",
        "header_version": header_version,
        "manufacturer": manufac,
        "catalog_number": lumcat,
        "luminaire_description": luminaire_desc,
        "photometric_type": photometric_type,
        "dimensions_mm": {"length": length_mm, "width": width_mm, "height": height_mm},
        "vertical_angles_count": n_vertical,
        "horizontal_angles_count": n_horizontal,
        "total_flux_lm": round(total_flux_lm, 1),
        "total_wattage_w": round(wattage_w, 1),
        "efficacy_lm_w": round(total_flux_lm / max(1.0, wattage_w), 1),
        "nadir_cd": round(nadir_cd, 1),
        "max_cd": round(max_cd, 1),
        "beam_angle_fwhm_deg": round(half_angle * 2.0, 1),
        "glamox_decoded": glamox_info,
    }


def parse_relux_or_dialux_project(content: str | dict[str, Any]) -> dict[str, Any]:
    """
    Parse a Relux (`.rdf` / XML / JSON / CSV) or DIALux (`.evo` XML / JSON / CSV)
    project export into a normalized project model with rooms, luminaire schedules,
    and decoded Glamox / DALI-2 hardware profiles.
    """
    if isinstance(content, dict):
        data = content
    else:
        raw = str(content or "").strip()
        if not raw:
            raise ValueError("Empty Relux/DIALux project content")
        if raw.startswith("{") or raw.startswith("["):
            parsed_json = json.loads(raw)
            data = (
                {"rooms": parsed_json} if isinstance(parsed_json, list) else parsed_json
            )
        elif raw.startswith("<"):
            data = _parse_relux_xml(raw)
        else:
            data = _parse_relux_csv(raw)

    project_name = str(
        data.get("project_name")
        or data.get("name")
        or "Relux Lighting & DALI-2 Project"
    )
    source_tool = str(data.get("source_tool") or "relux").lower()
    raw_rooms = data.get("rooms") or []

    normalized_rooms: list[dict[str, Any]] = []
    for idx, rm in enumerate(raw_rooms):
        room_id = str(rm.get("room_id") or rm.get("id") or f"RM-{idx + 1:02d}")
        room_name = str(rm.get("name") or f"Room {idx + 1}")
        length_m = _safe_float(rm.get("length_m", rm.get("length", 6.0)), 6.0)
        width_m = _safe_float(rm.get("width_m", rm.get("width", 4.0)), 4.0)
        height_m = _safe_float(rm.get("height_m", rm.get("height", 2.8)), 2.8)
        workplane_m = _safe_float(rm.get("workplane_m", 0.8), 0.8)
        zone_code = str(
            rm.get("zone_code") or rm.get("usage") or "OFFICE_WRITING"
        ).upper()
        maintenance_factor = _safe_float(rm.get("maintenance_factor", 0.80), 0.80)

        lum_list_raw = rm.get("luminaires") or []
        if not lum_list_raw and (rm.get("luminaire_code") or rm.get("luminaire")):
            lum_list_raw = [
                {
                    "code": rm.get("luminaire_code") or rm.get("luminaire"),
                    "quantity": rm.get("quantity", 1),
                    "flux_lm": rm.get("flux_lm"),
                    "wattage_w": rm.get("wattage_w"),
                }
            ]

        normalized_lums: list[dict[str, Any]] = []
        for lum in lum_list_raw:
            code = str(
                lum.get("code")
                or lum.get("model")
                or lum.get("name")
                or "Glamox C95-R 600x600 4000 DALI 840 MP"
            )
            decoded = decode_glamox_code(code)
            qty = max(1, _safe_int(lum.get("quantity", lum.get("count", 1)), 1))
            flux = _safe_float(lum.get("flux_lm"), decoded["flux_lm"])
            wattage = _safe_float(lum.get("wattage_w"), decoded["wattage_w"])
            ugr = _safe_float(lum.get("ugr"), decoded["ugr_rating"])
            normalized_lums.append(
                {
                    "code": code,
                    "quantity": qty,
                    "flux_lm": flux,
                    "wattage_w": wattage,
                    "ugr_rating": ugr,
                    "cri_ra": _safe_int(lum.get("cri_ra"), decoded["cri_ra"]),
                    "decoded": decoded,
                }
            )

        normalized_rooms.append(
            {
                "room_id": room_id,
                "name": room_name,
                "zone_code": zone_code,
                "length_m": length_m,
                "width_m": width_m,
                "height_m": height_m,
                "workplane_m": workplane_m,
                "maintenance_factor": maintenance_factor,
                "relux_em_lux": _safe_float(rm.get("em_lux"), 0.0) or None,
                "relux_u0": _safe_float(rm.get("u0"), 0.0) or None,
                "relux_ugr": _safe_float(rm.get("ugr"), 0.0) or None,
                "sensors_count": _safe_int(rm.get("sensors_count", 1), 1),
                "pushbuttons_count": _safe_int(rm.get("pushbuttons_count", 1), 1),
                "luminaires": normalized_lums,
            }
        )

    return {
        "project_name": project_name,
        "source_tool": source_tool,
        "rooms_count": len(normalized_rooms),
        "rooms": normalized_rooms,
    }


def _parse_relux_xml(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    proj_name = (
        root.attrib.get("name") or root.findtext("ProjectName") or "Relux XML Export"
    )
    rooms: list[dict[str, Any]] = []

    for r_el in root.findall(".//Room"):
        lums: list[dict[str, Any]] = []
        for l_el in r_el.findall(".//Luminaire"):
            lums.append(
                {
                    "code": l_el.attrib.get("code")
                    or l_el.findtext("Name")
                    or "Glamox C95-R 4000 DALI 840 MP",
                    "quantity": _safe_int(
                        l_el.attrib.get("quantity") or l_el.findtext("Quantity"), 1
                    ),
                    "flux_lm": _safe_float(
                        l_el.attrib.get("flux") or l_el.findtext("Flux"), 0.0
                    )
                    or None,
                    "wattage_w": _safe_float(
                        l_el.attrib.get("power") or l_el.findtext("Power"), 0.0
                    )
                    or None,
                }
            )
        rooms.append(
            {
                "room_id": r_el.attrib.get("id") or r_el.findtext("Id"),
                "name": r_el.attrib.get("name") or r_el.findtext("Name") or "Room",
                "zone_code": r_el.attrib.get("zone")
                or r_el.findtext("Zone")
                or "OFFICE_WRITING",
                "length_m": _safe_float(
                    r_el.attrib.get("length") or r_el.findtext("Length"), 6.0
                ),
                "width_m": _safe_float(
                    r_el.attrib.get("width") or r_el.findtext("Width"), 4.0
                ),
                "height_m": _safe_float(
                    r_el.attrib.get("height") or r_el.findtext("Height"), 2.8
                ),
                "em_lux": _safe_float(
                    r_el.attrib.get("em_lux") or r_el.findtext("EmLux"), 0.0
                )
                or None,
                "u0": _safe_float(r_el.attrib.get("u0") or r_el.findtext("U0"), 0.0)
                or None,
                "ugr": _safe_float(r_el.attrib.get("ugr") or r_el.findtext("UGR"), 0.0)
                or None,
                "luminaires": lums,
            }
        )

    return {"project_name": proj_name, "source_tool": "relux", "rooms": rooms}


def _parse_relux_csv(csv_text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    rooms_map: dict[str, dict[str, Any]] = {}
    for row in reader:
        r_name = str(
            row.get("room") or row.get("Room") or row.get("room_name") or "Room 1"
        ).strip()
        if r_name not in rooms_map:
            rooms_map[r_name] = {
                "name": r_name,
                "zone_code": row.get("zone_code")
                or row.get("zone")
                or "OFFICE_WRITING",
                "length_m": _safe_float(row.get("length_m") or row.get("length"), 6.0),
                "width_m": _safe_float(row.get("width_m") or row.get("width"), 4.0),
                "height_m": _safe_float(row.get("height_m") or row.get("height"), 2.8),
                "luminaires": [],
            }
        rooms_map[r_name]["luminaires"].append(
            {
                "code": row.get("luminaire")
                or row.get("luminaire_code")
                or "Glamox C95-R 4000 DALI 840 MP",
                "quantity": _safe_int(row.get("quantity") or row.get("qty"), 1),
                "flux_lm": _safe_float(row.get("flux_lm"), 0.0) or None,
                "wattage_w": _safe_float(row.get("wattage_w"), 0.0) or None,
            }
        )
    return {
        "project_name": "Relux CSV Schedule",
        "source_tool": "relux",
        "rooms": list(rooms_map.values()),
    }


def parse_dali_address_csv(csv_content: str) -> dict[str, Any]:
    """Parse a DALI-2 addressing / commissioning CSV table into structured universes and devices."""
    reader = csv.DictReader(io.StringIO(str(csv_content or "").strip()))
    devices: list[dict[str, Any]] = []
    for row in reader:
        devices.append(
            {
                "universe": _safe_int(row.get("universe") or row.get("line") or 1, 1),
                "short_address": _safe_int(
                    row.get("short_address") or row.get("address"), 0
                ),
                "address_type": str(
                    row.get("address_type") or row.get("type") or "ECG"
                ).upper(),
                "device_model": str(
                    row.get("device_model") or row.get("model") or "Glamox C95-R DALI"
                ),
                "group": _safe_int(row.get("group"), 0),
                "room": str(row.get("room") or ""),
            }
        )
    return {"total_devices": len(devices), "devices": devices}
