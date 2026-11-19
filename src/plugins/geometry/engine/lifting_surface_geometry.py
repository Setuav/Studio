"""Geometry builder for lifting surfaces and deflected 3D control surfaces."""

from __future__ import annotations

import math
from typing import Any, Literal

from .airfoil import apply_airfoil_shaping, sample_airfoil_points
from .data import LoftGeometry, Section
from .lifting_surface_cuts import build_lifting_surface_with_control_surfaces
from .lifting_surface_math import (
    mapping,
    number,
    sample_structured_airfoil_round,
)
from .lifting_surface_tips import (
    build_tip_cap_loft,
    build_winglet_loft,
    tip_cap_parameters,
    tip_treatment_type,
    winglet_parameters,
)
from .palettes import lifting_surface_color
from .transforms import Matrix4, section_transform, transform_point


def build_lifting_surface_geometry(
    component: dict[str, Any],
    control_surfaces: list[dict[str, Any]] | None = None,
) -> tuple[LoftGeometry, ...]:
    """Generate loft geometries for a lifting surface and its control surfaces."""
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    profiles = geometry.get("profiles")
    if not isinstance(profiles, list) or len(profiles) < 2:
        return ()

    comp_id = str(component["id"])
    interpolation = "smooth" if len(profiles) > 2 else "linear"

    twist_location = float(geometry.get("twist_location", 0.25))

    # Airfoil Shaping parameters
    shaping = geometry.get("airfoil_shaping")
    shaping = shaping if isinstance(shaping, dict) else {}
    te_thickness = float(shaping.get("te_thickness", 0.0))
    thickness_scale = float(shaping.get("thickness_scale", 1.0))
    camber_scale = float(shaping.get("camber_scale", 1.0))
    # Section alignment: "xz" (default) | "normal" (perpendicular to span)
    section_align = str(geometry.get("section_align", "xz")).lower()

    tip_type = tip_treatment_type(geometry)

    if not isinstance(control_surfaces, list) or not control_surfaces:
        # Simple continuous lifting surface without control surfaces
        sections = tuple(
            section
            for value in profiles
            if (
                section := _build_profile_section(
                    value,
                    twist_location=twist_location,
                    te_thickness=te_thickness,
                    thickness_scale=thickness_scale,
                    camber_scale=camber_scale,
                    section_align=section_align,
                )
            )
            is not None
        )
        if len(sections) < 2:
            return ()
        lofts_list = [
            LoftGeometry(
                component_id=comp_id,
                owner_id=comp_id,
                sections=sections,
                color=lifting_surface_color(),
                interpolation=interpolation,
                station_spacing=15.0,
                closed_ends=True,
            )
        ]
    else:
        # Segmented wing with clean rectangular bay cutouts and round hinges
        lofts_list = list(
            _build_lifting_surface_with_control_surfaces(
                comp_id=comp_id,
                profiles=profiles,
                control_surfaces=control_surfaces,
                interpolation=interpolation,
                twist_location=twist_location,
                te_thickness=te_thickness,
                thickness_scale=thickness_scale,
                camber_scale=camber_scale,
                section_align=section_align,
            )
        )

    # Attach dedicated G1-continuous aerodynamic tip cap mesh if round or sharp
    if tip_type in ("round", "sharp"):
        y0 = (
            float(profiles[0].get("position", {}).get("y", 0.0))
            if isinstance(profiles[0].get("position"), dict)
            else 0.0
        )
        y1 = (
            float(profiles[-1].get("position", {}).get("y", 0.0))
            if isinstance(profiles[-1].get("position"), dict)
            else 0.0
        )
        span_dir = 1.0 if y1 >= y0 else -1.0

        p_prev = profiles[-2] if len(profiles) >= 2 else profiles[-1]
        p_tip = profiles[-1]
        prev_pos = p_prev.get("position", {}) if isinstance(p_prev.get("position"), dict) else {}
        tip_pos = p_tip.get("position", {}) if isinstance(p_tip.get("position"), dict) else {}
        dy = float(tip_pos.get("y", 0.0)) - float(prev_pos.get("y", 0.0))
        if abs(dy) > 1e-4:
            dx_le = float(tip_pos.get("x", 0.0)) - float(prev_pos.get("x", 0.0))
            dx_te = (float(tip_pos.get("x", 0.0)) + number(p_tip.get("chord"))) - (
                float(prev_pos.get("x", 0.0)) + number(p_prev.get("chord"))
            )
            le_sweep_slope = dx_le / dy
            te_sweep_slope = dx_te / dy
        else:
            le_sweep_slope = 0.0
            te_sweep_slope = 0.0

        tip_cap = build_tip_cap_loft(
            comp_id=comp_id,
            tip_profile=profiles[-1],
            tip_type=tip_type,
            cap=tip_cap_parameters(geometry),
            span_dir=span_dir,
            le_sweep_slope=le_sweep_slope,
            te_sweep_slope=te_sweep_slope,
            twist_location=twist_location,
        )
        if tip_cap is not None:
            lofts_list.append(tip_cap)

    elif tip_type == "winglet":
        y0 = (
            float(profiles[0].get("position", {}).get("y", 0.0))
            if isinstance(profiles[0].get("position"), dict)
            else 0.0
        )
        y1 = (
            float(profiles[-1].get("position", {}).get("y", 0.0))
            if isinstance(profiles[-1].get("position"), dict)
            else 0.0
        )
        span_dir = 1.0 if y1 >= y0 else -1.0

        p_prev = profiles[-2] if len(profiles) >= 2 else profiles[-1]
        p_tip = profiles[-1]
        prev_pos = p_prev.get("position", {}) if isinstance(p_prev.get("position"), dict) else {}
        tip_pos = p_tip.get("position", {}) if isinstance(p_tip.get("position"), dict) else {}
        dy = float(tip_pos.get("y", 0.0)) - float(prev_pos.get("y", 0.0))
        if abs(dy) > 1e-4:
            dx_le = float(tip_pos.get("x", 0.0)) - float(prev_pos.get("x", 0.0))
            dx_te = (float(tip_pos.get("x", 0.0)) + number(p_tip.get("chord"))) - (
                float(prev_pos.get("x", 0.0)) + number(p_prev.get("chord"))
            )
            incoming_le_sweep_deg = math.degrees(math.atan2(dx_le, abs(dy)))
            incoming_te_sweep_deg = math.degrees(math.atan2(dx_te, abs(dy)))
        else:
            incoming_le_sweep_deg = 0.0
            incoming_te_sweep_deg = 0.0

        winglet_loft = build_winglet_loft(
            comp_id=comp_id,
            tip_profile=profiles[-1],
            winglet=winglet_parameters(geometry),
            span_dir=span_dir,
            incoming_le_sweep_deg=incoming_le_sweep_deg,
            incoming_te_sweep_deg=incoming_te_sweep_deg,
            twist_location=twist_location,
            te_thickness=te_thickness,
            thickness_scale=thickness_scale,
            camber_scale=camber_scale,
        )
        if winglet_loft is not None:
            lofts_list.append(winglet_loft)

    return tuple(lofts_list)


def _apply_shaping(
    coords: tuple[tuple[float, float], ...],
    te_thickness: float,
    thickness_scale: float,
    camber_scale: float,
) -> tuple[tuple[float, float], ...]:
    """Apply airfoil shaping transforms (TE blunting, t/c scale, camber scale)."""
    return apply_airfoil_shaping(
        coords,
        te_thickness=te_thickness,
        thickness_scale=thickness_scale,
        camber_scale=camber_scale,
    )


def _section_with_align(
    matrix: Matrix4,
    chord: float,
    main_2d: tuple[tuple[float, float], ...],
    dihedral_rad: float,
    section_align: str,
    is_station: bool = True,
) -> Section:
    """Build a 3D Section, optionally rotating the airfoil plane to be normal to the span direction."""
    if section_align == "normal" and abs(dihedral_rad) > 1e-4:
        cos_d = math.cos(dihedral_rad)
        sin_d = math.sin(dihedral_rad)
        corrected: list[tuple[float, float, float]] = []
        for x, z in main_2d:
            corrected.append((x * chord, -z * chord * sin_d, z * chord * cos_d))
        return Section(tuple(transform_point(matrix, p) for p in corrected), is_station=is_station)
    return Section(
        tuple(transform_point(matrix, (x * chord, 0.0, z * chord)) for x, z in main_2d),
        is_station=is_station,
    )


def _build_profile_section(
    value: object,
    twist_location: float = 0.25,
    te_thickness: float = 0.0,
    thickness_scale: float = 1.0,
    camber_scale: float = 1.0,
    section_align: str = "xz",
) -> Section | None:
    profile = value if isinstance(value, dict) else None
    if profile is None:
        return None
    chord = number(profile.get("chord"))
    if chord <= 0:
        return None
    coords = sample_airfoil_points(profile.get("airfoil"))
    coords = _apply_shaping(coords, te_thickness, thickness_scale, camber_scale)
    rot = mapping(profile.get("rotation"))
    dihedral_rad = math.radians(number(rot.get("x", 0.0)))
    matrix = section_transform(profile, chord=chord, twist_location=twist_location)
    main_2d, _ = sample_structured_airfoil_round(coords, x_h=1.0, is_flap=False)
    return _section_with_align(matrix, chord, main_2d, dihedral_rad, section_align)


def _build_lifting_surface_with_control_surfaces(
    comp_id: str,
    profiles: list[dict[str, Any]],
    control_surfaces: list[dict[str, Any]],
    interpolation: Literal["linear", "smooth"],
    twist_location: float = 0.25,
    te_thickness: float = 0.0,
    thickness_scale: float = 1.0,
    camber_scale: float = 1.0,
    section_align: str = "xz",
) -> tuple[LoftGeometry, ...]:
    return build_lifting_surface_with_control_surfaces(
        comp_id=comp_id,
        profiles=profiles,
        control_surfaces=control_surfaces,
        interpolation=interpolation,
        twist_location=twist_location,
        te_thickness=te_thickness,
        thickness_scale=thickness_scale,
        camber_scale=camber_scale,
        section_align=section_align,
        plain_surface_builder=_plain_lifting_surface,
        interpolate_station_fn=_interpolate_station_props,
        apply_shaping_fn=_apply_shaping,
        section_with_align_fn=_section_with_align,
    )


def _plain_lifting_surface(
    comp_id: str,
    profiles: list[dict[str, Any]],
    interpolation: Literal["linear", "smooth"],
    te_thickness: float,
    thickness_scale: float,
    camber_scale: float,
    section_align: str,
) -> tuple[LoftGeometry, ...]:
    sections = tuple(
        section
        for profile in profiles
        if (
            section := _build_profile_section(
                profile,
                te_thickness=te_thickness,
                thickness_scale=thickness_scale,
                camber_scale=camber_scale,
                section_align=section_align,
            )
        )
        is not None
    )
    return (
        LoftGeometry(
            component_id=comp_id,
            owner_id=comp_id,
            sections=sections,
            color=lifting_surface_color(),
            interpolation=interpolation,
            station_spacing=15.0,
            closed_ends=True,
        ),
    )


def _interpolate_station_props(
    y: float,
    profiles: list[dict[str, Any]],
) -> tuple[float, dict[str, Any], tuple[tuple[float, float], ...]]:
    """Interpolate chord, section dict (for transform), and airfoil coords at span y."""
    sorted_profs = sorted(
        profiles,
        key=lambda p: (
            float(p.get("position", {}).get("y", 0.0))
            if isinstance(p.get("position"), dict)
            else 0.0
        ),
    )
    y_coords = [
        float(p.get("position", {}).get("y", 0.0)) if isinstance(p.get("position"), dict) else 0.0
        for p in sorted_profs
    ]

    if y <= y_coords[0]:
        p = sorted_profs[0]
        chord = number(p.get("chord"))
        coords = sample_airfoil_points(p.get("airfoil"))
        return chord, p, coords
    if y >= y_coords[-1]:
        p = sorted_profs[-1]
        chord = number(p.get("chord"))
        coords = sample_airfoil_points(p.get("airfoil"))
        return chord, p, coords

    idx = 0
    while idx < len(y_coords) - 1 and y_coords[idx + 1] < y:
        idx += 1

    p0, p1 = sorted_profs[idx], sorted_profs[idx + 1]
    y0, y1 = y_coords[idx], y_coords[idx + 1]
    t = (y - y0) / max(y1 - y0, 1e-6)

    c0 = number(p0.get("chord"))
    c1 = number(p1.get("chord"))
    chord_interp = c0 + (c1 - c0) * t

    pos0 = p0.get("position", {}) if isinstance(p0.get("position"), dict) else {}
    pos1 = p1.get("position", {}) if isinstance(p1.get("position"), dict) else {}
    rot0 = p0.get("rotation", {}) if isinstance(p0.get("rotation"), dict) else {}
    rot1 = p1.get("rotation", {}) if isinstance(p1.get("rotation"), dict) else {}

    pos_interp = {
        "x": float(pos0.get("x", 0.0))
        + (float(pos1.get("x", 0.0)) - float(pos0.get("x", 0.0))) * t,
        "y": y,
        "z": float(pos0.get("z", 0.0))
        + (float(pos1.get("z", 0.0)) - float(pos0.get("z", 0.0))) * t,
    }
    rot_interp = {
        "x": float(rot0.get("x", 0.0))
        + (float(rot1.get("x", 0.0)) - float(rot0.get("x", 0.0))) * t,
        "y": float(rot0.get("y", 0.0))
        + (float(rot1.get("y", 0.0)) - float(rot0.get("y", 0.0))) * t,
        "z": float(rot0.get("z", 0.0))
        + (float(rot1.get("z", 0.0)) - float(rot0.get("z", 0.0))) * t,
    }

    af = p0.get("airfoil") if t < 0.5 else p1.get("airfoil")
    coords = sample_airfoil_points(af)

    prof_interp = {
        "chord": chord_interp,
        "position": pos_interp,
        "rotation": rot_interp,
        "airfoil": af,
    }
    return chord_interp, prof_interp, coords


__all__ = [
    "build_lifting_surface_geometry",
]
