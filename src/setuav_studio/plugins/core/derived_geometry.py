"""Geometry-derived component properties.

This module intentionally has no Qt or plugin dependencies.  It provides the
small, deterministic geometry-to-properties bridge used by the transform,
envelope and weight-balance editors.  Persisted values still win whenever a
user explicitly declares them; these values are the defaults for geometric
components and control surfaces.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


# A conservative average density for foam/composite model aircraft structure.
# Projects can override it with parameters.geometry_density_kg_m3 or
# parameters.material_density_kg_m3.
DEFAULT_DENSITY_KG_M3 = 160.0


@dataclass(frozen=True, slots=True)
class DerivedComponentGeometry:
    transform: dict[str, Any]
    envelope: dict[str, Any]
    mass_g: float | None
    volume_mm3: float
    source: str = "derived"


def derive_project_component_geometry(
    components: list[dict[str, Any]],
) -> dict[str, DerivedComponentGeometry]:
    """Derive local transform, envelope and mass for all geometric components.

    Control-surface geometry is still derived for envelopes and view data, but
    its mass is not folded into the weight-balance result.  A lifting surface
    is treated as one mass item; this avoids making hinge-bay approximations
    visible as separate aircraft mass components.
    """
    by_id = {
        str(item.get("id")): item
        for item in components
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    result: dict[str, DerivedComponentGeometry] = {}
    for component_id, component in by_id.items():
        result[component_id] = derive_component_geometry(component, by_id)

    return result


def derive_component_geometry(
    component: dict[str, Any],
    by_id: dict[str, dict[str, Any]] | None = None,
) -> DerivedComponentGeometry:
    """Return geometry-derived local properties for one component."""
    ctype = str(component.get("type") or "")
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    density = _density(parameters)
    if ctype == "org.setuav.core:lifting-surface":
        return _lifting_surface(component, density)
    if ctype == "org.setuav.core:control-surface" and by_id is not None:
        parent = by_id.get(str(_frame_parent(component) or ""))
        if parent is not None:
            return _control_surface(component, parent, density)
    if ctype == "org.setuav.core:fuselage":
        return _fuselage(component, density)
    return DerivedComponentGeometry(_zero_transform(), _empty_envelope(), None, 0.0)


def _lifting_surface(component: dict[str, Any], density: float) -> DerivedComponentGeometry:
    geometry = _geometry(component)
    profiles = geometry.get("profiles")
    if not isinstance(profiles, list) or len(profiles) < 2:
        return DerivedComponentGeometry(_zero_transform(), _empty_envelope(), None, 0.0)
    bounds, area_mm2, thickness_ratio = _surface_bounds(profiles)
    mirror = bool(geometry.get("mirror"))
    if mirror:
        bounds[1] = -bounds[1] - bounds[4]
        bounds[4] *= 2.0
        area_mm2 *= 2.0
    span = max(bounds[4], 0.0)
    mean_chord = area_mm2 / span if span > 1e-9 else 0.0
    volume = area_mm2 * mean_chord * max(thickness_ratio, 0.01) * 0.5
    return DerivedComponentGeometry(
        _zero_transform(), _box_from_bounds(bounds), _mass(volume, density), volume
    )


def _control_surface(
    component: dict[str, Any],
    parent: dict[str, Any],
    density: float,
) -> DerivedComponentGeometry:
    parent_geom = _geometry(parent)
    profiles = parent_geom.get("profiles")
    params = component.get("parameters")
    params = params if isinstance(params, dict) else {}
    geometry = params.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    if not isinstance(profiles, list) or len(profiles) < 2:
        return DerivedComponentGeometry(_zero_transform(), _empty_envelope(), None, 0.0)
    profile_values = [_profile_values(item) for item in profiles]
    y_root = profile_values[0][1]
    y_tip = profile_values[-1][1]
    semi_span = max(abs(y_tip - y_root), 1.0)
    start = _span_value(geometry, "start", semi_span)
    end = _span_value(geometry, "end", semi_span)
    if end < start:
        start, end = end, start
    span_dir = 1.0 if y_tip >= y_root else -1.0
    center_s = (start + end) * 0.5
    center_y = y_root + span_dir * center_s
    profile = _interpolate_profile(profile_values, center_y)
    local_chord = profile[3]
    x_le = profile[0]
    x_h = _control_hinge_fraction(
        geometry,
        profile_values,
        y_root=y_root,
        center_s=center_s,
        local_chord=local_chord,
    )
    chord = max((1.0 - x_h) * local_chord, 0.0)
    _, _, local_thickness = _surface_bounds(profiles)
    thickness = max(local_chord * local_thickness, 0.5)
    mirrored = bool(parent_geom.get("mirror"))
    width = max(end - start, 0.0) * (2.0 if mirrored else 1.0)
    volume = max(chord * width * thickness * 0.5, 0.0)
    # Match the geometry engine's section frame, including sweep, twist and
    # dihedral. The control component's origin is the centre of the flap bay.
    try:
        from setuav_studio.plugins.geometry.engine.transforms import section_transform, transform_point
        twist_location = _number(parent_geom.get("twist_location", 0.25))
        matrix = section_transform(
            _profile_dict(profile),
            chord=local_chord,
            twist_location=twist_location,
        )
        center = transform_point(matrix, ((x_h + (1.0 - x_h) * 0.5) * local_chord, 0.0, 0.0))
    except Exception:
        center = (x_le + (x_h + (1.0 - x_h) * 0.5) * local_chord, center_y, profile[2])
    if mirrored:
        center = (center[0], 0.0, center[2])
    rotation = profile[5]
    return DerivedComponentGeometry(
        {
            "position": {"x": center[0], "y": center[1], "z": center[2]},
            "rotation": {"roll": rotation[0], "pitch": rotation[1], "yaw": rotation[2]},
        },
        {"shape": "box", "size_mm": {"x": chord, "y": width, "z": thickness},
         "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0}},
        _mass(volume, density), volume
    )


def _fuselage(component: dict[str, Any], density: float) -> DerivedComponentGeometry:
    geometry = _geometry(component)
    segments = geometry.get("segments")
    points: list[tuple[float, float, float, float, float]] = []
    for segment in segments if isinstance(segments, list) else []:
        for section in segment.get("sections", []) if isinstance(segment, dict) else []:
            if not isinstance(section, dict):
                continue
            pos = section.get("position") if isinstance(section.get("position"), dict) else {}
            profile = section.get("profile") if isinstance(section.get("profile"), dict) else {}
            points.append((_number(pos.get("x")), _number(pos.get("y")), _number(pos.get("z")),
                           _number(profile.get("width")), _number(profile.get("height"))))
    if not points:
        return DerivedComponentGeometry(_zero_transform(), _empty_envelope(), None, 0.0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    min_y = min(y - w * 0.5 for _, y, _, w, _ in points)
    max_y = max(y + w * 0.5 for _, y, _, w, _ in points)
    min_z = min(z - h * 0.5 for _, _, z, _, h in points)
    max_z = max(z + h * 0.5 for _, _, z, _, h in points)
    bounds = [min(xs), min_y, min_z,
              max(xs) - min(xs), max_y - min_y, max_z - min_z]
    volume = bounds[3] * bounds[4] * bounds[5] * 0.35
    return DerivedComponentGeometry(_zero_transform(), _box_from_bounds(bounds), _mass(volume, density), volume)


def _surface_bounds(profiles: list[Any]) -> tuple[list[float], float, float]:
    values = [_profile_values(item) for item in profiles]
    bounds = [float("inf"), float("inf"), float("inf"), -float("inf"), -float("inf"), -float("inf")]
    area = 0.0
    thicknesses: list[float] = []
    for index, value in enumerate(values):
        x, y, z, chord, thickness, _rotation = value
        bounds[0] = min(bounds[0], x)
        bounds[3] = max(bounds[3], x + chord)
        bounds[1] = min(bounds[1], y)
        bounds[3] = max(bounds[3], x + chord)
        bounds[2] = min(bounds[2], z - thickness * chord * 0.5)
        bounds[5] = max(bounds[5], z + thickness * chord * 0.5)
        if index:
            prev = values[index - 1]
            area += abs(y - prev[1]) * (chord + prev[3]) * 0.5
        thicknesses.append(thickness)
    bounds[3] = max(v[0] + v[3] for v in values)
    bounds[4] = max(v[1] for v in values)
    return [bounds[0], bounds[1], bounds[2], bounds[3] - bounds[0], bounds[4] - bounds[1], bounds[5] - bounds[2]], area, max(thicknesses or [0.12])


def _profile_values(profile: Any) -> tuple[float, float, float, float, float, tuple[float, float, float]]:
    profile = profile if isinstance(profile, dict) else {}
    pos = profile.get("position") if isinstance(profile.get("position"), dict) else {}
    chord = max(_number(profile.get("chord")), 0.0)
    rotation = profile.get("rotation") if isinstance(profile.get("rotation"), dict) else {}
    return (_number(pos.get("x")), _number(pos.get("y")), _number(pos.get("z")), chord, _airfoil_thickness(profile.get("airfoil")),
            (_number(rotation.get("x", rotation.get("roll"))), _number(rotation.get("y", rotation.get("pitch"))), _number(rotation.get("z", rotation.get("yaw")))))


def _interpolate_profile(
    values: list[tuple[float, float, float, float, float, tuple[float, float, float]]],
    y: float,
) -> tuple[float, float, float, float, float, tuple[float, float, float]]:
    values = sorted(values, key=lambda value: value[1])
    if y <= values[0][1]:
        return values[0]
    if y >= values[-1][1]:
        return values[-1]
    for left, right in zip(values, values[1:]):
        if left[1] <= y <= right[1]:
            t = (y - left[1]) / max(right[1] - left[1], 1e-9)
            rotation = tuple(
                left[5][axis] + t * (right[5][axis] - left[5][axis])
                for axis in range(3)
            )
            return tuple(
                left[index] + t * (right[index] - left[index])
                for index in range(5)
            ) + (rotation,)  # type: ignore[return-value]
    return values[0]


def _interpolate_planform(
    values: list[tuple[float, float, float, float, float, tuple[float, float, float]]],
    y: float,
) -> tuple[float, float]:
    profile = _interpolate_profile(values, y)
    return profile[0], profile[3]


def _control_hinge_fraction(
    geometry: dict[str, Any],
    profiles: list[tuple[float, float, float, float, float, tuple[float, float, float]]],
    *,
    y_root: float,
    center_s: float,
    local_chord: float,
) -> float:
    """Return the hinge x/chord fraction using the same rules as the loft builder."""
    mode = str(geometry.get("chord_mode") or "ratio").lower()
    span_start = _span_value(geometry, "start", max(abs(profiles[-1][1] - y_root), 1.0))
    chord_value = max(_number(geometry.get("chord", 40.0)), 1.0)
    hinge_sweep = geometry.get("hinge_sweep")
    if hinge_sweep is not None:
        span_dir = 1.0 if profiles[-1][1] >= y_root else -1.0
        start_profile = _interpolate_profile(profiles, y_root + span_dir * span_start)
        x_h0 = start_profile[0] + start_profile[3] - chord_value
        x_h = x_h0 + (center_s - span_start) * math.tan(math.radians(_number(hinge_sweep)))
        center_profile = _interpolate_profile(profiles, y_root + span_dir * center_s)
        return min(max((x_h - center_profile[0]) / max(local_chord, 1.0), 0.05), 0.95)
    if mode == "ratio" and "chord_fraction" in geometry:
        return 1.0 - min(max(_number(geometry.get("chord_fraction")), 0.05), 0.95)
    return 1.0 - min(max(chord_value / max(local_chord, 1.0), 0.05), 0.95)


def _profile_dict(
    profile: tuple[float, float, float, float, float, tuple[float, float, float]],
) -> dict[str, Any]:
    return {
        "position": {"x": profile[0], "y": profile[1], "z": profile[2]},
        "chord": profile[3],
        "rotation": {"x": profile[5][0], "y": profile[5][1], "z": profile[5][2]},
    }


def _span_value(geometry: dict[str, Any], suffix: str, semispan: float) -> float:
    mode = str(geometry.get("span_mode") or "ratio").lower()
    key = "span_" + suffix
    eta_key = "eta_" + suffix
    if mode == "ratio" and eta_key in geometry:
        return max(0.0, min(1.0, _number(geometry.get(eta_key)))) * semispan
    if mode == "dimension" and key in geometry:
        return max(0.0, _number(geometry.get(key)))
    if eta_key in geometry:
        eta = geometry.get("eta_" + suffix, geometry.get(key, 0.0))
        return max(0.0, min(1.0, _number(eta))) * semispan
    return max(0.0, _number(geometry.get(key)))


def _airfoil_thickness(value: object) -> float:
    points: Any = None
    if isinstance(value, dict):
        if value.get("type") == "coordinates":
            points = value.get("points")
        elif value.get("type") == "naca":
            value = value.get("code")
    if isinstance(value, str):
        code = "".join(ch for ch in value if ch.isdigit())
        if len(code) >= 4:
            try:
                return max(float(code[2:4]) / 100.0, 0.01)
            except ValueError:
                pass
    if isinstance(points, list):
        z_values = [_number(item[1]) for item in points if isinstance(item, (list, tuple)) and len(item) >= 2]
        if z_values:
            return max(max(z_values) - min(z_values), 0.01)
    return 0.12


def _box_from_bounds(bounds: list[float]) -> dict[str, Any]:
    return {"shape": "box", "size_mm": {"x": bounds[3], "y": bounds[4], "z": bounds[5]},
            "offset_mm": {"x": bounds[0] + bounds[3] * 0.5, "y": bounds[1] + bounds[4] * 0.5, "z": bounds[2] + bounds[5] * 0.5}}


def _mass(volume_mm3: float, density_kg_m3: float) -> float:
    return volume_mm3 / 1_000_000_000.0 * density_kg_m3 * 1000.0


def _density(parameters: dict[str, Any]) -> float:
    return max(_number(parameters.get("material_density_kg_m3", parameters.get("geometry_density_kg_m3", DEFAULT_DENSITY_KG_M3))), 1.0)


def _declared_mass(component: dict[str, Any]) -> float | None:
    params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
    value = component.get("mass", params.get("mass"))
    return _number(value) if value is not None else None


def _geometry(component: dict[str, Any]) -> dict[str, Any]:
    params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
    value = params.get("geometry")
    return value if isinstance(value, dict) else {}


def _frame_parent(component: dict[str, Any]) -> str | None:
    value = component.get("attach_to") or component.get("parent")
    return str(value) if isinstance(value, str) and value else None


def _zero_transform() -> dict[str, Any]:
    return {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}}


def _empty_envelope() -> dict[str, Any]:
    return {"shape": "box", "size_mm": {"x": 0.0, "y": 0.0, "z": 0.0}, "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0}}


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
