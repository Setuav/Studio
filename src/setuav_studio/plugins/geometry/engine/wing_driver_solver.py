"""8-Variable 3-Driver OpenVSP Planform Solver.

Parameters (8 variables):
1. area (S, in dm²)
2. span (b, in mm)
3. aspect_ratio (AR)
4. taper_ratio (taper)
5. root_chord (c_root, in mm)
6. tip_chord (c_tip, in mm)
7. ave_chord (c_ave, in mm)
8. mac (c_mac, in mm)

Given ANY triplet of independent driver variables, solves for all 8 parameters.
"""

from __future__ import annotations

import math

PLANFORM_PARAM_KEYS = [
    "area",
    "span",
    "aspect_ratio",
    "taper_ratio",
    "root_chord",
    "tip_chord",
    "ave_chord",
    "mac",
]

PLANFORM_PARAM_LABELS = {
    "area": "Planform Area",
    "span": "Wingspan",
    "aspect_ratio": "Aspect Ratio",
    "taper_ratio": "Taper Ratio",
    "root_chord": "Root Chord",
    "tip_chord": "Tip Chord",
    "ave_chord": "Average Chord",
    "mac": "Mean Aerodyn Chord (MAC)",
}

PLANFORM_PARAM_UNITS = {
    "area": "dm²",
    "span": "mm",
    "aspect_ratio": "",
    "taper_ratio": "",
    "root_chord": "mm",
    "tip_chord": "mm",
    "ave_chord": "mm",
    "mac": "mm",
}


def compute_all_8_parameters(
    span: float,
    root_chord: float,
    tip_chord: float,
    *,
    is_symmetric: bool = True,
    y_offset: float = 0.0,
) -> dict[str, float]:
    """Compute all 8 planform parameters from geometric primitives (span, root_chord, tip_chord)."""
    b = max(float(span), 1e-4)
    c_root = max(float(root_chord), 1e-4)
    c_tip = max(float(tip_chord), 1e-4)

    c_ave = 0.5 * (c_root + c_tip)
    taper = c_tip / c_root

    # Single trapezoid panel span
    b_panel = (b / 2.0 - y_offset) if is_symmetric else b
    b_panel = max(b_panel, 1e-4)

    s_panel = c_ave * b_panel
    s_center = (2.0 * y_offset * c_root) if is_symmetric else 0.0
    s_total_mm2 = (2.0 * s_panel + s_center) if is_symmetric else s_panel

    ar = (b * b) / max(s_total_mm2, 1e-6)

    # Chords are clamped above, so the MAC denominator is always positive.
    mac = (2.0 / 3.0) * (c_root + c_tip - (c_root * c_tip) / (c_root + c_tip))

    # Area presented in dm² (1 dm² = 10,000 mm²)
    s_total_dm2 = s_total_mm2 / 10000.0

    return {
        "area": s_total_dm2,
        "span": b,
        "aspect_ratio": ar,
        "taper_ratio": taper,
        "root_chord": c_root,
        "tip_chord": c_tip,
        "ave_chord": c_ave,
        "mac": mac,
    }


def solve_8_parameter_driver(
    active_drivers: list[str] | set[str],
    inputs: dict[str, float],
    current_state: dict[str, float],
    *,
    is_symmetric: bool = True,
    y_offset: float = 0.0,
) -> dict[str, float]:
    """Universal 8-variable 3-driver solver for wings and sections."""
    drivers = set(active_drivers)
    cur = compute_all_8_parameters(
        current_state.get("span", 1000.0),
        current_state.get("root_chord", 200.0),
        current_state.get("tip_chord", 100.0),
        is_symmetric=is_symmetric,
        y_offset=y_offset,
    )

    # Values map with fallback to current
    v = {k: max(float(inputs.get(k, cur[k])), 1e-6) for k in PLANFORM_PARAM_KEYS}

    span = cur["span"]
    c_root = cur["root_chord"]
    c_tip = cur["tip_chord"]

    # 1. If span is an active driver
    if "span" in drivers:
        span = v["span"]
        b_panel = max((span / 2.0 - y_offset) if is_symmetric else span, 1e-4)
        panel_area_factor = b_panel if is_symmetric else 0.5 * b_panel
        root_area_factor = panel_area_factor + (2.0 * y_offset if is_symmetric else 0.0)

        if "root_chord" in drivers and "tip_chord" in drivers:
            c_root = v["root_chord"]
            c_tip = v["tip_chord"]
        elif "root_chord" in drivers and "taper_ratio" in drivers:
            c_root = v["root_chord"]
            c_tip = v["taper_ratio"] * c_root
        elif "tip_chord" in drivers and "taper_ratio" in drivers:
            c_tip = v["tip_chord"]
            c_root = c_tip / max(v["taper_ratio"], 1e-4)
        elif "area" in drivers and "taper_ratio" in drivers:
            s_target = v["area"] * 10000.0  # dm² to mm²
            taper = v["taper_ratio"]
            denom = root_area_factor + panel_area_factor * taper
            c_root = s_target / max(denom, 1e-6)
            c_tip = taper * c_root
        elif "aspect_ratio" in drivers and "taper_ratio" in drivers:
            s_target = (span * span) / max(v["aspect_ratio"], 1e-4)
            taper = v["taper_ratio"]
            denom = root_area_factor + panel_area_factor * taper
            c_root = s_target / max(denom, 1e-6)
            c_tip = taper * c_root
        elif "area" in drivers and "root_chord" in drivers:
            c_root = v["root_chord"]
            s_target = v["area"] * 10000.0
            s_center = (2.0 * y_offset * c_root) if is_symmetric else 0.0
            s_panel = (s_target - s_center) / (2.0 if is_symmetric else 1.0)
            c_ave = max(s_panel / b_panel, 1e-4)
            c_tip = max(2.0 * c_ave - c_root, 1e-4)
        elif "aspect_ratio" in drivers and "root_chord" in drivers:
            c_root = v["root_chord"]
            s_target = (span * span) / max(v["aspect_ratio"], 1e-4)
            s_center = (2.0 * y_offset * c_root) if is_symmetric else 0.0
            s_panel = (s_target - s_center) / (2.0 if is_symmetric else 1.0)
            c_ave = max(s_panel / b_panel, 1e-4)
            c_tip = max(2.0 * c_ave - c_root, 1e-4)
        elif "area" in drivers and "tip_chord" in drivers:
            c_tip = v["tip_chord"]
            s_target = v["area"] * 10000.0
            num = s_target - panel_area_factor * c_tip
            c_root = max(num / max(root_area_factor, 1e-6), 1e-4)
        else:
            if "taper_ratio" in drivers:
                taper = v["taper_ratio"]
                c_tip = taper * c_root
            elif "root_chord" in drivers:
                c_root = v["root_chord"]
            elif "tip_chord" in drivers:
                c_tip = v["tip_chord"]

    # 2. If span is NOT an active driver
    else:
        if "area" in drivers and "aspect_ratio" in drivers:
            s_target = v["area"] * 10000.0
            ar = v["aspect_ratio"]
            span = math.sqrt(s_target * ar)
            b_panel = max((span / 2.0 - y_offset) if is_symmetric else span, 1e-4)
            panel_area_factor = b_panel if is_symmetric else 0.5 * b_panel
            root_area_factor = panel_area_factor + (2.0 * y_offset if is_symmetric else 0.0)

            if "taper_ratio" in drivers:
                taper = v["taper_ratio"]
                denom = root_area_factor + panel_area_factor * taper
                c_root = s_target / max(denom, 1e-6)
                c_tip = taper * c_root
            elif "root_chord" in drivers:
                c_root = v["root_chord"]
                s_center = (2.0 * y_offset * c_root) if is_symmetric else 0.0
                s_panel = (s_target - s_center) / (2.0 if is_symmetric else 1.0)
                c_ave = max(s_panel / b_panel, 1e-4)
                c_tip = max(2.0 * c_ave - c_root, 1e-4)
            elif "tip_chord" in drivers:
                c_tip = v["tip_chord"]
                num = s_target - panel_area_factor * c_tip
                c_root = max(num / max(root_area_factor, 1e-6), 1e-4)
            else:
                taper = cur["taper_ratio"]
                denom = root_area_factor + panel_area_factor * taper
                c_root = s_target / max(denom, 1e-6)
                c_tip = taper * c_root
        elif "area" in drivers and "root_chord" in drivers and "tip_chord" in drivers:
            c_root = v["root_chord"]
            c_tip = v["tip_chord"]
            c_ave = 0.5 * (c_root + c_tip)
            s_target = v["area"] * 10000.0
            s_center = (2.0 * y_offset * c_root) if is_symmetric else 0.0
            s_panel = max(s_target - s_center, 1e-4) / (2.0 if is_symmetric else 1.0)
            b_panel = s_panel / max(c_ave, 1e-6)
            span = (2.0 * (b_panel + y_offset)) if is_symmetric else b_panel
        elif "area" in drivers and "root_chord" in drivers and "taper_ratio" in drivers:
            c_root = v["root_chord"]
            taper = v["taper_ratio"]
            c_tip = taper * c_root
            c_ave = 0.5 * (c_root + c_tip)
            s_target = v["area"] * 10000.0
            s_center = (2.0 * y_offset * c_root) if is_symmetric else 0.0
            s_panel = max(s_target - s_center, 1e-4) / (2.0 if is_symmetric else 1.0)
            b_panel = s_panel / max(c_ave, 1e-6)
            span = (2.0 * (b_panel + y_offset)) if is_symmetric else b_panel
        elif "aspect_ratio" in drivers and "root_chord" in drivers and "tip_chord" in drivers:
            c_root = v["root_chord"]
            c_tip = v["tip_chord"]
            c_ave = 0.5 * (c_root + c_tip)
            ar = v["aspect_ratio"]
            span = ar * c_ave
        else:
            c_root = v.get("root_chord", cur["root_chord"])
            c_tip = v.get("tip_chord", cur["tip_chord"])

    return compute_all_8_parameters(
        span, c_root, c_tip, is_symmetric=is_symmetric, y_offset=y_offset
    )
