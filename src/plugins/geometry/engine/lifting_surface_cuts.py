"""Control surface spanwise partitioning and hinge deflection geometry."""

from __future__ import annotations

import math
from collections.abc import Callable
from itertools import pairwise
from typing import Any, Literal

from ..viewport.palettes import control_surface_color, wing_color
from .data import LoftGeometry, Point3D, Section
from .lifting_surface_math import (
    mapping,
    number,
    rotate_section_around_axis,
    sample_structured_airfoil_round,
)
from .transforms import section_transform, transform_point


def build_lifting_surface_with_control_surfaces(
    comp_id: str,
    profiles: list[dict[str, Any]],
    control_surfaces: list[dict[str, Any]],
    interpolation: Literal["linear", "smooth"],
    twist_location: float = 0.25,
    te_thickness: float = 0.0,
    thickness_scale: float = 1.0,
    camber_scale: float = 1.0,
    section_align: str = "xz",
    *,
    plain_surface_builder: Callable[..., tuple[LoftGeometry, ...]],
    interpolate_station_fn: Callable[
        ..., tuple[float, dict[str, Any], tuple[tuple[float, float], ...]]
    ],
    apply_shaping_fn: Callable[..., tuple[tuple[float, float], ...]],
    section_with_align_fn: Callable[..., Section],
) -> tuple[LoftGeometry, ...]:
    """Build spanwise wing partitions with independent control-surface bays."""
    span_values, root, semi_span, span_direction = profile_span_context(profiles)
    valid_controls = valid_control_surfaces(
        control_surfaces,
        min(span_values),
        max(span_values),
        root,
        semi_span,
        span_direction,
    )
    if not valid_controls:
        return plain_surface_builder(
            comp_id,
            profiles,
            interpolation,
            te_thickness,
            thickness_scale,
            camber_scale,
            section_align,
        )

    lofts: list[LoftGeometry] = []
    for stations, control in span_partitions(
        span_values,
        valid_controls,
        span_direction,
    ):
        if control is None:
            lofts.append(
                build_uncut_segment(
                    comp_id,
                    stations,
                    span_values,
                    profiles,
                    interpolation,
                    twist_location,
                    te_thickness,
                    thickness_scale,
                    camber_scale,
                    section_align,
                    interpolate_station_fn=interpolate_station_fn,
                    apply_shaping_fn=apply_shaping_fn,
                    section_with_align_fn=section_with_align_fn,
                )
            )
        else:
            lofts.extend(
                build_control_segment(
                    comp_id,
                    stations,
                    span_values,
                    profiles,
                    control,
                    interpolation,
                    root,
                    span_direction,
                    twist_location,
                    te_thickness,
                    thickness_scale,
                    camber_scale,
                    section_align,
                    interpolate_station_fn=interpolate_station_fn,
                    apply_shaping_fn=apply_shaping_fn,
                    section_with_align_fn=section_with_align_fn,
                )
            )
    return tuple(lofts)


def profile_span_context(
    profiles: list[dict[str, Any]],
) -> tuple[list[float], float, float, float]:
    values = [number(mapping(profile.get("position")).get("y")) for profile in profiles]
    root = values[0]
    tip = values[-1]
    return values, root, max(abs(tip - root), 1.0), 1.0 if tip >= root else -1.0


def valid_control_surfaces(
    controls: list[dict[str, Any]],
    min_span: float,
    max_span: float,
    root: float,
    semi_span: float,
    span_direction: float,
) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for index, control in enumerate(controls):
        if not isinstance(control, dict):
            continue
        start, end = control_span_values(control, semi_span)
        if end <= start:
            continue
        y_start = root + span_direction * min(start, end)
        y_end = root + span_direction * max(start, end)
        y_min = max(min_span, min(y_start, y_end))
        y_max = min(max_span, max(y_start, y_end))
        if y_max <= y_min + 1e-3:
            continue
        valid.append(
            normalized_control_surface(
                control,
                index,
                start,
                end,
                y_min,
                y_max,
                semi_span,
            )
        )
    return valid


def control_span_values(control: dict[str, Any], semi_span: float) -> tuple[float, float]:
    mode = str(control.get("span_mode", "ratio")).lower()
    if mode == "dimension" and ("span_start" in control or "span_end" in control):
        return float(control.get("span_start", 0.0)), float(control.get("span_end", 0.0))
    if mode == "ratio" and ("eta_start" in control or "eta_end" in control):
        return (
            float(control.get("eta_start", 0.0)) * semi_span,
            float(control.get("eta_end", 0.0)) * semi_span,
        )
    if "span_start" in control or "span_end" in control:
        return float(control.get("span_start", 0.0)), float(control.get("span_end", 0.0))
    if "eta_start" in control or "eta_end" in control:
        return (
            float(control.get("eta_start", 0.0)) * semi_span,
            float(control.get("eta_end", 0.0)) * semi_span,
        )
    return 0.0, 0.0


def normalized_control_surface(
    control: dict[str, Any],
    index: int,
    start: float,
    end: float,
    y_min: float,
    y_max: float,
    semi_span: float,
) -> dict[str, Any]:
    span_start = min(start, end)
    span_end = max(start, end)
    return {
        "tag": str(control.get("tag") or f"CS_{index + 1}"),
        "type": str(control.get("type") or "aileron"),
        "y_min": y_min,
        "y_max": y_max,
        "s_start": span_start,
        "s_end": span_end,
        "eta_start": round(span_start / semi_span, 4),
        "eta_end": round(span_end / semi_span, 4),
        "chord_fraction": control_chord_fraction(control),
        "chord": max(number(control.get("chord", 40.0)), 1.0),
        "hinge_sweep": (
            number(control.get("hinge_sweep")) if control.get("hinge_sweep") is not None else None
        ),
        "deflection": number(control.get("deflection", 0.0)),
    }


def control_chord_fraction(control: dict[str, Any]) -> float | None:
    if str(control.get("chord_mode", "ratio")).lower() == "dimension":
        return None
    value = control.get("chord_fraction")
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def span_partitions(
    span_values: list[float],
    controls: list[dict[str, Any]],
    span_direction: float,
) -> list[tuple[list[float], dict[str, Any] | None]]:
    cuts = {min(span_values), max(span_values)}
    for control in controls:
        cuts.add(control["y_min"])
        cuts.add(control["y_max"])
    sorted_cuts = sorted(cuts)
    partitions: list[tuple[list[float], dict[str, Any] | None]] = []
    for start, end in pairwise(sorted_cuts):
        if abs(end - start) < 1e-4:
            continue
        midpoint = (start + end) * 0.5
        control = next(
            (
                candidate
                for candidate in controls
                if candidate["y_min"] <= midpoint <= candidate["y_max"]
            ),
            None,
        )
        stations = [
            start,
            *[value for value in sorted(span_values) if start + 1e-3 < value < end - 1e-3],
            end,
        ]
        if span_direction < 0:
            stations.sort(reverse=True)
        partitions.append((stations, control))
    return partitions


def build_uncut_segment(
    comp_id: str,
    stations: list[float],
    span_values: list[float],
    profiles: list[dict[str, Any]],
    interpolation: Literal["linear", "smooth"],
    twist_location: float,
    te_thickness: float,
    thickness_scale: float,
    camber_scale: float,
    section_align: str,
    *,
    interpolate_station_fn: Callable[
        ..., tuple[float, dict[str, Any], tuple[tuple[float, float], ...]]
    ],
    apply_shaping_fn: Callable[..., tuple[tuple[float, float], ...]],
    section_with_align_fn: Callable[..., Section],
) -> LoftGeometry:
    sections: list[Section] = []
    for station in stations:
        chord, profile, coordinates = interpolate_station_fn(station, profiles)
        coordinates = apply_shaping_fn(
            coordinates,
            te_thickness,
            thickness_scale,
            camber_scale,
        )
        rotation = mapping(profile.get("rotation"))
        dihedral = math.radians(number(rotation.get("x", rotation.get("roll", 0.0))))
        matrix = section_transform(profile, chord=chord, twist_location=twist_location)
        main_2d, _ = sample_structured_airfoil_round(
            coordinates,
            x_h=1.0,
            is_flap=False,
        )
        sections.append(
            section_with_align_fn(
                matrix,
                chord,
                main_2d,
                dihedral,
                section_align,
                is_station=is_original_station(station, span_values),
            )
        )
    return LoftGeometry(
        component_id=comp_id,
        sections=tuple(sections),
        color=wing_color(),
        interpolation=interpolation,
        station_spacing=15.0,
        closed_ends=True,
    )


def build_control_segment(
    comp_id: str,
    stations: list[float],
    span_values: list[float],
    profiles: list[dict[str, Any]],
    control: dict[str, Any],
    interpolation: Literal["linear", "smooth"],
    root: float,
    span_direction: float,
    twist_location: float,
    te_thickness: float,
    thickness_scale: float,
    camber_scale: float,
    section_align: str,
    *,
    interpolate_station_fn: Callable[
        ..., tuple[float, dict[str, Any], tuple[tuple[float, float], ...]]
    ],
    apply_shaping_fn: Callable[..., tuple[tuple[float, float], ...]],
    section_with_align_fn: Callable[..., Section],
) -> tuple[LoftGeometry, LoftGeometry]:
    hinge_orig = hinge_origin(control, root, span_direction, profiles, interpolate_station_fn)
    main_sections: list[Section] = []
    flap_sections: list[Section] = []
    hinge_points: list[Point3D] = []
    for station in stations:
        main, flap, hinge = control_station_sections(
            station,
            span_values,
            profiles,
            control,
            hinge_orig,
            root,
            twist_location,
            te_thickness,
            thickness_scale,
            camber_scale,
            section_align,
            interpolate_station_fn=interpolate_station_fn,
            apply_shaping_fn=apply_shaping_fn,
            section_with_align_fn=section_with_align_fn,
        )
        main_sections.append(main)
        flap_sections.append(flap)
        hinge_points.append(hinge)
    flap_sections = deflected_sections(
        flap_sections,
        hinge_points,
        control["deflection"],
    )
    return (
        LoftGeometry(
            component_id=comp_id,
            sections=tuple(main_sections),
            color=wing_color(),
            interpolation=interpolation,
            station_spacing=15.0,
            closed_ends=True,
        ),
        LoftGeometry(
            component_id=f"{comp_id}:{control['tag']}",
            sections=tuple(flap_sections),
            color=control_surface_color(),
            interpolation=interpolation,
            station_spacing=15.0,
            closed_ends=True,
        ),
    )


def hinge_origin(
    control: dict[str, Any],
    root: float,
    span_direction: float,
    profiles: list[dict[str, Any]],
    interpolate_station_fn: Callable[
        ..., tuple[float, dict[str, Any], tuple[tuple[float, float], ...]]
    ],
) -> float:
    station = root + span_direction * control["s_start"]
    chord, profile, _ = interpolate_station_fn(station, profiles)
    position = profile.get("position")
    leading_edge = float(position.get("x", 0.0)) if isinstance(position, dict) else 0.0
    return leading_edge + chord - control["chord"]


def control_station_sections(
    station: float,
    span_values: list[float],
    profiles: list[dict[str, Any]],
    control: dict[str, Any],
    hinge_orig: float,
    root: float,
    twist_location: float,
    te_thickness: float,
    thickness_scale: float,
    camber_scale: float,
    section_align: str,
    *,
    interpolate_station_fn: Callable[
        ..., tuple[float, dict[str, Any], tuple[tuple[float, float], ...]]
    ],
    apply_shaping_fn: Callable[..., tuple[tuple[float, float], ...]],
    section_with_align_fn: Callable[..., Section],
) -> tuple[Section, Section, Point3D]:
    chord, profile, coordinates = interpolate_station_fn(station, profiles)
    coordinates = apply_shaping_fn(
        coordinates,
        te_thickness,
        thickness_scale,
        camber_scale,
    )
    rotation = mapping(profile.get("rotation"))
    dihedral = math.radians(number(rotation.get("x", rotation.get("roll", 0.0))))
    matrix = section_transform(profile, chord=chord, twist_location=twist_location)
    position = mapping(profile.get("position"))
    hinge_frac = hinge_fraction(
        control,
        hinge_orig,
        abs(station - root),
        number(position.get("x")),
        chord,
    )
    main_2d, hinge = sample_structured_airfoil_round(
        coordinates,
        x_h=hinge_frac,
        is_flap=False,
    )
    flap_2d, _ = sample_structured_airfoil_round(
        coordinates,
        x_h=hinge_frac,
        is_flap=True,
    )
    main = section_with_align_fn(
        matrix,
        chord,
        main_2d,
        dihedral,
        section_align,
        is_station=is_original_station(station, span_values),
    )
    flap = section_with_align_fn(
        matrix,
        chord,
        flap_2d,
        dihedral,
        section_align,
        is_station=False,
    )
    hinge_3d = transform_point(
        matrix,
        (hinge[0] * chord, 0.0, hinge[1] * chord),
    )
    return main, flap, hinge_3d


def hinge_fraction(
    control: dict[str, Any],
    hinge_orig: float,
    current_span: float,
    leading_edge: float,
    chord: float,
) -> float:
    sweep = control["hinge_sweep"]
    chord_fraction = control.get("chord_fraction")
    if sweep is not None:
        hinge_x = hinge_orig + (current_span - control["s_start"]) * math.tan(math.radians(sweep))
        relative = (hinge_x - leading_edge) / max(chord, 1.0)
        return min(max(relative, 0.05), 0.95)
    if chord_fraction is not None and chord_fraction > 0.0:
        return 1.0 - min(max(chord_fraction, 0.05), 0.95)
    chord_depth = control["chord"] / max(chord, 1.0)
    return 1.0 - min(max(chord_depth, 0.05), 0.95)


def is_original_station(station: float, span_values: list[float]) -> bool:
    return any(abs(station - value) < 1e-3 for value in span_values)


def deflected_sections(
    sections: list[Section],
    hinge_points: list[Point3D],
    deflection: float,
) -> list[Section]:
    if abs(deflection) <= 1e-4 or len(hinge_points) < 2:
        return sections
    origin = hinge_points[0]
    end = hinge_points[-1]
    direction = (
        end[0] - origin[0],
        end[1] - origin[1],
        end[2] - origin[2],
    )
    return [
        rotate_section_around_axis(section, origin, direction, deflection) for section in sections
    ]


__all__ = [
    "build_control_segment",
    "build_lifting_surface_with_control_surfaces",
    "build_uncut_segment",
    "control_chord_fraction",
    "control_span_values",
    "control_station_sections",
    "deflected_sections",
    "hinge_fraction",
    "hinge_origin",
    "is_original_station",
    "normalized_control_surface",
    "profile_span_context",
    "span_partitions",
    "valid_control_surfaces",
]
