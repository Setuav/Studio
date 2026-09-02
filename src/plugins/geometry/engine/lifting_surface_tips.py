"""Tip cap and winglet 3D loft generation for lifting surfaces."""

from __future__ import annotations

import math
from typing import Any

from ..viewport.palettes import wing_color
from .airfoil import apply_airfoil_shaping, sample_airfoil_points
from .data import LoftGeometry, Point3D, Section
from .lifting_surface_math import (
    interp_branch_z,
    number,
    split_airfoil_upper_lower,
)
from .transforms import section_transform, transform_point


def build_tip_cap_loft(
    comp_id: str,
    tip_profile: dict[str, Any],
    tip_type: str = "round",
    tip_length: float = 20.0,
    offset_x: float = 0.0,
    span_dir: float = 1.0,
    le_sweep_slope: float = 0.0,
    te_sweep_slope: float = 0.0,
    twist_location: float = 0.25,
) -> LoftGeometry | None:
    """Generate a smooth, aerodynamic G1-conformal bullnose or beveled edge cap mesh."""
    if tip_type not in ("round", "sharp") or tip_length <= 0.0:
        return None

    chord = number(tip_profile.get("chord"))
    if chord <= 0:
        return None

    coords = sample_airfoil_points(tip_profile.get("airfoil"))
    upper_b, lower_b = split_airfoil_upper_lower(coords)
    matrix = section_transform(tip_profile, chord=chord, twist_location=twist_location)

    num_x = 33
    x_stations = [0.5 * (1.0 - math.cos(math.pi * i / (num_x - 1))) for i in range(num_x)]
    max_h = max(
        (interp_branch_z(upper_b, x) - interp_branch_z(lower_b, x)) * 0.5 for x in x_stations
    )
    if max_h < 1e-6:
        return None

    num_theta = 17 if tip_type == "round" else 3
    cap_sections: list[Section] = []

    for k in range(num_theta):
        theta = math.pi * 0.5 - (k / (num_theta - 1)) * math.pi
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        pts: list[Point3D] = []
        for x_rel in x_stations:
            z_u = interp_branch_z(upper_b, x_rel)
            z_l = interp_branch_z(lower_b, x_rel)
            z_c = (z_u + z_l) * 0.5
            h = (z_u - z_l) * 0.5
            h_ratio = h / max_h

            delta_y = span_dir * tip_length * h_ratio * cos_t
            sweep_slope = le_sweep_slope + (te_sweep_slope - le_sweep_slope) * x_rel
            delta_x = (offset_x * h_ratio * cos_t) + (delta_y * sweep_slope)
            z_val = z_c + h * sin_t

            p_local = (x_rel * chord + delta_x, delta_y, z_val * chord)
            p_world = transform_point(matrix, p_local)
            pts.append(p_world)

        cap_sections.append(Section(tuple(pts)))

    return LoftGeometry(
        component_id=f"{comp_id}:tip-cap",
        sections=tuple(cap_sections),
        color=wing_color(),
        interpolation="linear",
        station_spacing=10.0,
        closed_ends=False,
    )


def compute_winglet_projected_dimensions(
    winglet_height: float,
    cant_root_deg: float,
    cant_tip_deg: float,
    blend_radius: float,
    n_pts: int = 50,
) -> tuple[float, float]:
    """Compute projected vertical height (delta Z) and span extension (delta Y) in mm.

    Returns:
        tuple[float, float]: (delta_z_height_mm, delta_y_span_mm)
    """
    if winglet_height <= 0.0:
        return 0.0, 0.0
    u_blend = min(1.0, max(0.01, blend_radius / winglet_height)) if blend_radius > 0.0 else 0.0
    c_root = cant_root_deg
    c_tip = cant_tip_deg

    u_vals = [0.5 * (1.0 - math.cos(math.pi * i / (n_pts - 1))) for i in range(n_pts)]
    cant_angles_rad: list[float] = []
    for u in u_vals:
        if blend_radius > 0.0:
            if u <= u_blend:
                t = u / u_blend
                w = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
                angle = c_root + (c_tip - c_root) * w
            else:
                angle = c_tip
        else:
            angle = c_root + (c_tip - c_root) * u
        cant_angles_rad.append(math.radians(angle))

    delta_y = 0.0
    delta_z = 0.0
    for i in range(1, n_pts):
        du = u_vals[i] - u_vals[i - 1]
        ds = winglet_height * du
        avg_cos = 0.5 * (math.cos(cant_angles_rad[i - 1]) + math.cos(cant_angles_rad[i]))
        avg_sin = 0.5 * (math.sin(cant_angles_rad[i - 1]) + math.sin(cant_angles_rad[i]))
        delta_y += ds * avg_cos
        delta_z += ds * avg_sin

    return delta_z, delta_y


def build_winglet_loft(
    comp_id: str,
    tip_profile: dict[str, Any],
    span_dir: float = 1.0,
    winglet_height: float = 130.0,
    cant_angle_deg: float = 80.0,
    cant_root_deg: float | None = 0.0,
    cant_tip_deg: float | None = None,
    blend_radius: float = 45.0,
    match_wing_tangent: bool = True,
    incoming_le_sweep_deg: float = 0.0,
    incoming_te_sweep_deg: float = 0.0,
    sweep_deg: float = 20.0,
    sweep_root_deg: float | None = None,
    sweep_tip_deg: float | None = None,
    le_sweep_root_deg: float | None = None,
    le_sweep_tip_deg: float | None = None,
    le_curvature: float = 0.0,
    te_sweep_root_deg: float | None = None,
    te_sweep_tip_deg: float | None = None,
    te_curvature: float = 0.0,
    scimitar_offset: float = 0.0,
    toe_angle_deg: float = 0.0,
    toe_root_deg: float | None = None,
    toe_tip_deg: float | None = None,
    root_chord_scale: float = 1.0,
    tip_chord_scale: float = 0.45,
    tip_thickness_scale: float = 0.7,
    taper_curve: float = 1.0,
    twist_location: float = 0.25,
    te_thickness: float = 0.0,
    thickness_scale: float = 1.0,
    camber_scale: float = 1.0,
    n_stations: int = 24,
) -> LoftGeometry | None:
    """Generate a parametric curved winglet loft with G1 tangency and independent LE/TE curves."""
    if winglet_height <= 0.0:
        return None

    tip_chord = number(tip_profile.get("chord"))
    if tip_chord <= 0.0:
        return None

    matrix = section_transform(tip_profile, chord=tip_chord, twist_location=twist_location)
    coords = sample_airfoil_points(tip_profile.get("airfoil"))
    coords = apply_airfoil_shaping(
        coords,
        te_thickness=te_thickness,
        thickness_scale=thickness_scale,
        camber_scale=camber_scale,
    )
    upper_b, lower_b = split_airfoil_upper_lower(coords)

    c_tip = cant_tip_deg if cant_tip_deg is not None else cant_angle_deg
    c_root = cant_root_deg if cant_root_deg is not None else 0.0

    le_s_root, le_s_tip, te_s_root, te_s_tip = winglet_sweep_angles(
        sweep_deg,
        sweep_root_deg,
        sweep_tip_deg,
        le_sweep_root_deg,
        le_sweep_tip_deg,
        te_sweep_root_deg,
        te_sweep_tip_deg,
        match_wing_tangent,
        incoming_le_sweep_deg,
        incoming_te_sweep_deg,
    )

    le_curv_val = le_curvature + scimitar_offset
    te_curv_val = te_curvature + (scimitar_offset * 0.4)

    t_root = toe_root_deg if toe_root_deg is not None else toe_angle_deg
    t_tip = toe_tip_deg if toe_tip_deg is not None else toe_angle_deg

    n_pts = max(n_stations, 20)
    u_vals = [0.5 * (1.0 - math.cos(math.pi * i / (n_pts - 1))) for i in range(n_pts)]
    cant_angles_rad = winglet_cant_angles(u_vals, c_root, c_tip, blend_radius, winglet_height)

    y_offsets: list[float] = [0.0]
    z_offsets: list[float] = [0.0]

    for i in range(1, n_pts):
        du = u_vals[i] - u_vals[i - 1]
        ds = winglet_height * du
        avg_cos = 0.5 * (math.cos(cant_angles_rad[i - 1]) + math.cos(cant_angles_rad[i]))
        avg_sin = 0.5 * (math.sin(cant_angles_rad[i - 1]) + math.sin(cant_angles_rad[i]))
        y_offsets.append(y_offsets[-1] + ds * avg_cos * span_dir)
        z_offsets.append(z_offsets[-1] + ds * avg_sin)

    m0_le = winglet_height * math.tan(math.radians(le_s_root))
    m1_le = winglet_height * math.tan(math.radians(le_s_tip))
    x_le_tip = 0.5 * (m0_le + m1_le)

    c0 = tip_chord * root_chord_scale
    c1 = tip_chord * tip_chord_scale
    k0_te = winglet_height * math.tan(math.radians(te_s_root))
    k1_te = winglet_height * math.tan(math.radians(te_s_tip))
    x_te_tip = x_le_tip + c1

    n_upper, n_lower, n_wall = 28, 28, 7
    global_x_upper = [0.5 * (1.0 + math.cos(math.pi * i / (n_upper - 1))) for i in range(n_upper)]
    global_x_lower = [0.5 * (1.0 - math.cos(math.pi * i / (n_lower - 1))) for i in range(n_lower)]

    sections: list[Section] = []

    for idx, u in enumerate(u_vals):
        h00 = 2.0 * u**3 - 3.0 * u**2 + 1.0
        h10 = u**3 - 2.0 * u**2 + u
        h01 = -2.0 * u**3 + 3.0 * u**2
        h11 = u**3 - u**2
        bow = 16.0 * (u**2) * ((1.0 - u) ** 2)

        x_le_u = x_le_tip * h01 + m0_le * h10 + m1_le * h11 + le_curv_val * bow
        x_te_u = c0 * h00 + x_te_tip * h01 + k0_te * h10 + k1_te * h11 + te_curv_val * bow
        chord_wl = max(x_te_u - x_le_u, 0.05 * c1)

        ds_y = y_offsets[idx]
        ds_z = z_offsets[idx]

        cant_rad = cant_angles_rad[idx]
        cos_cant = math.cos(cant_rad)
        sin_cant = math.sin(cant_rad)

        toe_deg = t_root + (t_tip - t_root) * u
        toe_rad = math.radians(toe_deg)
        cos_toe = math.cos(toe_rad)
        sin_toe = math.sin(toe_rad)

        t_scale = 1.0 + (tip_thickness_scale - 1.0) * u
        x_pivot = x_le_u + 0.25 * chord_wl

        def _calc_pt(
            x_rel: float,
            z_rel: float,
            *,
            x_le_u: float = x_le_u,
            chord_wl: float = chord_wl,
            t_scale: float = t_scale,
            x_pivot: float = x_pivot,
            cos_toe: float = cos_toe,
            sin_toe: float = sin_toe,
            sin_cant: float = sin_cant,
            cos_cant: float = cos_cant,
            ds_y: float = ds_y,
            ds_z: float = ds_z,
        ) -> Point3D:
            x_local = x_le_u + x_rel * chord_wl
            z_local = z_rel * chord_wl * t_scale
            dx_p = x_local - x_pivot
            x_toe = dx_p * cos_toe - z_local * sin_toe + x_pivot
            z_toe = dx_p * sin_toe + z_local * cos_toe
            dy_sec = -z_toe * sin_cant * span_dir
            dz_sec = z_toe * cos_cant
            p_local = (x_toe, ds_y + dy_sec, ds_z + dz_sec)
            return transform_point(matrix, p_local)

        pts: list[Point3D] = []

        # Upper surface (TE -> LE)
        for i in range(n_upper):
            x_rel = global_x_upper[i]
            z_val = interp_branch_z(upper_b, x_rel)
            pts.append(_calc_pt(x_rel, z_val))

        # LE point
        z_le = interp_branch_z(upper_b, 0.0)
        pts.append(_calc_pt(0.0, z_le))

        # Lower surface (LE -> TE)
        for i in range(n_lower):
            x_rel = global_x_lower[i]
            z_val = interp_branch_z(lower_b, x_rel)
            pts.append(_calc_pt(x_rel, z_val))

        # TE closure
        z_te_u = interp_branch_z(upper_b, 1.0)
        z_te_l = interp_branch_z(lower_b, 1.0)
        for j in range(1, n_wall + 1):
            fj = j / n_wall
            z_wall = z_te_u + fj * (z_te_l - z_te_u)
            pts.append(_calc_pt(1.0, z_wall))

        sections.append(Section(tuple(pts)))

    return LoftGeometry(
        component_id=f"{comp_id}:winglet",
        sections=tuple(sections),
        color=wing_color(),
        interpolation="smooth" if len(sections) > 2 else "linear",
        station_spacing=10.0,
        closed_ends=True,
    )


def winglet_sweep_angles(
    sweep: float,
    sweep_root: float | None,
    sweep_tip: float | None,
    leading_root: float | None,
    leading_tip: float | None,
    trailing_root: float | None,
    trailing_tip: float | None,
    match_tangent: bool,
    incoming_leading: float,
    incoming_trailing: float,
) -> tuple[float, float, float, float]:
    leading_tip_value = leading_tip if leading_tip is not None else sweep_tip
    if leading_tip_value is None:
        leading_tip_value = sweep

    leading_root_value = leading_root
    if leading_root_value is None:
        if match_tangent:
            leading_root_value = incoming_leading
        elif sweep_root is not None:
            leading_root_value = sweep_root
        else:
            leading_root_value = sweep

    trailing_root_value = trailing_root
    if trailing_root_value is None:
        trailing_root_value = incoming_trailing if match_tangent else leading_root_value * 0.7
    trailing_tip_value = trailing_tip if trailing_tip is not None else leading_tip_value * 0.5
    return leading_root_value, leading_tip_value, trailing_root_value, trailing_tip_value


def winglet_cant_angles(
    stations: list[float],
    root_angle: float,
    tip_angle: float,
    blend_radius: float,
    height: float,
) -> list[float]:
    blend_end = min(1.0, max(0.01, blend_radius / height)) if blend_radius > 0.0 else 0.0
    angles: list[float] = []
    for station in stations:
        if blend_radius <= 0.0:
            angle = root_angle + (tip_angle - root_angle) * station
        elif station > blend_end:
            angle = tip_angle
        else:
            ratio = station / blend_end
            weight = ratio**3 * (ratio * (ratio * 6.0 - 15.0) + 10.0)
            angle = root_angle + (tip_angle - root_angle) * weight
        angles.append(math.radians(angle))
    return angles


__all__ = [
    "build_tip_cap_loft",
    "build_winglet_loft",
    "compute_winglet_projected_dimensions",
    "winglet_cant_angles",
    "winglet_sweep_angles",
]
