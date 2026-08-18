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

TWIST_LOCATIONS = [
    (0.0, "Leading Edge (0%)"),
    (0.25, "Quarter Chord (25% c)"),
    (0.50, "Half Chord (50%)"),
    (0.75, "Hinge Line (75%)"),
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
            ("washout", "Tip Twist / Washout (ε)", "°"),
        ]
    if mode == "span_root_tip":
        return [
            ("span", "Total Wingspan (b)", "mm"),
            ("root_chord", "Root Chord (c_root)", "mm"),
            ("tip_chord", "Tip Chord (c_tip)", "mm"),
            ("sweep", "Sweep Angle (Λ)", "°"),
            ("washout", "Tip Twist / Washout (ε)", "°"),
        ]
    if mode == "span_area_taper":
        return [
            ("span", "Total Wingspan (b)", "mm"),
            ("area", "Planform Area (S)", "mm²"),
            ("taper_ratio", "Taper Ratio (λ)", "1"),
            ("sweep", "Sweep Angle (Λ)", "°"),
            ("washout", "Tip Twist / Washout (ε)", "°"),
        ]
    if mode == "span_ar_taper":
        return [
            ("span", "Total Wingspan (b)", "mm"),
            ("aspect_ratio", "Aspect Ratio (AR)", "1"),
            ("taper_ratio", "Taper Ratio (λ)", "1"),
            ("sweep", "Sweep Angle (Λ)", "°"),
            ("washout", "Tip Twist / Washout (ε)", "°"),
        ]
    return []


def solve_wing_planform(
    mode: str,
    inputs: dict[str, float],
    current_profiles: list[dict[str, Any]],
    sweep_loc: float = 0.25,
    symmetric: bool = True,
    y_offset: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Solve wing planform dimensions, sweep angle, and scale profile stations accordingly.

    Returns:
        (new_profiles, calculated_metrics)
    """
    if mode == "manual" or not current_profiles:
        metrics = compute_planform_metrics(current_profiles, sweep_loc, symmetric, y_offset)
        return current_profiles, metrics

    # 1. Compute macro parameters
    abs_y_offset = abs(float(y_offset))

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
        taper = c_tip / max(c_root, 1e-6)
        if symmetric:
            b_semi = b / 2.0
            b_panel = max(b_semi - abs_y_offset, 1.0)
            s = b_panel * (c_root + c_tip) + 2.0 * abs_y_offset * c_root
        else:
            s = b * (c_root + c_tip) / 2.0
        ar = (b**2) / max(s, 1e-6)
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
        metrics = compute_planform_metrics(current_profiles, sweep_loc, symmetric, y_offset)
        return current_profiles, metrics

    sweep_deg = float(inputs.get("sweep", 0.0))
    sweep_rad = math.radians(sweep_deg)

    # 2. Determine target panel span
    if symmetric:
        b_semi_new = b / 2.0
        target_panel_span = max(b_semi_new - abs_y_offset, 1.0)
    else:
        target_panel_span = max(b, 1.0)

    # 3. Find old panel span from current profiles
    y_vals = [
        float(p.get("position", {}).get("y", 0.0))
        if isinstance(p.get("position"), dict) else 0.0
        for p in current_profiles
    ]
    y_root_old = min(y_vals) if y_vals else 0.0
    y_tip_old = max(y_vals) if y_vals else 0.0
    old_panel_span = max(y_tip_old - y_root_old, 1e-6)
    root_x0 = float(current_profiles[0].get("position", {}).get("x", 0.0)) if current_profiles else 0.0

    has_washout = "washout" in inputs
    washout_deg = float(inputs.get("washout", 0.0))
    root_pitch = (
        float(current_profiles[0].get("rotation", {}).get("y", 0.0))
        if current_profiles and isinstance(current_profiles[0].get("rotation"), dict)
        else 0.0
    )

    new_profiles = []
    for p in current_profiles:
        p_new = deepcopy(p)
        pos = p_new.get("position")
        if not isinstance(pos, dict):
            pos = {"x": 0.0, "y": 0.0, "z": 0.0}
            p_new["position"] = pos
        rot = p_new.get("rotation")
        if not isinstance(rot, dict):
            rot = {"x": 0.0, "y": 0.0, "z": 0.0}
            p_new["rotation"] = rot

        y_old = float(pos.get("y", 0.0))
        fraction = min(max((y_old - y_root_old) / old_panel_span, 0.0), 1.0)

        dy_new = fraction * target_panel_span
        pos["y"] = y_root_old + dy_new

        # Chord
        c_i = max(c_root + (c_tip - c_root) * fraction, 1.0)
        p_new["chord"] = c_i

        # Sweep X offset
        pos["x"] = root_x0 + dy_new * math.tan(sweep_rad) - sweep_loc * (c_i - c_root)

        # Washout (Pitch / Twist)
        if has_washout:
            rot["y"] = root_pitch + fraction * washout_deg

        new_profiles.append(p_new)

    metrics = compute_planform_metrics(new_profiles, sweep_loc, symmetric, y_offset)
    return new_profiles, metrics


def compute_planform_metrics(
    profiles: list[dict[str, Any]],
    sweep_loc: float = 0.25,
    symmetric: bool = True,
    y_offset: float = 0.0,
) -> dict[str, float]:
    """Calculate aerodynamic planform metrics, sweep angle, and washout for arbitrary multi-station profiles.

    Args:
        profiles: List of station profile dicts with local coordinates.
        sweep_loc: Chord fraction for sweep reference (e.g. 0.0 LE, 0.25 QC, 0.50 HC, 1.0 TE).
        symmetric: True if wing is mirrored across Y=0 plane (tip-to-tip span = 2*(|y_offset| + y_tip)).
        y_offset: Component attachment Y translation from centerline.
    """
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
            "washout": 0.0,
        }

    s_panel = 0.0
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
        s_panel += s_i
        mac_num += s_i * c_mac_i

    y_vals = [
        float(p.get("position", {}).get("y", 0.0))
        if isinstance(p.get("position"), dict) else 0.0
        for p in profiles
    ]
    y_root = min(y_vals)
    y_tip = max(y_vals)
    b_panel = max(y_tip - y_root, 0.0)
    c_root = float(profiles[0].get("chord", 0.0))
    c_tip = float(profiles[-1].get("chord", 0.0))
    taper = c_tip / max(c_root, 1e-6)

    abs_y_offset = abs(float(y_offset))

    if symmetric:
        # Tip-to-tip span including attachment Y offset and station tip
        b_semi = abs_y_offset + y_tip
        b_total = 2.0 * b_semi

        # Carry-through center section area between fuselage centerline and root
        center_gap = 2.0 * (abs_y_offset + y_root)
        s_center = center_gap * c_root
        s_total = 2.0 * s_panel + s_center
        mac_total = (2.0 * mac_num + s_center * c_root) / max(s_total, 1e-6) if s_total > 0 else 0.0
    else:
        # Asymmetric / single panel (e.g. vertical fin)
        b_total = b_panel
        s_total = s_panel
        mac_total = mac_num / max(s_panel, 1e-6) if s_panel > 0 else 0.0

    ar = (b_total**2) / max(s_total, 1e-6) if s_total > 0 else 0.0

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

    # Washout (tip pitch - root pitch)
    rot_root = profiles[0].get("rotation", {}) if isinstance(profiles[0].get("rotation"), dict) else {}
    rot_tip = profiles[-1].get("rotation", {}) if isinstance(profiles[-1].get("rotation"), dict) else {}
    root_pitch = float(rot_root.get("y", rot_root.get("pitch", 0.0)))
    tip_pitch = float(rot_tip.get("y", rot_tip.get("pitch", 0.0)))
    washout_deg = tip_pitch - root_pitch

    return {
        "area": s_total,
        "span": b_total,
        "aspect_ratio": ar,
        "taper_ratio": taper,
        "root_chord": c_root,
        "tip_chord": c_tip,
        "mac": mac_total,
        "sweep": sweep_deg,
        "washout": washout_deg,
    }
