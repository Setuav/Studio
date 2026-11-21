"""Tip cap and winglet 3D loft generation for lifting surfaces."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from typing import Any, Final

from .airfoil import apply_airfoil_shaping, sample_airfoil_points
from .data import LoftGeometry, Point3D, Section
from .lifting_surface_math import (
    interp_branch_z,
    split_airfoil_upper_lower,
)
from .transforms import section_transform, transform_point


@dataclass(frozen=True, slots=True)
class TipCapParameters:
    """Parameters of a round or sharp tip cap, keyed as stored in ``tip_treatment``."""

    length: float
    offset_x: float


@dataclass(frozen=True, slots=True)
class WingletParameters:
    """Parameters of a winglet tip, keyed as stored in ``tip_treatment``.

    With ``match_wing_tangent`` the winglet root continues the wing's leading and trailing
    edge sweep, and ``le_sweep_root`` and ``te_sweep_root`` are not used.
    """

    winglet_height: float
    match_wing_tangent: bool
    cant_root: float
    cant_tip: float
    blend_radius: float
    le_sweep_root: float
    le_sweep_tip: float
    le_curvature: float
    te_sweep_root: float
    te_sweep_tip: float
    te_curvature: float
    toe_root: float
    toe_tip: float
    root_chord_scale: float
    tip_chord_scale: float
    tip_thickness_scale: float


TIP_CAP_DEFAULTS: Final = TipCapParameters(length=20.0, offset_x=0.0)

WINGLET_DEFAULTS: Final = WingletParameters(
    winglet_height=130.0,
    match_wing_tangent=True,
    cant_root=0.0,
    cant_tip=80.0,
    blend_radius=0.0,
    le_sweep_root=20.0,
    le_sweep_tip=48.0,
    le_curvature=0.0,
    te_sweep_root=14.0,
    te_sweep_tip=24.0,
    te_curvature=0.0,
    toe_root=0.0,
    toe_tip=-1.5,
    root_chord_scale=1.0,
    tip_chord_scale=0.45,
    tip_thickness_scale=0.7,
)

TIP_TREATMENT_TYPES: Final = ("flat", "round", "sharp", "winglet")

_TIP_TREATMENT_DEFAULTS: Final[dict[str, TipCapParameters | WingletParameters | None]] = {
    "flat": None,
    "round": TIP_CAP_DEFAULTS,
    "sharp": TIP_CAP_DEFAULTS,
    "winglet": WINGLET_DEFAULTS,
}


def new_tip_treatment(tip_type: str, current: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a complete ``tip_treatment`` of ``tip_type`` with every parameter explicit.

    Switching between tip types that share their parameters (round and sharp) keeps the
    values of ``current``; any other switch writes the new type's defaults.
    """
    defaults = _type_defaults(tip_type)
    if defaults is None:
        return {"type": tip_type}
    if current is not None and _type_defaults(current["type"]) is defaults:
        return {"type": tip_type, **{key: current[key] for key in asdict(defaults)}}
    return {"type": tip_type, **asdict(defaults)}


def tip_treatment_type(geometry: Mapping[str, Any]) -> str:
    """Return the validated tip type of a lifting surface geometry.

    A geometry without ``tip_treatment`` has a flat tip. A present ``tip_treatment`` must
    hold exactly the parameters of its type.
    """
    tip_treatment = geometry.get("tip_treatment")
    if tip_treatment is None:
        return "flat"
    if not isinstance(tip_treatment, Mapping):
        raise ValueError(f"Tip treatment must be an object, got {tip_treatment!r}")
    if "type" not in tip_treatment:
        raise ValueError("Tip treatment is missing 'type'")
    tip_type = tip_treatment["type"]
    defaults = _type_defaults(tip_type)
    expected = set(asdict(defaults)) if defaults is not None else set()
    present = _parameter_keys(tip_treatment)
    missing = sorted(expected - present)
    if missing:
        raise ValueError(f"{tip_type.capitalize()} tip treatment is missing {_key_list(missing)}")
    unknown = sorted(present - expected)
    if unknown:
        raise ValueError(f"{tip_type.capitalize()} tip treatment has unknown {_key_list(unknown)}")
    if defaults is not None:
        for field in fields(defaults):
            _check_value_type(tip_type, field.name, tip_treatment[field.name], defaults)
    return tip_type


def tip_cap_parameters(geometry: Mapping[str, Any]) -> TipCapParameters:
    """Return the tip cap parameters of a lifting surface with a round or sharp tip."""
    tip_type = tip_treatment_type(geometry)
    if tip_type not in ("round", "sharp"):
        raise ValueError(f"Tip treatment {tip_type!r} is not a round or sharp tip cap")
    tip_treatment = geometry["tip_treatment"]
    return TipCapParameters(
        **{field.name: float(tip_treatment[field.name]) for field in fields(TipCapParameters)}
    )


def winglet_parameters(geometry: Mapping[str, Any]) -> WingletParameters:
    """Return the winglet parameters of a lifting surface with a winglet tip."""
    tip_type = tip_treatment_type(geometry)
    if tip_type != "winglet":
        raise ValueError(f"Tip treatment {tip_type!r} is not a winglet")
    tip_treatment = geometry["tip_treatment"]
    values: dict[str, Any] = {}
    for field in fields(WingletParameters):
        value = tip_treatment[field.name]
        values[field.name] = value if isinstance(value, bool) else float(value)
    return WingletParameters(**values)


def _type_defaults(tip_type: object) -> TipCapParameters | WingletParameters | None:
    if not isinstance(tip_type, str) or tip_type not in _TIP_TREATMENT_DEFAULTS:
        raise ValueError(
            f"Unknown tip treatment type {tip_type!r}; expected one of {TIP_TREATMENT_TYPES}"
        )
    return _TIP_TREATMENT_DEFAULTS[tip_type]


def _parameter_keys(tip_treatment: Mapping[str, Any]) -> set[str]:
    return {str(key) for key in tip_treatment if key != "type"}


def _key_list(keys: list[str]) -> str:
    noun = "key" if len(keys) == 1 else "keys"
    return f"{noun} " + ", ".join(repr(key) for key in keys)


def _check_value_type(
    tip_type: str,
    key: str,
    value: object,
    defaults: TipCapParameters | WingletParameters,
) -> None:
    if isinstance(getattr(defaults, key), bool):
        if not isinstance(value, bool):
            raise ValueError(
                f"{tip_type.capitalize()} tip treatment {key!r} must be true or false, "
                f"got {value!r}"
            )
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{tip_type.capitalize()} tip treatment {key!r} must be a number, got {value!r}"
        )


def build_tip_cap_loft(
    comp_id: str,
    tip_profile: dict[str, Any],
    *,
    tip_type: str,
    cap: TipCapParameters,
    span_dir: float,
    le_sweep_slope: float,
    te_sweep_slope: float,
    twist_location: float,
) -> LoftGeometry | None:
    """Generate a smooth, aerodynamic G1-conformal bullnose or beveled edge cap mesh."""
    if tip_type not in ("round", "sharp") or cap.length <= 0.0:
        return None
    tip_length = cap.length
    offset_x = cap.offset_x

    chord = float(tip_profile["chord"])
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
        owner_id=comp_id,
        feature_wire="chords",
        sections=tuple(cap_sections),
        interpolation="linear",
        station_spacing=10.0,
        closed_ends=False,
    )


def compute_winglet_projected_dimensions(
    winglet: WingletParameters,
    n_pts: int = 50,
) -> tuple[float, float]:
    """Compute projected vertical height (delta Z) and span extension (delta Y) in mm.

    Returns:
        tuple[float, float]: (delta_z_height_mm, delta_y_span_mm)
    """
    winglet_height = winglet.winglet_height
    if winglet_height <= 0.0:
        return 0.0, 0.0

    u_vals = [0.5 * (1.0 - math.cos(math.pi * i / (n_pts - 1))) for i in range(n_pts)]
    cant_angles_rad = winglet_cant_angles(
        u_vals, winglet.cant_root, winglet.cant_tip, winglet.blend_radius, winglet_height
    )

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
    winglet: WingletParameters,
    *,
    span_dir: float,
    incoming_le_sweep_deg: float,
    incoming_te_sweep_deg: float,
    twist_location: float,
    te_thickness: float,
    thickness_scale: float,
    camber_scale: float,
    n_stations: int = 24,
) -> LoftGeometry | None:
    """Generate a parametric curved winglet loft with G1 tangency and independent LE/TE curves."""
    winglet_height = winglet.winglet_height
    if winglet_height <= 0.0:
        return None

    tip_chord = float(tip_profile["chord"])
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

    le_s_root, le_s_tip, te_s_root, te_s_tip = winglet_sweep_angles(
        winglet, incoming_le_sweep_deg, incoming_te_sweep_deg
    )

    le_curv_val = winglet.le_curvature
    te_curv_val = winglet.te_curvature
    t_root = winglet.toe_root
    t_tip = winglet.toe_tip
    root_chord_scale = winglet.root_chord_scale
    tip_chord_scale = winglet.tip_chord_scale
    tip_thickness_scale = winglet.tip_thickness_scale

    n_pts = max(n_stations, 20)
    u_vals = [0.5 * (1.0 - math.cos(math.pi * i / (n_pts - 1))) for i in range(n_pts)]
    cant_angles_rad = winglet_cant_angles(
        u_vals, winglet.cant_root, winglet.cant_tip, winglet.blend_radius, winglet_height
    )

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
        if idx == 0:
            x_le_u = 0.0
            chord_wl = tip_chord
            ds_y = 0.0
            ds_z = 0.0
            cant_rad = 0.0
            cos_cant = 1.0
            sin_cant = 0.0
            cos_toe = 1.0
            sin_toe = 0.0
            t_scale = 1.0
            x_pivot = twist_location * tip_chord
        else:
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
            x_pivot = x_le_u + twist_location * chord_wl

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
        owner_id=comp_id,
        feature_wire="ends",
        sections=tuple(sections),
        interpolation="smooth" if len(sections) > 2 else "linear",
        station_spacing=10.0,
        closed_ends=True,
    )


def winglet_sweep_angles(
    winglet: WingletParameters,
    incoming_leading: float,
    incoming_trailing: float,
) -> tuple[float, float, float, float]:
    """Return the winglet's (LE root, LE tip, TE root, TE tip) sweep angles in degrees.

    A winglet matching the wing tangent continues the incoming wing edge sweeps at its root.
    """
    if winglet.match_wing_tangent:
        leading_root, trailing_root = incoming_leading, incoming_trailing
    else:
        leading_root, trailing_root = winglet.le_sweep_root, winglet.te_sweep_root
    return leading_root, winglet.le_sweep_tip, trailing_root, winglet.te_sweep_tip


def winglet_cant_angles(
    stations: list[float],
    root_angle: float,
    tip_angle: float,
    blend_radius: float,
    height: float,
) -> list[float]:
    blend_end = min(1.0, max(0.01, blend_radius / height)) if blend_radius > 0.0 else 0.0
    angles: list[float] = []
    for i, station in enumerate(stations):
        if i == 0 or station == 0.0:
            angles.append(0.0)
            continue
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
    "TIP_CAP_DEFAULTS",
    "TIP_TREATMENT_TYPES",
    "WINGLET_DEFAULTS",
    "TipCapParameters",
    "WingletParameters",
    "build_tip_cap_loft",
    "build_winglet_loft",
    "compute_winglet_projected_dimensions",
    "new_tip_treatment",
    "tip_cap_parameters",
    "tip_treatment_type",
    "winglet_cant_angles",
    "winglet_parameters",
    "winglet_sweep_angles",
]
