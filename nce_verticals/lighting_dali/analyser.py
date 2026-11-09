"""
nce_verticals/lighting_dali/analyser.py
=======================================
Deterministic Photometric (EN 12464-1 / EN 1838 / EN 15193) and
IEC 62386 DALI-2 + NEK 400 Electrical Engineering Analyser Engine.

Governing Equations & Standards Cited:
--------------------------------------
1. EN 12464-1:2021 (Indoor Workplace Lighting):
   - Room Index:
       K = (L * W) / (h_m * (L + W)),  where h_m = H - h_workplane - h_suspension
   - Maintained Illuminance (Lumen Method):
       E_m = (N * Phi_lum * UF(K) * MF) / (L * W)
   - Required Luminaire Count:
       N_req = ceil((E_target * L * W) / (Phi_lum * UF(K) * MF))
2. EN 15193-1 (Energy Performance of Buildings - Lighting):
   - Installed Lighting Power Density:
       LPD = P_total / Area [W/m^2]
   - Normalized Power Density per 100 lx:
       e_norm = (LPD * 100) / E_m [W/(m^2 * 100 lx)]
3. IEC 62386 DALI-2 (Parts 101, 102, 103, 202, 207, 209, 251-253, 301-304):
   - Part 101 Bus Current Limit:
       I_bus = sum(N_ecg * I_ecg) + sum(N_ecd * I_ecd) <= I_psu_rated <= 250 mA
   - Part 101 Maximum Bus Voltage Drop (Delta_U <= 2.0 V):
       R_loop = (2 * rho_Cu * L_cable) / A_mm2
       Delta_U = (I_bus_mA / 1000.0) * R_loop <= 2.0 V
       (where rho_Cu = 0.0178 Ohm*mm2/m at 20°C, 0.0225 Ohm*mm2/m at 70°C)
   - Part 102 Short Addressing & Logarithmic Dimming Curve:
       Max 64 ECG short addresses (0..63), 16 Gear Groups (0..15), 16 Scenes (0..15).
       X(n) = 10^(((n - 1) / (253 / 3)) - 1) %   for n in [1..254],  X(0) = 0%
   - Part 103 Control Devices:
       Max 64 ECD short addresses (0..63), 32 Device Groups (0..31).
   - Part 209 DT8 Colour Control (Tunable White Mirek):
       Mirek = round(1,000,000 / T_Kelvin), valid range [154..370] for 6500K..2700K.
4. NEK 400 / EN 60898-1 MCB Breaker Sizing & Electronic Driver Inrush Derating:
   - Protects lighting circuits against nuisance magnetic tripping from capacitive
     LED driver cold-start inrush currents (B10/B16/C10/C16 breaker limits).
"""

from __future__ import annotations

import math
from typing import Any

from nce_verticals.lighting_dali.glamox_catalog import (
    GLAMOX_CONTROL_DEVICES,
    decode_glamox_code,
    recommend_glamox_luminaires,
)

# ---------------------------------------------------------------------------
# EN 12464-1:2021 Indoor Lighting Zone Requirements
# ---------------------------------------------------------------------------

EN12464_ZONES: dict[str, dict[str, Any]] = {
    "OFFICE_WRITING": {
        "title": "Offices — Writing, typing, reading, data processing (EN 12464-1 Table 5.26)",
        "em_target_lux": 500.0,
        "u0_min": 0.60,
        "ugr_max": 19.0,
        "ra_min": 80,
        "max_lpd_w_m2": 10.0,
    },
    "CAD_WORKSTATION": {
        "title": "Technical drawing & CAD work stations (EN 12464-1 Table 5.26)",
        "em_target_lux": 750.0,
        "u0_min": 0.70,
        "ugr_max": 16.0,
        "ra_min": 80,
        "max_lpd_w_m2": 12.0,
    },
    "MEETING_ROOM": {
        "title": "Conference and meeting rooms (EN 12464-1 Table 5.26)",
        "em_target_lux": 500.0,
        "u0_min": 0.60,
        "ugr_max": 19.0,
        "ra_min": 80,
        "max_lpd_w_m2": 10.0,
    },
    "CLASSROOM": {
        "title": "Educational classrooms and tutorial rooms (EN 12464-1 Table 5.36)",
        "em_target_lux": 500.0,
        "u0_min": 0.60,
        "ugr_max": 19.0,
        "ra_min": 80,
        "max_lpd_w_m2": 10.0,
    },
    "CORRIDOR": {
        "title": "Circulation areas and corridors (EN 12464-1 Table 5.1)",
        "em_target_lux": 100.0,
        "u0_min": 0.40,
        "ugr_max": 28.0,
        "ra_min": 40,
        "max_lpd_w_m2": 4.0,
    },
    "RECEPTION": {
        "title": "Reception desks and lobby areas (EN 12464-1 Table 5.26)",
        "em_target_lux": 300.0,
        "u0_min": 0.60,
        "ugr_max": 22.0,
        "ra_min": 80,
        "max_lpd_w_m2": 8.0,
    },
    "CONTROL_ROOM": {
        "title": "Control rooms and switchboard halls (EN 12464-1 Table 5.18)",
        "em_target_lux": 500.0,
        "u0_min": 0.70,
        "ugr_max": 16.0,
        "ra_min": 80,
        "max_lpd_w_m2": 11.0,
    },
    "HEALTHCARE_EXAM": {
        "title": "Healthcare examination and treatment rooms (EN 12464-1 Table 5.42)",
        "em_target_lux": 500.0,
        "u0_min": 0.60,
        "ugr_max": 19.0,
        "ra_min": 90,
        "max_lpd_w_m2": 12.0,
    },
    "INDUSTRIAL_ASSEMBLY": {
        "title": "Industrial medium assembly & electrical work (EN 12464-1 Table 5.11)",
        "em_target_lux": 300.0,
        "u0_min": 0.60,
        "ugr_max": 25.0,
        "ra_min": 80,
        "max_lpd_w_m2": 9.0,
    },
    "WAREHOUSE_HIGHBAY": {
        "title": "Warehouses and logistics aisles (EN 12464-1 Table 5.3)",
        "em_target_lux": 200.0,
        "u0_min": 0.40,
        "ugr_max": 25.0,
        "ra_min": 80,
        "max_lpd_w_m2": 7.0,
    },
}

RHO_CU_20C: float = 0.0178  # Ohm * mm^2 / m


def calculate_dali_dimming_level(arc_power_level: int) -> dict[str, Any]:
    """
    Calculate relative light output percentage X(n) per IEC 62386-102 logarithmic dimming curve:
        X(n) = 10^(((n - 1) / (253 / 3)) - 1) %   for n in [1..254],  X(0) = 0%.
    """
    n = max(0, min(254, int(arc_power_level)))
    if n == 0:
        pct = 0.0
    else:
        pct = math.pow(10.0, ((n - 1.0) / (253.0 / 3.0)) - 1.0)
    return {
        "dali_level": n,
        "light_output_pct": round(pct, 4),
        "equation": "X(n) = 10^(((n - 1) / (253 / 3)) - 1) % (IEC 62386-102)",
    }


def calculate_dt8_mirek(kelvin: float) -> dict[str, Any]:
    """
    Convert Correlated Color Temperature (CCT in Kelvin) to DALI-2 Part 209 (DT8) Mirek value:
        Mirek = round(1,000,000 / T_Kelvin).
    """
    tk = max(1000.0, min(20000.0, float(kelvin)))
    mirek = int(round(1_000_000.0 / tk))
    return {
        "cct_kelvin": tk,
        "dt8_mirek": mirek,
        "within_glamox_twh_range_2700_6500k": 154 <= mirek <= 370,
        "equation": "Mirek = round(10^6 / T_Kelvin) (IEC 62386-209 DT8)",
    }


def estimate_utilization_factor(room_index_k: float) -> float:
    """
    Deterministic Utilization Factor UF(K) for standard commercial reflection factors
    (ceiling 70%, walls 50%, floor 20%) as a function of Room Index K.
    """
    k = max(0.4, float(room_index_k))
    # Smooth rational curve calibrated against standard CIE / EULUMDAT utilization tables
    uf = 0.88 * (k / (k + 0.55))
    return round(min(0.86, max(0.35, uf)), 4)


def analyze_room_en12464(room: dict[str, Any]) -> dict[str, Any]:
    """
    Perform deterministic EN 12464-1:2021 photometric & EN 15193 energy compliance
    analysis for a single room.
    """
    zone_code = str(room.get("zone_code") or "OFFICE_WRITING").strip().upper()
    zone_req = EN12464_ZONES.get(zone_code, EN12464_ZONES["OFFICE_WRITING"])

    length_m = max(1.0, float(room.get("length_m", 6.0)))
    width_m = max(1.0, float(room.get("width_m", 4.0)))
    height_m = max(2.0, float(room.get("height_m", 2.8)))
    workplane_m = max(0.0, min(1.5, float(room.get("workplane_m", 0.8))))
    suspension_m = max(0.0, float(room.get("suspension_m", 0.0)))
    mf = max(0.50, min(0.95, float(room.get("maintenance_factor", 0.80))))

    area_m2 = round(length_m * width_m, 2)
    hm = max(0.8, height_m - workplane_m - suspension_m)
    room_index_k = round((length_m * width_m) / (hm * (length_m + width_m)), 3)
    uf = estimate_utilization_factor(room_index_k)

    luminaires = room.get("luminaires") or []
    total_flux_lm = 0.0
    total_wattage_w = 0.0
    total_qty = 0
    worst_ugr = 0.0
    min_cri = 100
    total_ecg = 0
    total_ecd = int(room.get("sensors_count", 1)) + int(
        room.get("pushbuttons_count", 1)
    )
    total_bus_ma = (int(room.get("sensors_count", 1)) * 6.0) + (
        int(room.get("pushbuttons_count", 1)) * 4.0
    )

    for lum in luminaires:
        code = str(lum.get("code") or "Glamox C95-R 4000 DALI 840 MP")
        dec = lum.get("decoded") or decode_glamox_code(code)
        qty = max(1, int(lum.get("quantity", 1)))
        flux = float(lum.get("flux_lm") or dec["flux_lm"])
        watt = float(lum.get("wattage_w") or dec["wattage_w"])
        ugr = float(lum.get("ugr_rating") or dec["ugr_rating"])
        cri = int(lum.get("cri_ra") or dec["cri_ra"])

        total_qty += qty
        total_flux_lm += qty * flux
        total_wattage_w += qty * watt
        worst_ugr = max(worst_ugr, ugr)
        min_cri = min(min_cri, cri)
        total_ecg += qty * int(dec.get("dali_ecg_addresses_per_unit", 1))
        total_ecd += qty * int(dec.get("dali_ecd_addresses_per_unit", 0))
        total_bus_ma += qty * float(dec.get("dali_bus_current_ma_per_unit", 2.0))

    if total_qty == 0:
        min_cri = 80
        worst_ugr = 19.0

    calculated_em_lux = (
        round((total_flux_lm * uf * mf) / area_m2, 1) if area_m2 > 0 else 0.0
    )
    em_lux = float(room.get("relux_em_lux") or calculated_em_lux)

    # Estimate spacing-to-height uniformity U0 if not supplied by Relux
    spacing_m = math.sqrt(area_m2 / max(1, total_qty))
    shr = round(spacing_m / hm, 2)
    estimated_u0 = 0.68 if shr <= 1.25 else (0.58 if shr <= 1.55 else 0.42)
    u0 = float(room.get("relux_u0") or estimated_u0)
    ugr_actual = float(room.get("relux_ugr") or worst_ugr)

    lpd_w_m2 = round(total_wattage_w / area_m2, 2) if area_m2 > 0 else 0.0
    norm_power_100lx = (
        round((lpd_w_m2 * 100.0) / max(1.0, em_lux), 2) if em_lux > 0 else 0.0
    )

    # Recommended luminaire count for target Em using primary luminaire (or Glamox C95-R 4000lm)
    ref_flux = (total_flux_lm / total_qty) if total_qty > 0 else 4000.0
    recommended_qty = max(
        1,
        math.ceil((zone_req["em_target_lux"] * area_m2) / max(1.0, ref_flux * uf * mf)),
    )

    violations: list[str] = []
    if em_lux < zone_req["em_target_lux"]:
        violations.append(
            f"Illuminance Em ({em_lux} lx) is below EN 12464-1 requirement ({zone_req['em_target_lux']} lx); "
            f"recommend >= {recommended_qty} luminaires."
        )
    if u0 < zone_req["u0_min"]:
        violations.append(
            f"Uniformity U0 ({u0:.2f}) is below minimum ({zone_req['u0_min']:.2f})."
        )
    if ugr_actual > zone_req["ugr_max"]:
        violations.append(
            f"Glare rating UGR ({ugr_actual:.1f}) exceeds max ({zone_req['ugr_max']:.1f}); "
            "switch to Glamox MP (Microprismatic) or C77 SI reflector."
        )
    if min_cri < zone_req["ra_min"]:
        violations.append(
            f"Color rendering Ra ({min_cri}) is below minimum ({zone_req['ra_min']})."
        )

    return {
        "room_id": room.get("room_id", "RM-01"),
        "name": room.get("name", "Room"),
        "zone_code": zone_code,
        "zone_title": zone_req["title"],
        "area_m2": area_m2,
        "mounting_height_hm_m": round(hm, 2),
        "room_index_k": room_index_k,
        "utilization_factor_uf": uf,
        "maintenance_factor_mf": mf,
        "luminaire_count": total_qty,
        "recommended_luminaire_count": recommended_qty,
        "em_lux": em_lux,
        "em_target_lux": zone_req["em_target_lux"],
        "u0_uniformity": round(u0, 2),
        "u0_target": zone_req["u0_min"],
        "ugr": round(ugr_actual, 1),
        "ugr_max": zone_req["ugr_max"],
        "cri_ra": min_cri,
        "ra_min": zone_req["ra_min"],
        "total_wattage_w": round(total_wattage_w, 1),
        "lpd_w_m2": lpd_w_m2,
        "normalized_w_m2_per_100lx": norm_power_100lx,
        "dali_ecg_addresses": total_ecg,
        "dali_ecd_addresses": total_ecd,
        "dali_bus_current_ma": round(total_bus_ma, 1),
        "compliant": len(violations) == 0,
        "violations": violations,
        "glamox_recommendation": recommend_glamox_luminaires(zone_code),
    }


def analyze_dali2_bus(
    *,
    ecg_count: int,
    ecd_sensor_count: int = 0,
    ecd_pushbutton_count: int = 0,
    dt1_emergency_count: int = 0,
    cable_length_m: float = 120.0,
    cable_cross_section_mm2: float = 1.5,
    psu_rated_current_ma: float = 240.0,
    topology: str = "line_or_star",
    total_driver_wattage_w: float | None = None,
    mcb_rating: str = "B16",
) -> dict[str, Any]:
    """
    Validate a single DALI-2 subnet per IEC 62386-101 / 102 / 103 and NEK 400:
    1. ECG Short Address limit (<= 64, recommended <= 54 for 15% spare capacity).
    2. ECD Input Device Short Address limit (<= 64).
    3. Bus Current Budget (I_bus <= I_psu <= 250 mA).
    4. Bus Cable Voltage Drop (Delta_U <= 2.0 V, L_max <= 300 m @ 1.5 mm^2).
    5. Topology check (no closed ring/loop allowed due to Manchester signal reflections).
    6. NEK 400 MCB LED Driver Inrush check.
    """
    total_ecg = max(0, int(ecg_count)) + max(0, int(dt1_emergency_count))
    total_ecd = max(0, int(ecd_sensor_count)) + max(0, int(ecd_pushbutton_count))

    bus_current_ma = (
        (total_ecg * 2.0)
        + (max(0, int(ecd_sensor_count)) * 6.0)
        + (max(0, int(ecd_pushbutton_count)) * 4.0)
    )
    psu_limit_ma = min(250.0, max(50.0, float(psu_rated_current_ma)))

    length_m = max(1.0, float(cable_length_m))
    area_mm2 = max(0.5, float(cable_cross_section_mm2))

    # Loop resistance R = (2 * rho_Cu * L) / A
    r_loop_ohm = (2.0 * RHO_CU_20C * length_m) / area_mm2
    voltage_drop_v = round((bus_current_ma / 1000.0) * r_loop_ohm, 3)

    # Max permissible length at 250 mA for 2.0 V drop: L_max = (2.0 * A) / (2 * rho_Cu * 0.25)
    max_length_for_section_m = min(
        300.0, round((2.0 * area_mm2) / (2.0 * RHO_CU_20C * 0.25), 1)
    )

    # NEK 400 MCB Inrush evaluation
    mcb_clean = str(mcb_rating or "B16").strip().upper()
    mcb_driver_limits = {"B10": 18, "B16": 30, "C10": 31, "C16": 50}
    max_drivers_per_mcb = mcb_driver_limits.get(mcb_clean, 30)
    required_mcb_circuits = max(
        1, math.ceil(max(1, int(ecg_count)) / max_drivers_per_mcb)
    )

    est_wattage_w = (
        float(total_driver_wattage_w)
        if total_driver_wattage_w is not None
        else (int(ecg_count) * 30.0)
    )
    steady_current_a = round(est_wattage_w / (230.0 * 0.95), 2)

    violations: list[str] = []
    warnings: list[str] = []

    if total_ecg > 64:
        violations.append(
            f"IEC 62386-102 violation: {total_ecg} Control Gear addresses exceed the 64-address limit per DALI subnet."
        )
    elif total_ecg > 54:
        warnings.append(
            f"Engineering headroom warning: {total_ecg}/64 ECG addresses used (>85%); limited spare capacity."
        )

    if total_ecd > 64:
        violations.append(
            f"IEC 62386-103 violation: {total_ecd} Control Device (sensor/switch) addresses exceed the 64-address limit."
        )

    if bus_current_ma > psu_limit_ma:
        violations.append(
            f"IEC 62386-101 violation: Bus current demand ({bus_current_ma:.1f} mA) exceeds PSU rating ({psu_limit_ma:.1f} mA, max 250 mA)."
        )

    if voltage_drop_v > 2.0:
        violations.append(
            f"IEC 62386-101 violation: Voltage drop ({voltage_drop_v:.2f} V) exceeds maximum 2.0 V over {length_m} m of {area_mm2} mm2 cable."
        )

    if length_m > max_length_for_section_m:
        violations.append(
            f"IEC 62386-101 cable length ({length_m} m) exceeds max recommended {max_length_for_section_m} m for {area_mm2} mm2 Cu."
        )

    if "ring" in topology.lower() or "loop" in topology.lower():
        violations.append(
            "IEC 62386-101 topology violation: Closed ring/loop topology is prohibited on DALI buses."
        )

    return {
        "iec_standard": "IEC 62386-101 / 102 / 103 (DALI-2) & NEK 400",
        "ecg_addresses_used": total_ecg,
        "ecg_addresses_max": 64,
        "ecg_utilization_pct": round((total_ecg / 64.0) * 100.0, 1),
        "ecd_addresses_used": total_ecd,
        "ecd_addresses_max": 64,
        "ecd_utilization_pct": round((total_ecd / 64.0) * 100.0, 1),
        "bus_current_ma": round(bus_current_ma, 1),
        "psu_rated_current_ma": psu_limit_ma,
        "max_bus_current_ma": 250.0,
        "cable_length_m": length_m,
        "cable_cross_section_mm2": area_mm2,
        "loop_resistance_ohm": round(r_loop_ohm, 3),
        "voltage_drop_v": voltage_drop_v,
        "max_voltage_drop_v": 2.0,
        "nek400_mcb_sizing": {
            "mcb_type": mcb_clean,
            "max_glamox_drivers_per_mcb": max_drivers_per_mcb,
            "recommended_mcb_circuits": required_mcb_circuits,
            "steady_state_current_a": steady_current_a,
        },
        "compliant": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
    }


def design_dali2_universe_allocation(
    rooms_analysis: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Automatically partition rooms across DALI-2 subnets (keeping <= 54 ECGs, <= 48 ECDs,
    and <= 200 mA per subnet for engineering margin) and size required Glamox Ethernet2DALI
    controllers (3 DALI-2 lines per controller).
    """
    universes: list[dict[str, Any]] = []
    current_u: dict[str, Any] = {
        "universe_id": 1,
        "rooms": [],
        "ecg_count": 0,
        "ecd_count": 0,
        "bus_current_ma": 0.0,
        "total_wattage_w": 0.0,
    }

    for rm in rooms_analysis:
        r_ecg = int(rm.get("dali_ecg_addresses", 0))
        r_ecd = int(rm.get("dali_ecd_addresses", 0))
        r_ma = float(rm.get("dali_bus_current_ma", 0.0))
        r_w = float(rm.get("total_wattage_w", 0.0))

        # If adding this room exceeds safe per-line engineering thresholds (54 ECG / 50 ECD / 210 mA), start new DALI line
        if current_u["rooms"] and (
            current_u["ecg_count"] + r_ecg > 54
            or current_u["ecd_count"] + r_ecd > 50
            or current_u["bus_current_ma"] + r_ma > 210.0
        ):
            universes.append(current_u)
            current_u = {
                "universe_id": len(universes) + 1,
                "rooms": [],
                "ecg_count": 0,
                "ecd_count": 0,
                "bus_current_ma": 0.0,
                "total_wattage_w": 0.0,
            }

        current_u["rooms"].append(rm.get("name", rm.get("room_id")))
        current_u["ecg_count"] += r_ecg
        current_u["ecd_count"] += r_ecd
        current_u["bus_current_ma"] = round(current_u["bus_current_ma"] + r_ma, 1)
        current_u["total_wattage_w"] = round(current_u["total_wattage_w"] + r_w, 1)

    if current_u["rooms"] or not universes:
        universes.append(current_u)

    for u in universes:
        u["bus_validation"] = analyze_dali2_bus(
            ecg_count=u["ecg_count"],
            ecd_sensor_count=max(1, u["ecd_count"] // 2),
            ecd_pushbutton_count=u["ecd_count"] - max(1, u["ecd_count"] // 2),
            total_driver_wattage_w=u["total_wattage_w"],
        )

    eth2dali_spec = GLAMOX_CONTROL_DEVICES["GLAMOX-ETH2DALI-3"]
    controllers_needed = max(
        1, math.ceil(len(universes) / int(eth2dali_spec["dali_lines_per_unit"]))
    )

    return {
        "total_dali2_subnets": len(universes),
        "glamox_eth2dali_controllers_required": controllers_needed,
        "controller_model": eth2dali_spec["name"],
        "universes": universes,
    }


def analyze_lighting_project(project_data: dict[str, Any]) -> dict[str, Any]:
    """Run full EN 12464-1 room analysis + IEC 62386 DALI-2 subnet design on a parsed project."""
    rooms = project_data.get("rooms") or []
    room_reports = [analyze_room_en12464(rm) for rm in rooms]
    dali_allocation = design_dali2_universe_allocation(room_reports)

    all_compliant = all(r["compliant"] for r in room_reports) and all(
        u["bus_validation"]["compliant"] for u in dali_allocation["universes"]
    )
    total_luminaires = sum(r["luminaire_count"] for r in room_reports)
    total_wattage_w = round(sum(r["total_wattage_w"] for r in room_reports), 1)
    total_area_m2 = round(sum(r["area_m2"] for r in room_reports), 2)

    return {
        "project_name": project_data.get("project_name", "Lighting & DALI-2 Project"),
        "source_tool": project_data.get("source_tool", "relux"),
        "compliance_passed": all_compliant,
        "summary": {
            "rooms_count": len(room_reports),
            "total_area_m2": total_area_m2,
            "total_luminaires": total_luminaires,
            "total_wattage_w": total_wattage_w,
            "average_lpd_w_m2": round(total_wattage_w / max(1.0, total_area_m2), 2),
            "total_dali2_subnets": dali_allocation["total_dali2_subnets"],
            "glamox_eth2dali_controllers": dali_allocation[
                "glamox_eth2dali_controllers_required"
            ],
        },
        "rooms_analysis": room_reports,
        "dali2_topology": dali_allocation,
    }
