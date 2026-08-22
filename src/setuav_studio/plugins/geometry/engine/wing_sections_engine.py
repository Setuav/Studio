"""Section-Based Kinematic Wing Engine (OpenVSP-style connected panels).

Converts between discrete profile stations and linked parametric wing sections (panels).
Every section (panel i) automatically links its root to the previous section's tip:
- Section i+1 root position == Section i tip position.
- Section i+1 root chord == Section i tip chord.
- Section i+1 root twist/dihedral == Section i tip twist/dihedral.

Includes Section-Level Driver Groups and Global OpenVSP Total Scaling (fract).
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any


SECTION_DRIVER_MODES: list[tuple[str, str]] = [
    ("span_root_tip", "Span, Root & Tip Chord"),
    ("area_ar_taper", "Area, AR & Taper Ratio"),
    ("span_area_taper", "Span, Area & Taper Ratio"),
    ("span_ar_taper", "Span, AR & Taper Ratio"),
]


def profiles_to_sections(
    profiles: list[dict[str, Any]],
    sweep_loc: float = 0.25,
) -> list[dict[str, Any]]:
    """Convert absolute profile stations into linked parametric wing sections."""
    if len(profiles) < 2:
        return []

    sections: list[dict[str, Any]] = []
    for i in range(len(profiles) - 1):
        p0 = profiles[i]
        p1 = profiles[i + 1]

        pos0 = p0.get("position", {}) if isinstance(p0.get("position"), dict) else {}
        pos1 = p1.get("position", {}) if isinstance(p1.get("position"), dict) else {}
        rot0 = p0.get("rotation", {}) if isinstance(p0.get("rotation"), dict) else {}
        rot1 = p1.get("rotation", {}) if isinstance(p1.get("rotation"), dict) else {}

        x0, y0, z0 = float(pos0.get("x", 0.0)), float(pos0.get("y", 0.0)), float(pos0.get("z", 0.0))
        x1, y1, z1 = float(pos1.get("x", 0.0)), float(pos1.get("y", 0.0)), float(pos1.get("z", 0.0))

        c0 = max(float(p0.get("chord", 200.0)), 1.0)
        c1 = max(float(p1.get("chord", 100.0)), 1.0)

        dy = abs(y1 - y0)
        dz = z1 - z0
        dx = x1 - x0

        # Section Dihedral Angle
        dihedral_deg = math.degrees(math.atan2(dz, max(dy, 1e-6)))

        # Section Sweep Angle at sweep_loc
        dx_ref = dx + sweep_loc * (c1 - c0)
        sweep_deg = math.degrees(math.atan2(dx_ref, max(dy, 1e-6)))

        # Section Twist Increment
        pitch0 = float(rot0.get("y", 0.0))
        pitch1 = float(rot1.get("y", 0.0))
        twist_deg = pitch1 - pitch0

        # Section planform metrics
        area_panel = 0.5 * (c0 + c1) * dy
        area_sym = 2.0 * area_panel
        ar = (4.0 * dy) / (c0 + c1) if (c0 + c1) > 1e-4 else 8.0
        taper = c1 / c0

        sections.append({
            "index": i,
            "span": dy,
            "root_chord": c0,
            "tip_chord": c1,
            "area": area_sym,
            "aspect_ratio": ar,
            "taper_ratio": taper,
            "sweep": sweep_deg,
            "dihedral": dihedral_deg,
            "twist": twist_deg,
            "root_airfoil": deepcopy(p0.get("airfoil", "2412")),
            "tip_airfoil": deepcopy(p1.get("airfoil", "2412")),
            "driver_mode": "span_root_tip",
        })

    return sections


def compute_section_planform_metrics(
    sec: dict[str, Any],
) -> dict[str, float]:
    """Compute planform metrics for a single trapezoidal wing section."""
    span = max(float(sec.get("span", 200.0)), 1e-4)
    c_root = max(float(sec.get("root_chord", 200.0)), 1e-4)
    c_tip = max(float(sec.get("tip_chord", 100.0)), 1e-4)

    area_panel = 0.5 * (c_root + c_tip) * span
    area_sym = 2.0 * area_panel
    ar = (4.0 * span) / (c_root + c_tip) if (c_root + c_tip) > 1e-4 else 8.0
    taper = c_tip / c_root
    ave_c = 0.5 * (c_root + c_tip)
    mac = (2.0 / 3.0) * (c_root + c_tip - (c_root * c_tip) / (c_root + c_tip))

    return {
        "span": span,
        "area": area_sym,
        "aspect_ratio": ar,
        "taper_ratio": taper,
        "root_chord": c_root,
        "tip_chord": c_tip,
        "ave_chord": ave_c,
        "mac": mac,
    }


def solve_section_driver(
    mode: str,
    inputs: dict[str, float],
    current_sec: dict[str, Any],
) -> dict[str, float]:
    """Solve section geometry given 3 active driver variables (OpenVSP WingDriverGroup style)."""
    curr_metrics = compute_section_planform_metrics(current_sec)

    if mode == "area_ar_taper":
        s_sym = max(float(inputs.get("area", curr_metrics["area"])), 1.0)
        ar = max(float(inputs.get("aspect_ratio", curr_metrics["aspect_ratio"])), 0.1)
        taper = max(float(inputs.get("taper_ratio", curr_metrics["taper_ratio"])), 0.001)
        span = math.sqrt(0.25 * s_sym * ar)
        c_root = s_sym / (span * (1.0 + taper))
        c_tip = taper * c_root
    elif mode == "span_root_tip":
        span = max(float(inputs.get("span", curr_metrics["span"])), 1.0)
        c_root = max(float(inputs.get("root_chord", curr_metrics["root_chord"])), 1.0)
        c_tip = max(float(inputs.get("tip_chord", curr_metrics["tip_chord"])), 1.0)
    elif mode == "span_area_taper":
        span = max(float(inputs.get("span", curr_metrics["span"])), 1.0)
        s_sym = max(float(inputs.get("area", curr_metrics["area"])), 1.0)
        taper = max(float(inputs.get("taper_ratio", curr_metrics["taper_ratio"])), 0.001)
        c_root = s_sym / (span * (1.0 + taper))
        c_tip = taper * c_root
    elif mode == "span_ar_taper":
        span = max(float(inputs.get("span", curr_metrics["span"])), 1.0)
        ar = max(float(inputs.get("aspect_ratio", curr_metrics["aspect_ratio"])), 0.1)
        taper = max(float(inputs.get("taper_ratio", curr_metrics["taper_ratio"])), 0.001)
        s_sym = (4.0 * span * span) / ar
        c_root = s_sym / (span * (1.0 + taper))
        c_tip = taper * c_root
    else:
        span = max(float(inputs.get("span", curr_metrics["span"])), 1.0)
        c_root = max(float(inputs.get("root_chord", curr_metrics["root_chord"])), 1.0)
        c_tip = max(float(inputs.get("tip_chord", curr_metrics["tip_chord"])), 1.0)

    temp_sec = {"span": span, "root_chord": c_root, "tip_chord": c_tip}
    return compute_section_planform_metrics(temp_sec)


def sections_to_profiles(
    sections: list[dict[str, Any]],
    root_profile: dict[str, Any] | None = None,
    sweep_loc: float = 0.25,
) -> list[dict[str, Any]]:
    """Construct full kinematic chain of profile stations from linked wing sections."""
    if not sections:
        return []

    # 1. Base root station (Station 0)
    if root_profile is not None:
        p0 = deepcopy(root_profile)
        p0.setdefault("position", {"x": 0.0, "y": 0.0, "z": 0.0})
        p0.setdefault("rotation", {"x": 0.0, "y": 0.0, "z": 0.0})
        p0["chord"] = float(sections[0].get("root_chord", 200.0))
        p0["airfoil"] = deepcopy(sections[0].get("root_airfoil", p0.get("airfoil", "2412")))
    else:
        p0 = {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "chord": float(sections[0].get("root_chord", 200.0)),
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "airfoil": deepcopy(sections[0].get("root_airfoil", "2412")),
        }

    profiles: list[dict[str, Any]] = [p0]

    # 2. Iteratively build connected stations along the chain
    curr_x = float(p0["position"].get("x", 0.0))
    curr_y = float(p0["position"].get("y", 0.0))
    curr_z = float(p0["position"].get("z", 0.0))
    curr_pitch = float(p0["rotation"].get("y", 0.0))
    curr_roll = float(p0["rotation"].get("x", 0.0))
    curr_yaw = float(p0["rotation"].get("z", 0.0))

    for sec in sections:
        span = max(float(sec.get("span", 200.0)), 1.0)
        c_root = float(sec.get("root_chord", 200.0))
        c_tip = max(float(sec.get("tip_chord", 100.0)), 1.0)
        sweep_rad = math.radians(float(sec.get("sweep", 0.0)))
        dihedral_rad = math.radians(float(sec.get("dihedral", 0.0)))
        twist = float(sec.get("twist", 0.0))

        # Tip point coordinates derived from section geometry
        next_y = curr_y + span
        next_z = curr_z + span * math.tan(dihedral_rad)
        dx_ref = span * math.tan(sweep_rad)
        next_x = curr_x + dx_ref - sweep_loc * (c_tip - c_root)
        next_pitch = curr_pitch + twist

        p_next = {
            "position": {
                "x": next_x,
                "y": next_y,
                "z": next_z,
            },
            "chord": c_tip,
            "rotation": {
                "x": curr_roll,
                "y": next_pitch,
                "z": curr_yaw,
            },
            "airfoil": deepcopy(sec.get("tip_airfoil", "2412")),
        }
        profiles.append(p_next)

        # Advance current state to this section's tip
        curr_x = next_x
        curr_y = next_y
        curr_z = next_z
        curr_pitch = next_pitch

    return profiles


def split_section(
    profiles: list[dict[str, Any]],
    section_index: int,
    sweep_loc: float = 0.25,
) -> list[dict[str, Any]]:
    """Split section i into two connected sections with an interpolated midpoint station."""
    sections = profiles_to_sections(profiles, sweep_loc)
    if not (0 <= section_index < len(sections)):
        return profiles

    sec = sections[section_index]
    span = sec["span"]
    c_root = sec["root_chord"]
    c_tip = sec["tip_chord"]
    c_mid = 0.5 * (c_root + c_tip)

    sec1 = {
        "span": 0.5 * span,
        "root_chord": c_root,
        "tip_chord": c_mid,
        "sweep": sec["sweep"],
        "dihedral": sec["dihedral"],
        "twist": 0.5 * sec["twist"],
        "root_airfoil": deepcopy(sec["root_airfoil"]),
        "tip_airfoil": deepcopy(sec["root_airfoil"]),
    }
    sec2 = {
        "span": 0.5 * span,
        "root_chord": c_mid,
        "tip_chord": c_tip,
        "sweep": sec["sweep"],
        "dihedral": sec["dihedral"],
        "twist": 0.5 * sec["twist"],
        "root_airfoil": deepcopy(sec["root_airfoil"]),
        "tip_airfoil": deepcopy(sec["tip_airfoil"]),
    }

    new_sections = sections[:section_index] + [sec1, sec2] + sections[section_index + 1:]
    return sections_to_profiles(new_sections, profiles[0], sweep_loc)


def insert_section(
    profiles: list[dict[str, Any]],
    sweep_loc: float = 0.25,
) -> list[dict[str, Any]]:
    """Append a new connected section at the wing tip."""
    sections = profiles_to_sections(profiles, sweep_loc)
    last_sec = sections[-1] if sections else {
        "span": 300.0,
        "root_chord": 200.0,
        "tip_chord": 100.0,
        "sweep": 0.0,
        "dihedral": 0.0,
        "twist": 0.0,
        "root_airfoil": "2412",
        "tip_airfoil": "2412",
    }

    new_sec = {
        "span": max(float(last_sec.get("span", 300.0)) * 0.8, 50.0),
        "root_chord": float(last_sec.get("tip_chord", 100.0)),
        "tip_chord": max(float(last_sec.get("tip_chord", 100.0)) * 0.7, 30.0),
        "sweep": float(last_sec.get("sweep", 0.0)),
        "dihedral": float(last_sec.get("dihedral", 0.0)),
        "twist": float(last_sec.get("twist", 0.0)),
        "root_airfoil": deepcopy(last_sec.get("tip_airfoil", "2412")),
        "tip_airfoil": deepcopy(last_sec.get("tip_airfoil", "2412")),
    }
    new_sections = sections + [new_sec]
    return sections_to_profiles(new_sections, profiles[0] if profiles else None, sweep_loc)


def delete_section(
    profiles: list[dict[str, Any]],
    section_index: int,
    sweep_loc: float = 0.25,
) -> list[dict[str, Any]]:
    """Delete section i (keeping at least 1 section / 2 profile stations)."""
    sections = profiles_to_sections(profiles, sweep_loc)
    if len(sections) <= 1 or not (0 <= section_index < len(sections)):
        return profiles

    deleted_sec = sections[section_index]
    new_sections = [s for j, s in enumerate(sections) if j != section_index]

    if section_index < len(new_sections):
        prev_tip_c = sections[section_index - 1]["tip_chord"] if section_index > 0 else deleted_sec["root_chord"]
        prev_tip_af = sections[section_index - 1]["tip_airfoil"] if section_index > 0 else deleted_sec["root_airfoil"]
        new_sections[section_index]["root_chord"] = prev_tip_c
        new_sections[section_index]["root_airfoil"] = deepcopy(prev_tip_af)

    return sections_to_profiles(new_sections, profiles[0], sweep_loc)
