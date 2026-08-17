"""Parametric Wing Sizing, Driver Groups, and Sweep Calculation Engine."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any


DRIVER_MODES = [
    ("area_ar_taper", "Area, Aspect Ratio & Taper (S, AR, λ)"),
    ("span_root_tip", "Span, Root & Tip Chord (b, c_root, c_tip)"),
    ("span_area_taper", "Span, Area & Taper (b, S, λ)"),
    ("span_ar_taper", "Span, Aspect Ratio & Taper (b, AR, λ)"),
    ("manual", "Manual Station Editing"),
]

SWEEP_LOCATIONS = [
    (0.0, "Leading Edge (0%)"),
    (0.25, "Quarter Chord (25% MAC)"),
    (0.50, "Half Chord (50%)"),
    (1.0, "Trailing Edge (100%)"),
]


def get_driver_inputs_for_mode(mode: str) -> list[tuple[str, str, str]]:
    """Return list of (key, label, unit) for active inputs in the given driver mode."""
    if mode == "area_ar_taper":
        return [
            ("area", "Planform Area (S)", "mm²"),
            ("aspect_ratio", "Aspect Ratio (AR)", "1"),
            ("taper_ratio", "Taper Ratio (λ)", "1"),
            ("sweep", "Sweep Angle (Λ)", "°"),
        ]
    if mode == "span_root_tip":
        return [
            ("span", "Total Wingspan (b)", "mm"),
            ("root_chord", "Root Chord (c_root)", "mm"),
            ("tip_chord", "Tip Chord (c_tip)", "mm"),
            ("sweep", "Sweep Angle (Λ)", "°"),
        ]
    if mode == "span_area_taper":
        return [
            ("span", "Total Wingspan (b)", "mm"),
            ("area", "Planform Area (S)", "mm²"),
            ("taper_ratio", "Taper Ratio (λ)", "1"),
            ("sweep", "Sweep Angle (Λ)", "°"),
        ]
    if mode == "span_ar_taper":
        return [
            ("span", "Total Wingspan (b)", "mm"),
            ("aspect_ratio", "Aspect Ratio (AR)", "1"),
            ("taper_ratio", "Taper Ratio (λ)", "1"),
            ("sweep", "Sweep Angle (Λ)", "°"),
        ]
    return []


def solve_wing_planform(
    mode: str,
    inputs: dict[str, float],
    current_profiles: list[dict[str, Any]],
    sweep_loc: float = 0.25,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Solve wing planform dimensions, sweep angle, and scale profile stations accordingly.

    Returns:
        (new_profiles, calculated_metrics)
    """
    if mode == "manual" or not current_profiles:
        metrics = compute_planform_metrics(current_profiles, sweep_loc)
        return current_profiles, metrics

    # 1. Compute macro parameters
    if mode == "area_ar_taper":
        s = max(float(inputs.get("area", 200000.0)), 100.0)
        ar = max(float(inputs.get("aspect_ratio", 5.0)), 0.1)
        taper = max(float(inputs.get("taper_ratio", 0.5)), 0.01)
        b = math.sqrt(s * ar)
        c_root = (2.0 * s) / (b * (1.0 + taper))
        c_tip = taper * c_root
    elif mode == "span_root_tip":
        b = max(float(inputs.get("span", 1000.0)), 10.0)
        c_root = max(float(inputs.get("root_chord", 200.0)), 1.0)
        c_tip = max(float(inputs.get("tip_chord", 100.0)), 1.0)
        s = b * (c_root + c_tip) / 2.0
        ar = (b**2) / max(s, 1e-6)
        taper = c_tip / max(c_root, 1e-6)
    elif mode == "span_area_taper":
        b = max(float(inputs.get("span", 1000.0)), 10.0)
        s = max(float(inputs.get("area", 200000.0)), 100.0)
        taper = max(float(inputs.get("taper_ratio", 0.5)), 0.01)
        ar = (b**2) / max(s, 1e-6)
        c_root = (2.0 * s) / (b * (1.0 + taper))
        c_tip = taper * c_root
    elif mode == "span_ar_taper":
        b = max(float(inputs.get("span", 1000.0)), 10.0)
        ar = max(float(inputs.get("aspect_ratio", 5.0)), 0.1)
        taper = max(float(inputs.get("taper_ratio", 0.5)), 0.01)
        s = (b**2) / max(ar, 1e-6)
        c_root = (2.0 * s) / (b * (1.0 + taper))
        c_tip = taper * c_root
    else:
        metrics = compute_planform_metrics(current_profiles, sweep_loc)
        return current_profiles, metrics

    sweep_deg = float(inputs.get("sweep", 0.0))
    sweep_rad = math.radians(sweep_deg)
    b_semi_new = b / 2.0

    # 2. Find old semi-span from current profiles
    old_b_semi = max(
        abs(float(p.get("position", {}).get("y", 0.0)))
        if isinstance(p.get("position"), dict) else 0.0
        for p in current_profiles
    )
    old_b_semi = max(old_b_semi, 1e-6)
    root_x0 = float(current_profiles[0].get("position", {}).get("x", 0.0)) if current_profiles else 0.0

    # 3. Scale profiles with sweep equation:
    # x_LE,i = x_0 + dy * tan(sweep) - sweep_loc * (c_i - c_root)
    new_profiles = []
    for p in current_profiles:
        p_new = deepcopy(p)
        pos = p_new.get("position")
        if not isinstance(pos, dict):
            pos = {"x": 0.0, "y": 0.0, "z": 0.0}
            p_new["position"] = pos
        y_old = float(pos.get("y", 0.0))
        fraction = min(max(abs(y_old) / old_b_semi, 0.0), 1.0)
        sign = 1.0 if y_old >= 0 else -1.0

        dy_new = fraction * b_semi_new
        pos["y"] = sign * dy_new

        # Chord
        c_i = max(c_root + (c_tip - c_root) * fraction, 1.0)
        p_new["chord"] = c_i

        # Sweep X offset
        pos["x"] = root_x0 + dy_new * math.tan(sweep_rad) - sweep_loc * (c_i - c_root)
        new_profiles.append(p_new)

    mac = (2.0 / 3.0) * (c_root + c_tip - (c_root * c_tip) / max(c_root + c_tip, 1e-6))
    metrics = {
        "area": s,
        "span": b,
        "aspect_ratio": ar,
        "taper_ratio": taper,
        "root_chord": c_root,
        "tip_chord": c_tip,
        "mac": mac,
        "sweep": sweep_deg,
    }
    return new_profiles, metrics


def compute_planform_metrics(
    profiles: list[dict[str, Any]],
    sweep_loc: float = 0.25,
) -> dict[str, float]:
    """Calculate aerodynamic planform metrics and sweep angle for arbitrary multi-station profiles."""
    if len(profiles) < 2:
        return {
            "area": 0.0,
            "span": 0.0,
            "aspect_ratio": 0.0,
            "taper_ratio": 0.0,
            "root_chord": 0.0,
            "tip_chord": 0.0,
            "mac": 0.0,
            "sweep": 0.0,
        }

    s_semi = 0.0
    mac_num = 0.0
    for i in range(len(profiles) - 1):
        p0, p1 = profiles[i], profiles[i + 1]
        pos0 = p0.get("position", {}) if isinstance(p0.get("position"), dict) else {}
        pos1 = p1.get("position", {}) if isinstance(p1.get("position"), dict) else {}
        dy = abs(float(pos1.get("y", 0.0)) - float(pos0.get("y", 0.0)))
        c0 = max(float(p0.get("chord", 0.0)), 0.0)
        c1 = max(float(p1.get("chord", 0.0)), 0.0)
        s_i = 0.5 * (c0 + c1) * dy
        c_mac_i = (2.0 / 3.0) * (c0 + c1 - (c0 * c1) / max(c0 + c1, 1e-6))
        s_semi += s_i
        mac_num += s_i * c_mac_i

    b_semi = max(
        abs(float(p.get("position", {}).get("y", 0.0)))
        if isinstance(p.get("position"), dict) else 0.0
        for p in profiles
    )
    b_total = 2.0 * b_semi
    s_total = 2.0 * s_semi
    ar = (b_total**2) / max(s_total, 1e-6) if s_total > 0 else 0.0
    mac = mac_num / max(s_semi, 1e-6) if s_semi > 0 else 0.0
    c_root = float(profiles[0].get("chord", 0.0))
    c_tip = float(profiles[-1].get("chord", 0.0))
    taper = c_tip / max(c_root, 1e-6)

    # Compute sweep angle at sweep_loc
    pos_root = profiles[0].get("position", {}) if isinstance(profiles[0].get("position"), dict) else {}
    pos_tip = profiles[-1].get("position", {}) if isinstance(profiles[-1].get("position"), dict) else {}
    x0 = float(pos_root.get("x", 0.0))
    y0 = float(pos_root.get("y", 0.0))
    xt = float(pos_tip.get("x", 0.0))
    yt = float(pos_tip.get("y", 0.0))
    dy = abs(yt - y0)
    if dy > 1e-6:
        dx_ref = (xt - x0) + sweep_loc * (c_tip - c_root)
        sweep_deg = math.degrees(math.atan2(dx_ref, dy))
    else:
        sweep_deg = 0.0

    return {
        "area": s_total,
        "span": b_total,
        "aspect_ratio": ar,
        "taper_ratio": taper,
        "root_chord": c_root,
        "tip_chord": c_tip,
        "mac": mac,
        "sweep": sweep_deg,
    }
