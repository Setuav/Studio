"""Parametric Wing Sizing, Driver Groups, Multi-Station Scaling, and Sweep Engine.

Inspired by OpenVSP's non-destructive hierarchical driver architecture:
- Closed-loop mathematical consistency accounting for fuselage carry-through center area.
- Multi-station proportional morphing that preserves intermediate cranks, kinks, and dihedral angles.
- OpenVSP analytic sweep conversion formula across arbitrary chord reference lines.
"""

from __future__ import annotations

import math
from copy import deepcopy
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


def calc_tan_sweep_at(
    loc_target: float,
    sweep_deg: float,
    loc_base: float,
    aspect_ratio: float,
    taper_ratio: float,
) -> float:
    """Convert sweep angle between reference chord locations using OpenVSP analytic formula.

    Formula:
        tan(sweep_target) = tan(sweep_base) - [4 / (AR * (1 + taper))] * (loc_target - loc_base) * (1 - taper)

    Returns:
        float: Equivalent sweep angle in degrees at loc_target.
    """
    if aspect_ratio <= 1e-6:
        return sweep_deg
    taper_clamped = max(taper_ratio, 0.0)
    tan_base = math.tan(math.radians(sweep_deg))
    factor = (
        (4.0 / (aspect_ratio * (1.0 + taper_clamped)))
        * (loc_target - loc_base)
        * (1.0 - taper_clamped)
    )
    tan_target = tan_base - factor
    return math.degrees(math.atan(tan_target))


def solve_wing_planform(
    mode: str,
    inputs: dict[str, float],
    current_profiles: list[dict[str, Any]],
    sweep_loc: float = 0.25,
    symmetric: bool = True,
    y_offset: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Solve wing planform dimensions, sweep angle, and scale profile stations accordingly.

    Uses closed-loop math accounting for center carry-through area and preserves
    multi-station relative chord, spanwise spacing, and 3D dihedral distributions.

    Returns:
        (new_profiles, calculated_metrics)
    """
    if mode == "manual" or not current_profiles:
        metrics = compute_planform_metrics(current_profiles, sweep_loc, symmetric, y_offset)
        return current_profiles, metrics

    targets = _resolve_planform_targets(mode, inputs, symmetric, y_offset)
    if targets is None:
        metrics = compute_planform_metrics(current_profiles, sweep_loc, symmetric, y_offset)
        return current_profiles, metrics
    b_panel, c_root, c_tip = targets

    sweep_deg = float(inputs.get("sweep", 0.0))
    sweep_rad = math.radians(sweep_deg)

    # 2. Extract baseline profile station geometry
    y_vals = [
        float(p.get("position", {}).get("y", 0.0)) if isinstance(p.get("position"), dict) else 0.0
        for p in current_profiles
    ]
    z_vals = [
        float(p.get("position", {}).get("z", 0.0)) if isinstance(p.get("position"), dict) else 0.0
        for p in current_profiles
    ]
    chords_old = [max(float(p.get("chord", 0.0)), 1e-6) for p in current_profiles]

    y_root_old = min(y_vals) if y_vals else 0.0
    y_tip_old = max(y_vals) if y_vals else 0.0
    old_panel_span = max(y_tip_old - y_root_old, 1e-6)
    z_root_old = z_vals[0] if z_vals else 0.0
    root_x0 = (
        float(current_profiles[0].get("position", {}).get("x", 0.0)) if current_profiles else 0.0
    )

    c_root_old = chords_old[0] if chords_old else 1.0
    c_tip_old = chords_old[-1] if chords_old else 1.0
    delta_c_old = c_tip_old - c_root_old
    delta_c_new = c_tip - c_root

    has_washout = "washout" in inputs
    washout_deg = float(inputs.get("washout", 0.0))
    root_pitch = (
        float(current_profiles[0].get("rotation", {}).get("y", 0.0))
        if current_profiles and isinstance(current_profiles[0].get("rotation"), dict)
        else 0.0
    )
    tip_pitch_old = (
        float(current_profiles[-1].get("rotation", {}).get("y", 0.0))
        if current_profiles and isinstance(current_profiles[-1].get("rotation"), dict)
        else 0.0
    )
    washout_old = tip_pitch_old - root_pitch

    span_ratio = b_panel / old_panel_span

    # 3. Morph profiles to new macro planform
    n_profiles = len(current_profiles)
    new_profiles = []

    for i, p in enumerate(current_profiles):
        p_new = deepcopy(p)
        pos = p_new.setdefault("position", {"x": 0.0, "y": 0.0, "z": 0.0})
        rot = p_new.setdefault("rotation", {"x": 0.0, "y": 0.0, "z": 0.0})

        y_old = float(pos.get("y", 0.0))
        z_old = float(pos.get("z", 0.0))
        eta = min(max((y_old - y_root_old) / old_panel_span, 0.0), 1.0)

        # Updated Y position
        dy_new = eta * b_panel
        pos["y"] = y_root_old + dy_new

        # Dihedral-preserving Z scaling
        pos["z"] = z_root_old + (z_old - z_root_old) * span_ratio

        # Multi-station proportional chord morphing
        if i == 0:
            c_i = c_root
        elif i == n_profiles - 1:
            c_i = c_tip
        else:
            if abs(delta_c_old) > 1e-4:
                r_i = (chords_old[i] - c_root_old) / delta_c_old
                c_i = max(c_root + r_i * delta_c_new, 1.0)
            else:
                chord_ratio = c_root / max(c_root_old, 1e-6)
                c_i = max(chords_old[i] * chord_ratio, 1.0)

        p_new["chord"] = c_i

        # Sweep X offset (aligning reference chord fraction along the sweep ray)
        x_sweep_ray = root_x0 + dy_new * math.tan(sweep_rad) + sweep_loc * c_root
        pos["x"] = x_sweep_ray - sweep_loc * c_i

        # Washout (Twist distribution)
        if has_washout:
            if i == 0:
                rot["y"] = root_pitch
            elif i == n_profiles - 1:
                rot["y"] = root_pitch + washout_deg
            else:
                if abs(washout_old) > 1e-4:
                    w_i = (float(p.get("rotation", {}).get("y", 0.0)) - root_pitch) / washout_old
                    rot["y"] = root_pitch + w_i * washout_deg
                else:
                    rot["y"] = root_pitch + eta * washout_deg

        new_profiles.append(p_new)

    metrics = compute_planform_metrics(new_profiles, sweep_loc, symmetric, y_offset)
    return new_profiles, metrics


def _resolve_planform_targets(
    mode: str, inputs: dict[str, float], symmetric: bool, y_offset: float
) -> tuple[float, float, float] | None:
    offset = abs(float(y_offset))
    if mode == "area_ar_taper":
        area = max(float(inputs.get("area", 200000.0)), 100.0)
        aspect_ratio = max(float(inputs.get("aspect_ratio", 5.0)), 0.1)
        span = math.sqrt(area * aspect_ratio)
        taper = max(float(inputs.get("taper_ratio", 0.5)), 0.01)
        panel_span = _target_panel_span(span, symmetric, offset)
        root = _root_chord_for_area(area, panel_span, taper, symmetric, offset)
        return panel_span, root, taper * root
    if mode == "span_root_tip":
        span = max(float(inputs.get("span", 1000.0)), 10.0)
        return (
            _target_panel_span(span, symmetric, offset),
            max(float(inputs.get("root_chord", 200.0)), 1.0),
            max(float(inputs.get("tip_chord", 100.0)), 1.0),
        )
    if mode in {"span_area_taper", "span_ar_taper"}:
        span = max(float(inputs.get("span", 1000.0)), 10.0)
        taper = max(float(inputs.get("taper_ratio", 0.5)), 0.01)
        area = _target_planform_area(mode, inputs, span)
        panel_span = _target_panel_span(span, symmetric, offset)
        root = _root_chord_for_area(area, panel_span, taper, symmetric, offset)
        return panel_span, root, taper * root
    return None


def _target_planform_area(mode: str, inputs: dict[str, float], span: float) -> float:
    if mode == "span_area_taper":
        return max(float(inputs.get("area", 200000.0)), 100.0)
    aspect_ratio = max(float(inputs.get("aspect_ratio", 5.0)), 0.1)
    return span**2 / max(aspect_ratio, 1e-6)


def _target_panel_span(span: float, symmetric: bool, offset: float) -> float:
    return max(span / 2.0 - offset if symmetric else span, 1.0)


def _root_chord_for_area(
    area: float, panel_span: float, taper: float, symmetric: bool, offset: float
) -> float:
    if symmetric:
        return area / max(panel_span * (1.0 + taper) + 2.0 * offset, 1e-6)
    return 2.0 * area / max(panel_span * (1.0 + taper), 1e-6)


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
        float(p.get("position", {}).get("y", 0.0)) if isinstance(p.get("position"), dict) else 0.0
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
    pos_root = (
        profiles[0].get("position", {}) if isinstance(profiles[0].get("position"), dict) else {}
    )
    pos_tip = (
        profiles[-1].get("position", {}) if isinstance(profiles[-1].get("position"), dict) else {}
    )
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

    # Compute dihedral angle
    z0 = float(pos_root.get("z", 0.0))
    zt = float(pos_tip.get("z", 0.0))
    dihedral_deg = math.degrees(math.atan2(zt - z0, dy)) if dy > 1e-6 else 0.0

    # Washout (tip pitch - root pitch)
    rot_root = (
        profiles[0].get("rotation", {}) if isinstance(profiles[0].get("rotation"), dict) else {}
    )
    rot_tip = (
        profiles[-1].get("rotation", {}) if isinstance(profiles[-1].get("rotation"), dict) else {}
    )
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
        "dihedral": dihedral_deg,
        "washout": washout_deg,
    }


def set_wing_global_sweep(
    profiles: list[dict[str, Any]],
    sweep_deg: float,
    sweep_loc: float = 0.25,
    sweep_curvature: float = 0.0,
) -> list[dict[str, Any]]:
    """Set global wing sweep angle at sweep_loc with optional progressive spanwise curvature (scimitar curve)."""
    if len(profiles) < 2:
        return profiles

    new_profs = deepcopy(profiles)
    y0 = float(new_profs[0].get("position", {}).get("y", 0.0))
    yt = float(new_profs[-1].get("position", {}).get("y", 0.0))
    b_panel = max(abs(yt - y0), 1e-4)
    c0 = float(new_profs[0].get("chord", 0.0))
    x0 = float(new_profs[0].get("position", {}).get("x", 0.0))
    tan_sw = math.tan(math.radians(sweep_deg))

    for p in new_profs:
        pos = p.setdefault("position", {})
        y_i = float(pos.get("y", 0.0))
        c_i = float(p.get("chord", c0))
        dy = abs(y_i - y0)
        eta = dy / b_panel
        # Base linear sweep + progressive quadratic curvature (eta^2)
        dx_ref = dy * tan_sw + sweep_curvature * (eta**2)
        pos["x"] = x0 + dx_ref - sweep_loc * (c_i - c0)

    return new_profs


def set_wing_global_dihedral(
    profiles: list[dict[str, Any]],
    dihedral_deg: float,
) -> list[dict[str, Any]]:
    """Set global wing dihedral angle, adjusting all profile Z positions."""
    if len(profiles) < 2:
        return profiles

    new_profs = deepcopy(profiles)
    y0 = float(new_profs[0].get("position", {}).get("y", 0.0))
    z0 = float(new_profs[0].get("position", {}).get("z", 0.0))
    tan_dih = math.tan(math.radians(dihedral_deg))

    for p in new_profs:
        pos = p.setdefault("position", {})
        y_i = float(pos.get("y", 0.0))
        dy = abs(y_i - y0)
        pos["z"] = z0 + dy * tan_dih

    return new_profs


def set_wing_global_twist(
    profiles: list[dict[str, Any]],
    washout_deg: float,
) -> list[dict[str, Any]]:
    """Set global wing twist/washout linearly from root to tip."""
    if len(profiles) < 2:
        return profiles

    new_profs = deepcopy(profiles)
    y0 = float(new_profs[0].get("position", {}).get("y", 0.0))
    yt = float(new_profs[-1].get("position", {}).get("y", 0.0))
    span_panel = max(abs(yt - y0), 1e-4)

    rot0 = new_profs[0].setdefault("rotation", {})
    root_pitch = float(rot0.get("y", rot0.get("pitch", 0.0)))

    for p in new_profs:
        pos = p.setdefault("position", {})
        rot = p.setdefault("rotation", {})
        y_i = float(pos.get("y", 0.0))
        eta = abs(y_i - y0) / span_panel
        rot["y"] = root_pitch + eta * washout_deg

    return new_profs
