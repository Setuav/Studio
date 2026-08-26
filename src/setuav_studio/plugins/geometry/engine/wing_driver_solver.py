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

    if "span" in drivers:
        span, c_root, c_tip = _solve_with_span_driver(
            drivers, v, c_root, c_tip, is_symmetric, y_offset
        )
    else:
        span, c_root, c_tip = _solve_without_span_driver(drivers, v, cur, is_symmetric, y_offset)

    return compute_all_8_parameters(
        span, c_root, c_tip, is_symmetric=is_symmetric, y_offset=y_offset
    )


def _solve_with_span_driver(
    drivers: set[str],
    values: dict[str, float],
    current_root: float,
    current_tip: float,
    is_symmetric: bool,
    y_offset: float,
) -> tuple[float, float, float]:
    span = values["span"]
    panel_span = max((span / 2.0 - y_offset) if is_symmetric else span, 1e-4)
    panel_factor = panel_span if is_symmetric else 0.5 * panel_span
    root_factor = panel_factor + (2.0 * y_offset if is_symmetric else 0.0)
    root, tip = current_root, current_tip

    if {"root_chord", "tip_chord"} <= drivers:
        root, tip = values["root_chord"], values["tip_chord"]
    elif {"root_chord", "taper_ratio"} <= drivers:
        root = values["root_chord"]
        tip = values["taper_ratio"] * root
    elif {"tip_chord", "taper_ratio"} <= drivers:
        tip = values["tip_chord"]
        root = tip / max(values["taper_ratio"], 1e-4)
    elif "taper_ratio" in drivers and ({"area", "aspect_ratio"} & drivers):
        area = _target_area(span, values, "area" in drivers)
        taper = values["taper_ratio"]
        root = area / max(root_factor + panel_factor * taper, 1e-6)
        tip = taper * root
    elif "root_chord" in drivers and ({"area", "aspect_ratio"} & drivers):
        root = values["root_chord"]
        area = _target_area(span, values, "area" in drivers)
        center = 2.0 * y_offset * root if is_symmetric else 0.0
        panel_area = (area - center) / (2.0 if is_symmetric else 1.0)
        tip = max(2.0 * max(panel_area / panel_span, 1e-4) - root, 1e-4)
    elif {"area", "tip_chord"} <= drivers:
        tip = values["tip_chord"]
        area = values["area"] * 10000.0
        root = max((area - panel_factor * tip) / max(root_factor, 1e-6), 1e-4)
    elif "taper_ratio" in drivers:
        tip = values["taper_ratio"] * root
    elif "root_chord" in drivers:
        root = values["root_chord"]
    elif "tip_chord" in drivers:
        tip = values["tip_chord"]
    return span, root, tip


def _target_area(span: float, values: dict[str, float], use_area: bool) -> float:
    if use_area:
        return values["area"] * 10000.0
    return span * span / max(values["aspect_ratio"], 1e-4)


def _solve_without_span_driver(
    drivers: set[str],
    values: dict[str, float],
    current: dict[str, float],
    is_symmetric: bool,
    y_offset: float,
) -> tuple[float, float, float]:
    span = current["span"]
    root = values.get("root_chord", current["root_chord"])
    tip = values.get("tip_chord", current["tip_chord"])
    if {"area", "aspect_ratio"} <= drivers:
        area = values["area"] * 10000.0
        span = math.sqrt(area * values["aspect_ratio"])
        return _chords_for_area(span, area, drivers, values, current, is_symmetric, y_offset)
    if {"area", "root_chord", "tip_chord"} <= drivers:
        return _span_for_area(values["area"] * 10000.0, root, tip, is_symmetric, y_offset)
    if {"area", "root_chord", "taper_ratio"} <= drivers:
        tip = values["taper_ratio"] * root
        return _span_for_area(values["area"] * 10000.0, root, tip, is_symmetric, y_offset)
    if {"aspect_ratio", "root_chord", "tip_chord"} <= drivers:
        return values["aspect_ratio"] * 0.5 * (root + tip), root, tip
    return span, root, tip


def _chords_for_area(
    span: float,
    area: float,
    drivers: set[str],
    values: dict[str, float],
    current: dict[str, float],
    is_symmetric: bool,
    y_offset: float,
) -> tuple[float, float, float]:
    panel_span = max((span / 2.0 - y_offset) if is_symmetric else span, 1e-4)
    panel_factor = panel_span if is_symmetric else 0.5 * panel_span
    root_factor = panel_factor + (2.0 * y_offset if is_symmetric else 0.0)
    if "taper_ratio" in drivers:
        taper = values["taper_ratio"]
        root = area / max(root_factor + panel_factor * taper, 1e-6)
        return span, root, taper * root
    if "root_chord" in drivers:
        root = values["root_chord"]
        center = 2.0 * y_offset * root if is_symmetric else 0.0
        panel_area = (area - center) / (2.0 if is_symmetric else 1.0)
        tip = max(2.0 * max(panel_area / panel_span, 1e-4) - root, 1e-4)
        return span, root, tip
    if "tip_chord" in drivers:
        tip = values["tip_chord"]
        root = max((area - panel_factor * tip) / max(root_factor, 1e-6), 1e-4)
        return span, root, tip
    taper = current["taper_ratio"]
    root = area / max(root_factor + panel_factor * taper, 1e-6)
    return span, root, taper * root


def _span_for_area(
    area: float, root: float, tip: float, is_symmetric: bool, y_offset: float
) -> tuple[float, float, float]:
    center = 2.0 * y_offset * root if is_symmetric else 0.0
    panel_area = max(area - center, 1e-4) / (2.0 if is_symmetric else 1.0)
    panel_span = panel_area / max(0.5 * (root + tip), 1e-6)
    span = 2.0 * (panel_span + y_offset) if is_symmetric else panel_span
    return span, root, tip
