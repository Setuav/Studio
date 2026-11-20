"""Planform measurements of a wing's profile stations and its sweep and twist references."""

from __future__ import annotations

import math
from typing import Any

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
        dx_ref = (xt - x0) - sweep_loc * (c_root - c_tip)
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
    root_pitch = float(rot_root.get("y", 0.0))
    tip_pitch = float(rot_tip.get("y", 0.0))
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
