"""
nce_verticals/lighting_dali/glamox_catalog.py
=============================================
Comprehensive Glamox Luminaire & DALI-2 Control System Reference Catalog,
Part-Number / Variant Suffix Decoder, and Room-Application Selector.

Covers:
1. Glamox Commercial Indoor Series (C95, C80, C77, C35, C52, D70, A65)
2. Glamox Industrial & Healthcare Series (i80, i40, i75, C90 Cleanroom)
3. Glamox Marine & Offshore Series (MAX Ex/ATEX, FX60, TL60, MIR - DNV certified)
4. Glamox DALI-2 Control Ecosystem:
   - Glamox Ethernet2DALI (IEC 62386-103 Multi-Line Application Controller)
   - Glamox DALI-2 PIR/Lux Multi-Sensor (IEC 62386-303 & 304)
   - Glamox DALI-2 4-Channel Pushbutton Interface (IEC 62386-301)
   - Glamox DALI-2 Bus Power Supply & Repeater
   - Glamox Wireless Radio / ActiveAhead / D4i Sensor-Ready (SR) variants
5. Deterministic Glamox Variant Code Parser (`decode_glamox_code`):
   Decodes strings such as `"Glamox C95-R 600x600 4000 DALI 840 MP EM 3H"` or
   `"C77-P 300x1200 4500 TWH 827-865 SI SEN"` into structured engineering specs.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Curated Glamox Luminaire Reference Library (Config-as-IP)
# ---------------------------------------------------------------------------

GLAMOX_LUMINAIRE_CATALOG: dict[str, dict[str, Any]] = {
    "C95-R": {
        "family": "C95",
        "model": "C95-R",
        "title": "Glamox C95-R Recessed Modular LED Luminaire",
        "mounting": "recessed",
        "category": "office_commercial",
        "ip_rating": "IP20/IP40",
        "ik_rating": "IK07",
        "ugr_rating": 19.0,
        "default_flux_lm": 4000.0,
        "default_wattage_w": 30.0,
        "efficacy_lm_w": 133.3,
        "cri_ra": 80,
        "cct_k": 4000,
        "optics": ["MP (Microprismatic UGR<=19)", "OP (Opal)", "CI (Circle)"],
        "dali2_device_types": [
            "DT6 (IEC 62386-207)",
            "DT8 Tunable White (IEC 62386-209)",
            "DT1 Emergency (IEC 62386-202)",
            "D4i / SR (IEC 62386-251..253)",
        ],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 21.0,
        "inrush_width_us": 180.0,
        "max_per_b16_mcb": 30,
        "max_per_c16_mcb": 50,
        "applications": [
            "OFFICE_WRITING",
            "MEETING_ROOM",
            "CLASSROOM",
            "CAD_WORKSTATION",
        ],
    },
    "C95-S": {
        "family": "C95",
        "model": "C95-S",
        "title": "Glamox C95-S Surface-Mounted LED Luminaire",
        "mounting": "surface",
        "category": "office_commercial",
        "ip_rating": "IP40",
        "ik_rating": "IK07",
        "ugr_rating": 19.0,
        "default_flux_lm": 4000.0,
        "default_wattage_w": 31.0,
        "efficacy_lm_w": 129.0,
        "cri_ra": 80,
        "cct_k": 4000,
        "optics": ["MP (Microprismatic UGR<=19)", "OP (Opal)"],
        "dali2_device_types": ["DT6", "DT8 Tunable White", "DT1 Emergency", "D4i / SR"],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 21.0,
        "inrush_width_us": 180.0,
        "max_per_b16_mcb": 30,
        "max_per_c16_mcb": 50,
        "applications": ["OFFICE_WRITING", "MEETING_ROOM", "CLASSROOM", "CORRIDOR"],
    },
    "C80-PR": {
        "family": "C80",
        "model": "C80-PR",
        "title": "Glamox C80-PR Linear Recessed/Pendant Architectural Profile",
        "mounting": "recessed_or_pendant",
        "category": "architectural_linear",
        "ip_rating": "IP20",
        "ik_rating": "IK02",
        "ugr_rating": 19.0,
        "default_flux_lm": 3500.0,
        "default_wattage_w": 27.0,
        "efficacy_lm_w": 129.6,
        "cri_ra": 80,
        "cct_k": 4000,
        "optics": [
            "MP (Microprismatic)",
            "OP (Opal)",
            "SL (Silver Matt Reflector)",
            "AS (Asymmetric)",
        ],
        "dali2_device_types": ["DT6", "DT8 Tunable White", "DT1 Emergency", "D4i / SR"],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 19.0,
        "inrush_width_us": 160.0,
        "max_per_b16_mcb": 32,
        "max_per_c16_mcb": 52,
        "applications": ["OFFICE_WRITING", "MEETING_ROOM", "RECEPTION", "CORRIDOR"],
    },
    "C77-R": {
        "family": "C77",
        "model": "C77-R",
        "title": "Glamox C77-R Ultra-Low Glare Office & Control Room Luminaire",
        "mounting": "recessed",
        "category": "office_low_glare",
        "ip_rating": "IP20",
        "ik_rating": "IK05",
        "ugr_rating": 16.0,
        "default_flux_lm": 4200.0,
        "default_wattage_w": 29.0,
        "efficacy_lm_w": 144.8,
        "cri_ra": 80,
        "cct_k": 4000,
        "optics": [
            "SI (Specular Darklight Reflector UGR<=16)",
            "MP (Microprismatic UGR<=19)",
        ],
        "dali2_device_types": ["DT6", "DT8 Tunable White", "DT1 Emergency", "D4i / SR"],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 20.0,
        "inrush_width_us": 175.0,
        "max_per_b16_mcb": 30,
        "max_per_c16_mcb": 50,
        "applications": [
            "CAD_WORKSTATION",
            "CONTROL_ROOM",
            "OFFICE_WRITING",
            "MEETING_ROOM",
        ],
    },
    "C77-P": {
        "family": "C77",
        "model": "C77-P",
        "title": "Glamox C77-P Direct/Indirect Pendant Office Luminaire",
        "mounting": "pendant",
        "category": "office_low_glare",
        "ip_rating": "IP20",
        "ik_rating": "IK05",
        "ugr_rating": 16.0,
        "default_flux_lm": 5200.0,
        "default_wattage_w": 36.0,
        "efficacy_lm_w": 144.4,
        "cri_ra": 80,
        "cct_k": 4000,
        "optics": ["SI (Specular Louver)", "MP (Microprismatic 50/50 Up/Down)"],
        "dali2_device_types": [
            "DT6 (1 or 2 DALI addresses for Up/Down)",
            "DT8 Tunable White",
            "D4i / SR",
        ],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 24.0,
        "inrush_width_us": 190.0,
        "max_per_b16_mcb": 26,
        "max_per_c16_mcb": 44,
        "applications": ["OFFICE_WRITING", "MEETING_ROOM", "CAD_WORKSTATION"],
    },
    "D70-R": {
        "family": "D70",
        "model": "D70-R",
        "title": "Glamox D70-R Architectural Recessed Downlight",
        "mounting": "recessed_downlight",
        "category": "downlight_circulation",
        "ip_rating": "IP55",
        "ik_rating": "IK07",
        "ugr_rating": 19.0,
        "default_flux_lm": 2200.0,
        "default_wattage_w": 18.0,
        "efficacy_lm_w": 122.2,
        "cri_ra": 80,
        "cct_k": 3000,
        "optics": [
            "SI (Specular Reflector)",
            "SM (Semi-Matt Reflector)",
            "WH (White Reflector)",
        ],
        "dali2_device_types": ["DT6", "DT8 Tunable White", "DT1 Emergency"],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 15.0,
        "inrush_width_us": 140.0,
        "max_per_b16_mcb": 38,
        "max_per_c16_mcb": 60,
        "applications": ["CORRIDOR", "RECEPTION", "MEETING_ROOM"],
    },
    "C90-R": {
        "family": "C90",
        "model": "C90-R",
        "title": "Glamox C90-R IP65 Cleanroom & Healthcare Luminaire",
        "mounting": "recessed",
        "category": "healthcare_cleanroom",
        "ip_rating": "IP65",
        "ik_rating": "IK08",
        "ugr_rating": 19.0,
        "default_flux_lm": 4500.0,
        "default_wattage_w": 34.0,
        "efficacy_lm_w": 132.4,
        "cri_ra": 90,
        "cct_k": 4000,
        "optics": [
            "MP (Tempered Glass + Microprismatic)",
            "OP (Tempered Glass + Opal)",
        ],
        "dali2_device_types": ["DT6", "DT8 Tunable White (Human Centric Lighting)"],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 24.0,
        "inrush_width_us": 200.0,
        "max_per_b16_mcb": 25,
        "max_per_c16_mcb": 42,
        "applications": ["HEALTHCARE_EXAM", "CLEANROOM", "LABORATORY"],
    },
    "i80": {
        "family": "i80",
        "model": "i80",
        "title": "Glamox i80 IP65 Industrial & Sport High-Bay Luminaire",
        "mounting": "high_bay_surface_or_suspended",
        "category": "industrial_highbay",
        "ip_rating": "IP65",
        "ik_rating": "IK10",
        "ugr_rating": 22.0,
        "default_flux_lm": 14000.0,
        "default_wattage_w": 92.0,
        "efficacy_lm_w": 152.2,
        "cri_ra": 80,
        "cct_k": 4000,
        "optics": ["NB (Narrow Beam)", "MB (Medium Beam)", "WB (Wide Beam)"],
        "dali2_device_types": ["DT6 (2x DALI Drivers for >16000lm variants)"],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 52.0,
        "inrush_width_us": 260.0,
        "max_per_b16_mcb": 10,
        "max_per_c16_mcb": 16,
        "applications": ["INDUSTRIAL_ASSEMBLY", "WAREHOUSE_HIGHBAY", "SPORTS_HALL"],
    },
    "i40": {
        "family": "i40",
        "model": "i40",
        "title": "Glamox i40 IP66/IP67 Industrial & Parking Linear Luminaire",
        "mounting": "surface_or_cable_tray",
        "category": "industrial_weatherproof",
        "ip_rating": "IP66/IP67",
        "ik_rating": "IK08",
        "ugr_rating": 25.0,
        "default_flux_lm": 5500.0,
        "default_wattage_w": 38.0,
        "efficacy_lm_w": 144.7,
        "cri_ra": 80,
        "cct_k": 4000,
        "optics": ["OP (Opal PC/Acrylic)"],
        "dali2_device_types": ["DT6", "DT1 Emergency"],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 24.0,
        "inrush_width_us": 190.0,
        "max_per_b16_mcb": 24,
        "max_per_c16_mcb": 40,
        "applications": ["INDUSTRIAL_ASSEMBLY", "TECHNICAL_ROOM", "PARKING_GARAGE"],
    },
    "MAX-EX": {
        "family": "MAX",
        "model": "MAX-EX",
        "title": "Glamox Aqua Signal MAX Ex Zone 1/2 Marine & Offshore Luminaire",
        "mounting": "ceiling_or_bulkhead",
        "category": "marine_offshore_atex",
        "ip_rating": "IP66/IP67",
        "ik_rating": "IK10",
        "ugr_rating": 25.0,
        "default_flux_lm": 4800.0,
        "default_wattage_w": 39.0,
        "efficacy_lm_w": 123.1,
        "cri_ra": 80,
        "cct_k": 4000,
        "optics": ["Clear Polycarbonate Diffuser (DNV & ATEX Ex db eb mb IIC T4 Gb)"],
        "dali2_device_types": ["DT6", "DT1 Emergency (3H Battery)"],
        "dali_bus_current_ma": 2.0,
        "inrush_peak_a": 26.0,
        "inrush_width_us": 210.0,
        "max_per_b16_mcb": 20,
        "max_per_c16_mcb": 34,
        "applications": [
            "MARINE_ENGINE_ROOM",
            "OFFSHORE_HAZARDOUS_EX",
            "INDUSTRIAL_ASSEMBLY",
        ],
    },
}

# ---------------------------------------------------------------------------
# Glamox DALI-2 Routers, Multi-Sensors & Input Devices (IEC 62386-103/301..304)
# ---------------------------------------------------------------------------

GLAMOX_CONTROL_DEVICES: dict[str, dict[str, Any]] = {
    "GLAMOX-ETH2DALI-3": {
        "sku": "GLAMOX-ETH2DALI-3",
        "name": "Glamox Ethernet2DALI 3-Line DALI-2 Application Controller",
        "iec_standard": "IEC 62386-101 / 103",
        "role": "application_controller_router",
        "dali_lines_per_unit": 3,
        "guaranteed_psu_current_ma_per_line": 240.0,
        "max_psu_current_ma_per_line": 250.0,
        "max_ecg_addresses_per_line": 64,
        "max_ecd_addresses_per_line": 64,
        "protocols": ["DALI-2", "BACnet/IP", "MQTT", "OPC-UA"],
        "mounting": "DIN-rail (6 TE)",
    },
    "GLAMOX-DALI2-MULTISENSOR-PIR": {
        "sku": "GLAMOX-DALI2-MULTISENSOR-PIR",
        "name": "Glamox DALI-2 Multi-Sensor (PIR Presence + Constant Light Control)",
        "iec_standard": "IEC 62386-103 / 303 (Occupancy) / 304 (Light Sensor)",
        "role": "input_device_sensor",
        "ecd_addresses_used": 1,
        "instances": ["303_OCCUPANCY_PIR", "304_LIGHT_LUX"],
        "dali_bus_current_ma": 6.0,
        "coverage_diameter_m_at_2_8m": 7.0,
        "coverage_area_m2": 38.5,
    },
    "GLAMOX-DALI2-HIGHBAY-SENSOR": {
        "sku": "GLAMOX-DALI2-HIGHBAY-SENSOR",
        "name": "Glamox DALI-2 High-Bay PIR + Lux Sensor (up to 16m mounting height)",
        "iec_standard": "IEC 62386-103 / 303 / 304",
        "role": "input_device_sensor",
        "ecd_addresses_used": 1,
        "instances": ["303_OCCUPANCY_PIR", "304_LIGHT_LUX"],
        "dali_bus_current_ma": 8.0,
        "coverage_diameter_m_at_10m": 14.0,
        "coverage_area_m2": 154.0,
    },
    "GLAMOX-DALI2-PB4": {
        "sku": "GLAMOX-DALI2-PB4",
        "name": "Glamox DALI-2 4-Input Pushbutton Coupler",
        "iec_standard": "IEC 62386-103 / 301 (Push Buttons)",
        "role": "input_device_switch",
        "ecd_addresses_used": 1,
        "instances": [
            "301_PUSHBUTTON_1",
            "301_PUSHBUTTON_2",
            "301_PUSHBUTTON_3",
            "301_PUSHBUTTON_4",
        ],
        "dali_bus_current_ma": 4.0,
    },
}


def decode_glamox_code(raw_code_or_description: str) -> dict[str, Any]:
    """
    Deterministic parser for Glamox luminaire designation strings from Relux, DIALux,
    schedules, or CAD blocks (e.g. `"Glamox C95-R 600x600 4000 DALI 840 MP EM 3H"`).
    """
    text = str(raw_code_or_description or "").strip()
    upper = text.upper()
    tokens = re.split(r"[\s,/;|]+", upper)

    # 1. Identify base Glamox model
    matched_model = None
    for model_key in GLAMOX_LUMINAIRE_CATALOG:
        if model_key in upper:
            matched_model = model_key
            break
    if not matched_model:
        fam_match = re.search(
            r"\b(C95|C90|C80|C77|C52|C35|C20|D70|D20|A65|I80|I75|I40|MAX|FX60|TL60)(?:-[A-Z0-9]+)?\b",
            upper,
        )
        if fam_match:
            candidate = fam_match.group(0)
            matched_model = (
                candidate
                if candidate in GLAMOX_LUMINAIRE_CATALOG
                else fam_match.group(1)
            )

    base_spec = GLAMOX_LUMINAIRE_CATALOG.get(matched_model or "", {})

    # 2. Extract dimensions (e.g. 600x600, 300x1200, 150x1500)
    dim_match = re.search(r"\b(\d{2,4})\s*[X*]\s*(\d{2,4})\b", upper)
    dimensions_mm = f"{dim_match.group(1)}x{dim_match.group(2)}" if dim_match else None

    # 3. Extract CRI & CCT code (e.g. 830, 840, 930, 940, 827-865)
    cri_ra = int(base_spec.get("cri_ra", 80))
    cct_k: int | str = int(base_spec.get("cct_k", 4000))
    tunable_white = False

    if re.search(r"\b(827-865|927-965|TWH|CCT|DT8)\b", upper):
        tunable_white = True
        cct_k = "2700-6500"
        if "927-965" in upper:
            cri_ra = 90
    else:
        cct_code_match = re.search(r"\b([89])(27|30|35|40|50|65)\b", upper)
        if cct_code_match:
            cri_ra = int(cct_code_match.group(1)) * 10
            cct_k = int(cct_code_match.group(2)) * 100

    # 4. Extract lumen package (e.g. 2500, 3500, 4000, 5200, 14000)
    flux_lm = float(base_spec.get("default_flux_lm", 4000.0))
    for tok in tokens:
        clean_num = re.sub(r"LM$", "", tok)
        if clean_num.isdigit():
            val = int(clean_num)
            if (
                val
                not in (
                    827,
                    830,
                    835,
                    840,
                    850,
                    865,
                    927,
                    930,
                    940,
                    965,
                    300,
                    600,
                    1200,
                    1500,
                )
                and 800 <= val <= 35000
            ):
                flux_lm = float(val)
                break

    # 5. Identify DALI-2 / Control Driver & Device Types
    dali_device_types: list[str] = []
    control_type = "ON_OFF_HF"
    if tunable_white or "DT8" in tokens:
        control_type = "DALI-2_DT8_TUNABLE_WHITE"
        dali_device_types.extend(["DT6 (IEC 62386-207)", "DT8 (IEC 62386-209)"])
    elif any(k in tokens for k in ("DALI", "DALI2", "DALI-2", "DA2", "DT6")):
        control_type = "DALI-2_DT6"
        dali_device_types.append("DT6 (IEC 62386-207)")
    elif "SR" in tokens or "D4I" in tokens:
        control_type = "DALI-2_D4i_SENSOR_READY"
        dali_device_types.extend(["DT6 (IEC 62386-207)", "D4i (IEC 62386-251..253)"])

    # 6. Identify Emergency Lighting (DT1 / 1H / 3H)
    has_emergency = bool(re.search(r"\b(EM|EM1H|EM3H|DA-EM|DT1|1H|3H|ST)\b", upper))
    emergency_duration_h = (
        3 if "3H" in upper else (1 if "1H" in upper else (3 if has_emergency else 0))
    )
    if has_emergency and ("DALI" in control_type or "DA-EM" in upper or "DT1" in upper):
        dali_device_types.append("DT1 Emergency (IEC 62386-202)")

    # 7. Identify Integrated Sensor (PIR / Lux / Wireless)
    has_integrated_sensor = bool(re.search(r"\b(SEN|PIR|MW|WLR|ACTIVEAHEAD)\b", upper))
    if has_integrated_sensor:
        dali_device_types.append("Part 303/304 Occupancy+Light Sensor")

    # 8. Identify Optic
    optic_code = "MP"
    for candidate_opt in ("MP", "OP", "SI", "SM", "SL", "AS", "NB", "MB", "WB", "CI"):
        if candidate_opt in tokens:
            optic_code = candidate_opt
            break

    efficacy = float(base_spec.get("efficacy_lm_w", 133.3))
    wattage_w = (
        round(flux_lm / efficacy, 1)
        if efficacy > 0
        else float(base_spec.get("default_wattage_w", 30.0))
    )

    # DALI short addresses consumed by this luminaire
    ecg_addresses = (1 if "DT6" in " ".join(dali_device_types) else 0) + (
        1 if "DT1" in " ".join(dali_device_types) else 0
    )
    ecd_addresses = 1 if has_integrated_sensor else 0
    bus_current_ma = (ecg_addresses * 2.0) + (ecd_addresses * 6.0)

    return {
        "raw_input": text,
        "is_glamox": bool("GLAMOX" in upper or matched_model),
        "family": base_spec.get("family", matched_model or "GENERIC"),
        "model": matched_model or "GENERIC_LED",
        "title": base_spec.get("title", text or "LED Luminaire"),
        "dimensions_mm": dimensions_mm,
        "optic_code": optic_code,
        "ugr_rating": 16.0
        if optic_code == "SI"
        else (19.0 if optic_code == "MP" else float(base_spec.get("ugr_rating", 22.0))),
        "flux_lm": flux_lm,
        "wattage_w": wattage_w,
        "efficacy_lm_w": round(flux_lm / max(1.0, wattage_w), 1),
        "cri_ra": cri_ra,
        "cct_k": cct_k,
        "tunable_white_dt8": tunable_white,
        "control_type": control_type,
        "dali2_device_types": dali_device_types,
        "has_emergency": has_emergency,
        "emergency_duration_h": emergency_duration_h,
        "has_integrated_sensor": has_integrated_sensor,
        "dali_ecg_addresses_per_unit": ecg_addresses,
        "dali_ecd_addresses_per_unit": ecd_addresses,
        "dali_bus_current_ma_per_unit": bus_current_ma,
        "inrush_peak_a": float(base_spec.get("inrush_peak_a", 21.0)),
        "max_per_b16_mcb": int(base_spec.get("max_per_b16_mcb", 30)),
        "max_per_c16_mcb": int(base_spec.get("max_per_c16_mcb", 50)),
    }


def recommend_glamox_luminaires(
    zone_code: str = "OFFICE_WRITING",
    *,
    require_tunable_white: bool = False,
    require_emergency_pct: float = 0.15,
) -> dict[str, Any]:
    """Recommend Glamox luminaire models and DALI-2 control devices for an EN 12464-1 zone."""
    z = str(zone_code or "OFFICE_WRITING").strip().upper()
    matches = [
        spec
        for spec in GLAMOX_LUMINAIRE_CATALOG.values()
        if z in spec.get("applications", [])
    ]
    if not matches:
        matches = [GLAMOX_LUMINAIRE_CATALOG["C95-R"], GLAMOX_LUMINAIRE_CATALOG["C77-R"]]

    primary = dict(matches[0])
    driver_suffix = "TWH 827-865" if require_tunable_white else "DALI 840"
    optic_suffix = "SI" if primary["ugr_rating"] <= 16.0 else "MP"
    recommended_part = f"Glamox {primary['model']} {int(primary['default_flux_lm'])} {driver_suffix} {optic_suffix}"

    return {
        "zone_code": z,
        "primary_recommendation": primary,
        "recommended_order_code": recommended_part,
        "emergency_variant_code": f"{recommended_part} DA-EM 3H",
        "emergency_ratio_recommended": require_emergency_pct,
        "alternative_models": [m["model"] for m in matches[1:]],
        "recommended_dali2_controls": [
            GLAMOX_CONTROL_DEVICES["GLAMOX-ETH2DALI-3"],
            GLAMOX_CONTROL_DEVICES["GLAMOX-DALI2-MULTISENSOR-PIR"],
            GLAMOX_CONTROL_DEVICES["GLAMOX-DALI2-PB4"],
        ],
    }
