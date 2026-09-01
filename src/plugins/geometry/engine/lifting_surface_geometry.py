"""Geometry builder for lifting surfaces and deflected 3D control surfaces."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any, Literal

from ..viewport.palettes import control_surface_color, wing_color
from .airfoil import apply_airfoil_shaping, sample_airfoil_points
from .data import LoftGeometry, Point3D, Section
from .transforms import Matrix4, section_transform, transform_point

sample_airfoil = sample_airfoil_points


def build_lifting_surface_geometry(
    component: dict[str, Any],
) -> tuple[LoftGeometry, ...]:
    """Generate loft geometries for a lifting surface and its control surfaces."""
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    profiles = geometry.get("profiles")
    if not isinstance(profiles, list) or len(profiles) < 2:
        return ()

    comp_id = str(component.get("id") or "lifting-surface")
    interpolation = "smooth" if len(profiles) > 2 else "linear"

    control_surfaces = geometry.get("control_surfaces")
    twist_location = float(geometry.get("twist_location", 0.25))

    # Airfoil Shaping parameters
    shaping = geometry.get("airfoil_shaping")
    shaping = shaping if isinstance(shaping, dict) else {}
    te_thickness = float(shaping.get("te_thickness", 0.0))  # fraction of chord, e.g. 0.004
    thickness_scale = float(shaping.get("thickness_scale", 1.0))
    camber_scale = float(shaping.get("camber_scale", 1.0))
    # Section alignment: "xz" (default) | "normal" (perpendicular to span)
    section_align = str(geometry.get("section_align", "xz")).lower()

    tip_treatment = geometry.get("tip_treatment")
    tip_treatment = tip_treatment if isinstance(tip_treatment, dict) else {}
    tip_type = str(tip_treatment.get("type", "flat")).lower()
    tip_length = float(tip_treatment.get("length", 20.0))
    tip_offset_x = float(tip_treatment.get("offset_x", 0.0))

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
                sections=sections,
                color=wing_color(),
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
    if tip_type in ("round", "sharp") and tip_length > 0.0:
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

        # Compute LE and TE sweep slopes from the last two profiles
        # so the tip cap follows both leading and trailing edge lines
        p_prev = profiles[-2] if len(profiles) >= 2 else profiles[-1]
        p_tip = profiles[-1]
        prev_pos = p_prev.get("position", {}) if isinstance(p_prev.get("position"), dict) else {}
        tip_pos = p_tip.get("position", {}) if isinstance(p_tip.get("position"), dict) else {}
        dy = float(tip_pos.get("y", 0.0)) - float(prev_pos.get("y", 0.0))
        if abs(dy) > 1e-4:
            dx_le = float(tip_pos.get("x", 0.0)) - float(prev_pos.get("x", 0.0))
            dx_te = (float(tip_pos.get("x", 0.0)) + _number(p_tip.get("chord"))) - (
                float(prev_pos.get("x", 0.0)) + _number(p_prev.get("chord"))
            )
            le_sweep_slope = dx_le / dy
            te_sweep_slope = dx_te / dy
        else:
            le_sweep_slope = 0.0
            te_sweep_slope = 0.0

        tip_profile = profiles[-1]
        tip_cap = _build_tip_cap_loft(
            comp_id=comp_id,
            tip_profile=tip_profile,
            tip_type=tip_type,
            tip_length=tip_length,
            offset_x=tip_offset_x,
            span_dir=span_dir,
            le_sweep_slope=le_sweep_slope,
            te_sweep_slope=te_sweep_slope,
            twist_location=twist_location,
        )
        if tip_cap is not None:
            lofts_list.append(tip_cap)

    elif tip_type == "winglet":
        # Winglet: a separate swept/canted surface growing from the tip
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
            dx_te = (float(tip_pos.get("x", 0.0)) + _number(p_tip.get("chord"))) - (
                float(prev_pos.get("x", 0.0)) + _number(p_prev.get("chord"))
            )
            incoming_le_sweep_deg = math.degrees(math.atan2(dx_le, abs(dy)))
            incoming_te_sweep_deg = math.degrees(math.atan2(dx_te, abs(dy)))
        else:
            incoming_le_sweep_deg = 0.0
            incoming_te_sweep_deg = 0.0

        match_tangent = bool(tip_treatment.get("match_wing_tangent", True))
        winglet_height = float(tip_treatment.get("winglet_height", 130.0))
        cant_angle = float(tip_treatment.get("cant_angle", 80.0))
        cant_root = float(tip_treatment.get("cant_root", 0.0))
        cant_tip = tip_treatment.get("cant_tip")
        blend_radius = float(
            tip_treatment.get("blend_radius", 45.0 if "blend_radius" in tip_treatment else 0.0)
        )

        # Sweep & Curvatures
        sweep_default = float(tip_treatment.get("winglet_sweep", 20.0))
        le_sweep_root = tip_treatment.get("le_sweep_root", tip_treatment.get("sweep_root"))
        le_sweep_tip = tip_treatment.get("le_sweep_tip", tip_treatment.get("sweep_tip", 48.0))
        le_curvature = float(
            tip_treatment.get("le_curvature", tip_treatment.get("scimitar_offset", 0.0))
        )

        te_sweep_root = tip_treatment.get("te_sweep_root")
        te_sweep_tip = tip_treatment.get("te_sweep_tip")
        te_curvature = float(tip_treatment.get("te_curvature", 0.0))

        toe_angle = float(tip_treatment.get("toe_angle", 0.0))
        toe_root = tip_treatment.get("toe_root")
        toe_tip = tip_treatment.get("toe_tip", -1.5 if "toe_tip" not in tip_treatment else 0.0)

        root_chord_scale = float(tip_treatment.get("root_chord_scale", 1.0))
        tip_chord_scale = float(tip_treatment.get("tip_chord_scale", 0.45))
        tip_thickness_scale = float(tip_treatment.get("tip_thickness_scale", 0.7))
        taper_curve = float(tip_treatment.get("taper_curve", 1.0))

        winglet_loft = _build_winglet_loft(
            comp_id=comp_id,
            tip_profile=profiles[-1],
            span_dir=span_dir,
            winglet_height=winglet_height,
            cant_angle_deg=cant_angle,
            cant_root_deg=float(cant_root) if cant_root is not None else None,
            cant_tip_deg=float(cant_tip) if cant_tip is not None else None,
            blend_radius=blend_radius,
            match_wing_tangent=match_tangent,
            incoming_le_sweep_deg=incoming_le_sweep_deg,
            incoming_te_sweep_deg=incoming_te_sweep_deg,
            sweep_deg=sweep_default,
            le_sweep_root_deg=float(le_sweep_root) if le_sweep_root is not None else None,
            le_sweep_tip_deg=float(le_sweep_tip) if le_sweep_tip is not None else None,
            le_curvature=le_curvature,
            te_sweep_root_deg=float(te_sweep_root) if te_sweep_root is not None else None,
            te_sweep_tip_deg=float(te_sweep_tip) if te_sweep_tip is not None else None,
            te_curvature=te_curvature,
            toe_angle_deg=toe_angle,
            toe_root_deg=float(toe_root) if toe_root is not None else None,
            toe_tip_deg=float(toe_tip) if toe_tip is not None else None,
            root_chord_scale=root_chord_scale,
            tip_chord_scale=tip_chord_scale,
            tip_thickness_scale=tip_thickness_scale,
            taper_curve=taper_curve,
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
    """Build a 3D Section, optionally rotating the airfoil plane to be normal to the span direction.

    When section_align == 'normal', the 2D airfoil profile is treated as lying in a plane perpendicular
    to the span (Y) axis of the wing rather than the global XZ plane.  This corrects the effective
    cross-section at high dihedral angles so that the section thickness appears correct when viewed
    perpendicular to the wing surface — matching OpenVSP / AVL behaviour.
    """
    if section_align == "normal" and abs(dihedral_rad) > 1e-4:
        # Rotate the 2D points around the X-axis by dihedral_rad before applying the full matrix.
        # In the wing-local frame x=chord, z=thickness; dihedral tilts the z-axis toward Y.
        cos_d = math.cos(dihedral_rad)
        sin_d = math.sin(dihedral_rad)
        corrected: list[tuple[float, float, float]] = []
        for x, z in main_2d:
            # After dihedral rotation: new y_local = -z*sin_d, new z_local = z*cos_d
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
    chord = _number(profile.get("chord"))
    if chord <= 0:
        return None
    coords = sample_airfoil_points(profile.get("airfoil"))
    coords = _apply_shaping(coords, te_thickness, thickness_scale, camber_scale)
    rot = _mapping(profile.get("rotation"))
    dihedral_rad = math.radians(_number(rot.get("x", rot.get("roll", 0.0))))
    matrix = section_transform(profile, chord=chord, twist_location=twist_location)
    main_2d, _ = _sample_structured_airfoil_round(coords, x_h=1.0, is_flap=False)
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
    """Build spanwise wing partitions with independent control-surface bays."""
    span_values, root, semi_span, span_direction = _profile_span_context(profiles)
    valid_controls = _valid_control_surfaces(
        control_surfaces,
        min(span_values),
        max(span_values),
        root,
        semi_span,
        span_direction,
    )
    if not valid_controls:
        return _plain_lifting_surface(
            comp_id,
            profiles,
            interpolation,
            te_thickness,
            thickness_scale,
            camber_scale,
            section_align,
        )

    lofts: list[LoftGeometry] = []
    for stations, control in _span_partitions(
        span_values,
        valid_controls,
        span_direction,
    ):
        if control is None:
            lofts.append(
                _build_uncut_segment(
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
                )
            )
        else:
            lofts.extend(
                _build_control_segment(
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
                )
            )
    return tuple(lofts)


def _profile_span_context(
    profiles: list[dict[str, Any]],
) -> tuple[list[float], float, float, float]:
    values = [_number(_mapping(profile.get("position")).get("y")) for profile in profiles]
    root = values[0]
    tip = values[-1]
    return values, root, max(abs(tip - root), 1.0), 1.0 if tip >= root else -1.0


def _valid_control_surfaces(
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
        start, end = _control_span_values(control, semi_span)
        if end <= start:
            continue
        y_start = root + span_direction * min(start, end)
        y_end = root + span_direction * max(start, end)
        y_min = max(min_span, min(y_start, y_end))
        y_max = min(max_span, max(y_start, y_end))
        if y_max <= y_min + 1e-3:
            continue
        valid.append(
            _normalized_control_surface(
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


def _control_span_values(control: dict[str, Any], semi_span: float) -> tuple[float, float]:
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


def _normalized_control_surface(
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
        "chord_fraction": _control_chord_fraction(control),
        "chord": max(_number(control.get("chord", 40.0)), 1.0),
        "hinge_sweep": (
            _number(control.get("hinge_sweep")) if control.get("hinge_sweep") is not None else None
        ),
        "deflection": _number(control.get("deflection", 0.0)),
    }


def _control_chord_fraction(control: dict[str, Any]) -> float | None:
    if str(control.get("chord_mode", "ratio")).lower() == "dimension":
        return None
    value = control.get("chord_fraction")
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


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
            sections=sections,
            color=wing_color(),
            interpolation=interpolation,
            station_spacing=15.0,
            closed_ends=True,
        ),
    )


def _span_partitions(
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


def _build_uncut_segment(
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
) -> LoftGeometry:
    sections: list[Section] = []
    for station in stations:
        chord, profile, coordinates = _interpolate_station_props(station, profiles)
        coordinates = _apply_shaping(
            coordinates,
            te_thickness,
            thickness_scale,
            camber_scale,
        )
        rotation = _mapping(profile.get("rotation"))
        dihedral = math.radians(_number(rotation.get("x", rotation.get("roll", 0.0))))
        matrix = section_transform(profile, chord=chord, twist_location=twist_location)
        main_2d, _ = _sample_structured_airfoil_round(
            coordinates,
            x_h=1.0,
            is_flap=False,
        )
        sections.append(
            _section_with_align(
                matrix,
                chord,
                main_2d,
                dihedral,
                section_align,
                is_station=_is_original_station(station, span_values),
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


def _build_control_segment(
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
) -> tuple[LoftGeometry, LoftGeometry]:
    hinge_origin = _hinge_origin(control, root, span_direction, profiles)
    main_sections: list[Section] = []
    flap_sections: list[Section] = []
    hinge_points: list[Point3D] = []
    for station in stations:
        main, flap, hinge = _control_station_sections(
            station,
            span_values,
            profiles,
            control,
            hinge_origin,
            root,
            twist_location,
            te_thickness,
            thickness_scale,
            camber_scale,
            section_align,
        )
        main_sections.append(main)
        flap_sections.append(flap)
        hinge_points.append(hinge)
    flap_sections = _deflected_sections(
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


def _hinge_origin(
    control: dict[str, Any],
    root: float,
    span_direction: float,
    profiles: list[dict[str, Any]],
) -> float:
    station = root + span_direction * control["s_start"]
    chord, profile, _ = _interpolate_station_props(station, profiles)
    position = profile.get("position")
    leading_edge = float(position.get("x", 0.0)) if isinstance(position, dict) else 0.0
    return leading_edge + chord - control["chord"]


def _control_station_sections(
    station: float,
    span_values: list[float],
    profiles: list[dict[str, Any]],
    control: dict[str, Any],
    hinge_origin: float,
    root: float,
    twist_location: float,
    te_thickness: float,
    thickness_scale: float,
    camber_scale: float,
    section_align: str,
) -> tuple[Section, Section, Point3D]:
    chord, profile, coordinates = _interpolate_station_props(station, profiles)
    coordinates = _apply_shaping(
        coordinates,
        te_thickness,
        thickness_scale,
        camber_scale,
    )
    rotation = _mapping(profile.get("rotation"))
    dihedral = math.radians(_number(rotation.get("x", rotation.get("roll", 0.0))))
    matrix = section_transform(profile, chord=chord, twist_location=twist_location)
    position = _mapping(profile.get("position"))
    hinge_fraction = _hinge_fraction(
        control,
        hinge_origin,
        abs(station - root),
        _number(position.get("x")),
        chord,
    )
    main_2d, hinge = _sample_structured_airfoil_round(
        coordinates,
        x_h=hinge_fraction,
        is_flap=False,
    )
    flap_2d, _ = _sample_structured_airfoil_round(
        coordinates,
        x_h=hinge_fraction,
        is_flap=True,
    )
    main = _section_with_align(
        matrix,
        chord,
        main_2d,
        dihedral,
        section_align,
        is_station=_is_original_station(station, span_values),
    )
    flap = _section_with_align(
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


def _hinge_fraction(
    control: dict[str, Any],
    hinge_origin: float,
    current_span: float,
    leading_edge: float,
    chord: float,
) -> float:
    sweep = control["hinge_sweep"]
    chord_fraction = control.get("chord_fraction")
    if sweep is not None:
        hinge_x = hinge_origin + (current_span - control["s_start"]) * math.tan(math.radians(sweep))
        relative = (hinge_x - leading_edge) / max(chord, 1.0)
        return min(max(relative, 0.05), 0.95)
    if chord_fraction is not None and chord_fraction > 0.0:
        return 1.0 - min(max(chord_fraction, 0.05), 0.95)
    chord_depth = control["chord"] / max(chord, 1.0)
    return 1.0 - min(max(chord_depth, 0.05), 0.95)


def _is_original_station(station: float, span_values: list[float]) -> bool:
    return any(abs(station - value) < 1e-3 for value in span_values)


def _deflected_sections(
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
        _rotate_section_around_axis(section, origin, direction, deflection) for section in sections
    ]


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
        chord = _number(p.get("chord"))
        coords = sample_airfoil_points(p.get("airfoil"))
        return chord, p, coords
    if y >= y_coords[-1]:
        p = sorted_profs[-1]
        chord = _number(p.get("chord"))
        coords = sample_airfoil_points(p.get("airfoil"))
        return chord, p, coords

    idx = 0
    while idx < len(y_coords) - 1 and y_coords[idx + 1] < y:
        idx += 1

    p0, p1 = sorted_profs[idx], sorted_profs[idx + 1]
    y0, y1 = y_coords[idx], y_coords[idx + 1]
    t = (y - y0) / max(y1 - y0, 1e-6)

    c0 = _number(p0.get("chord"))
    c1 = _number(p1.get("chord"))
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


def _split_airfoil_upper_lower(
    coords: tuple[tuple[float, float], ...],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Robustly split any closed airfoil coordinate loop into upper and lower curves (LE -> TE)."""
    le_idx = min(range(len(coords)), key=lambda i: coords[i][0])
    n = len(coords)
    ordered = [coords[(le_idx + i) % n] for i in range(n)]
    te_idx = max(range(len(ordered)), key=lambda i: ordered[i][0])

    path1 = ordered[: te_idx + 1]
    path2 = [ordered[0], *reversed(ordered[te_idx:])]

    avg_z1 = sum(p[1] for p in path1) / max(len(path1), 1)
    avg_z2 = sum(p[1] for p in path2) / max(len(path2), 1)

    if avg_z1 >= avg_z2:
        return path1, path2
    return path2, path1


def _interp_branch_z(branch: list[tuple[float, float]], x_t: float) -> float:
    """Interpolate Z coordinate along a monotonically ordered airfoil branch (LE -> TE)."""
    if not branch:
        return 0.0
    if x_t <= branch[0][0]:
        return branch[0][1]
    if x_t >= branch[-1][0]:
        return branch[-1][1]
    for j in range(len(branch) - 1):
        p0, p1 = branch[j], branch[j + 1]
        if (p0[0] <= x_t <= p1[0]) or (p1[0] <= x_t <= p0[0]):
            dx = p1[0] - p0[0]
            frac = (x_t - p0[0]) / dx if abs(dx) > 1e-9 else 0.0
            return p0[1] + frac * (p1[1] - p0[1])
    return branch[-1][1]


def _sample_structured_airfoil_round(
    coords: tuple[tuple[float, float], ...],
    x_h: float = 1.0,
    is_flap: bool = False,
    n_upper: int = 28,
    n_lower: int = 28,
    n_wall: int = 7,
) -> tuple[tuple[tuple[float, float], ...], tuple[float, float]]:
    """Sample structured 64-point loop with global chord alignment and round circular hinge socket/nose."""
    upper_branch, lower_branch = _split_airfoil_upper_lower(coords)

    z_u_h = _interp_branch_z(upper_branch, x_h)
    z_l_h = _interp_branch_z(lower_branch, x_h)
    z_h = (z_u_h + z_l_h) * 0.5
    r_h = max((z_u_h - z_l_h) * 0.5, 0.0) if x_h < 0.999 else 0.0

    global_x_upper = [0.5 * (1.0 + math.cos(math.pi * i / (n_upper - 1))) for i in range(n_upper)]
    global_x_lower = [0.5 * (1.0 - math.cos(math.pi * i / (n_lower - 1))) for i in range(n_lower)]

    if not is_flap:
        # Main Wing Section (64 pts):
        # Upper points: global aligned grid clamped at x_h
        upper_pts = []
        for i in range(n_upper):
            x_val = global_x_upper[i]
            x_clamped = min(x_val, x_h)
            z_val = _interp_branch_z(upper_branch, x_clamped)
            upper_pts.append((x_clamped, z_val))

        le_pt = (0.0, upper_branch[0][1])

        # Lower points: global aligned grid clamped at x_h
        lower_pts = []
        for i in range(1, n_lower + 1):
            x_val = global_x_lower[i - 1] if i <= n_lower else global_x_lower[-1]
            x_clamped = min(x_val, x_h)
            z_val = _interp_branch_z(lower_branch, x_clamped)
            lower_pts.append((x_clamped, z_val))

        # 7 points on socket / TE
        socket_pts = []
        if x_h < 0.999 and r_h > 1e-4:
            for i in range(1, n_wall + 1):
                theta = -math.pi * 0.5 + (i / n_wall) * math.pi
                x_c = x_h - r_h * math.cos(theta)
                z_c = z_h + r_h * math.sin(theta)
                socket_pts.append((x_c, z_c))
        else:
            z_te_l = _interp_branch_z(lower_branch, 1.0)
            z_te_u = _interp_branch_z(upper_branch, 1.0)
            for i in range(1, n_wall + 1):
                frac = i / n_wall
                socket_pts.append((1.0, z_te_l + frac * (z_te_u - z_te_l)))

        return (*upper_pts, le_pt, *lower_pts, *socket_pts), (x_h, z_h)
    else:
        # Flap Section (64 pts):
        # 28 upper flap points (1.0 down to x_h)
        flap_upper = []
        for i in range(n_upper):
            x_val = 1.0 - (1.0 - x_h) * (i / (n_upper - 1))
            z_val = _interp_branch_z(upper_branch, x_val)
            flap_upper.append((x_val, z_val))

        # 8 points on convex circular nose (from theta = +pi/2 down to -pi/2)
        flap_nose = []
        r_nose = r_h * 0.97
        for i in range(8):
            theta = math.pi * 0.5 - (i / 7.0) * math.pi
            x_c = x_h - r_nose * math.cos(theta)
            z_c = z_h + r_nose * math.sin(theta)
            flap_nose.append((x_c, z_c))

        # 28 lower flap points (x_h up to 1.0)
        flap_lower = []
        for i in range(1, n_lower + 1):
            x_val = x_h + (1.0 - x_h) * (i / n_lower)
            z_val = _interp_branch_z(lower_branch, x_val)
            flap_lower.append((x_val, z_val))

        return tuple(flap_upper + flap_nose + flap_lower), (x_h, z_h)


def _rotate_section_around_axis(
    section: Section,
    axis_pt: Point3D,
    axis_dir: Point3D,
    angle_deg: float,
) -> Section:
    """Rotate all points of a 3D section around an arbitrary 3D hinge axis by angle_deg."""
    length = math.sqrt(axis_dir[0] ** 2 + axis_dir[1] ** 2 + axis_dir[2] ** 2)
    if length < 1e-6:
        return section
    kx, ky, kz = axis_dir[0] / length, axis_dir[1] / length, axis_dir[2] / length
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    one_minus_cos = 1.0 - cos_a

    ox, oy, oz = axis_pt
    new_points: list[Point3D] = []

    for px, py, pz in section.points:
        vx, vy, vz = px - ox, py - oy, pz - oz
        dot = kx * vx + ky * vy + kz * vz
        cx = ky * vz - kz * vy
        cy = kz * vx - kx * vz
        cz = kx * vy - ky * vx

        rx = vx * cos_a + cx * sin_a + kx * dot * one_minus_cos
        ry = vy * cos_a + cy * sin_a + ky * dot * one_minus_cos
        rz = vz * cos_a + cz * sin_a + kz * dot * one_minus_cos

        new_points.append((rx + ox, ry + oy, rz + oz))

    return Section(tuple(new_points))


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _build_tip_cap_loft(
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
    """Generate a smooth, aerodynamic G1-conformal bullnose or beveled edge cap mesh.

    le_sweep_slope / te_sweep_slope: dX/dY of the wing's leading / trailing
    edge line at the tip.  The cap's chordwise stations are shifted along X
    proportionally so that the LE and TE edges of the cap continue the wing
    planform lines without a kink.
    """
    if tip_type not in ("round", "sharp") or tip_length <= 0.0:
        return None

    chord = _number(tip_profile.get("chord"))
    if chord <= 0:
        return None

    coords = sample_airfoil_points(tip_profile.get("airfoil"))
    upper_b, lower_b = _split_airfoil_upper_lower(coords)
    matrix = section_transform(tip_profile, chord=chord, twist_location=twist_location)

    num_x = 33
    x_stations = [0.5 * (1.0 - math.cos(math.pi * i / (num_x - 1))) for i in range(num_x)]
    max_h = max(
        (_interp_branch_z(upper_b, x) - _interp_branch_z(lower_b, x)) * 0.5 for x in x_stations
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
            z_u = _interp_branch_z(upper_b, x_rel)
            z_l = _interp_branch_z(lower_b, x_rel)
            z_c = (z_u + z_l) * 0.5
            h = (z_u - z_l) * 0.5
            h_ratio = h / max_h

            delta_y = span_dir * tip_length * h_ratio * cos_t
            # Sweep-following offset: interpolate between LE and TE sweep slopes
            # along chord so each edge continues the wing planform line
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


def _build_winglet_loft(
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
    """Generate a parametric curved winglet loft with G1 tangency and independent LE/TE curves.

    Supports:
    - G1 continuity with incoming wing planform (zero kink at junction).
    - Independent cubic Hermite/Bézier Leading Edge and Trailing Edge curves.
    - Smooth quintic transition blend from cant_root to cant_tip.
    - Thickness tapering towards the tip.
    - Normal section rotation and aerodynamic washout progression.
    """
    if winglet_height <= 0.0:
        return None

    tip_chord = _number(tip_profile.get("chord"))
    if tip_chord <= 0.0:
        return None

    # Tip station world position & rotation
    matrix = section_transform(tip_profile, chord=tip_chord, twist_location=twist_location)

    # Airfoil coords (with shaping applied)
    coords = sample_airfoil_points(tip_profile.get("airfoil"))
    coords = apply_airfoil_shaping(
        coords,
        te_thickness=te_thickness,
        thickness_scale=thickness_scale,
        camber_scale=camber_scale,
    )
    upper_b, lower_b = _split_airfoil_upper_lower(coords)

    # Resolve cant parameters
    c_tip = cant_tip_deg if cant_tip_deg is not None else cant_angle_deg
    c_root = cant_root_deg if cant_root_deg is not None else 0.0

    le_s_root, le_s_tip, te_s_root, te_s_tip = _winglet_sweep_angles(
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

    # Curvature parameters
    le_curv_val = le_curvature + scimitar_offset
    te_curv_val = te_curvature + (scimitar_offset * 0.4)

    # Toe parameters
    t_root = toe_root_deg if toe_root_deg is not None else toe_angle_deg
    t_tip = toe_tip_deg if toe_tip_deg is not None else toe_angle_deg

    # Cosine-spaced stations along height u in [0, 1]
    n_pts = max(n_stations, 20)
    u_vals = [0.5 * (1.0 - math.cos(math.pi * i / (n_pts - 1))) for i in range(n_pts)]

    cant_angles_rad = _winglet_cant_angles(u_vals, c_root, c_tip, blend_radius, winglet_height)

    # Integrate delta Y and delta Z along height
    y_offsets: list[float] = [0.0]
    z_offsets: list[float] = [0.0]

    for i in range(1, n_pts):
        du = u_vals[i] - u_vals[i - 1]
        ds = winglet_height * du
        avg_cos = 0.5 * (math.cos(cant_angles_rad[i - 1]) + math.cos(cant_angles_rad[i]))
        avg_sin = 0.5 * (math.sin(cant_angles_rad[i - 1]) + math.sin(cant_angles_rad[i]))
        y_offsets.append(y_offsets[-1] + ds * avg_cos * span_dir)
        z_offsets.append(z_offsets[-1] + ds * avg_sin)

    # Hermite boundary values for LE and TE curves
    m0_le = winglet_height * math.tan(math.radians(le_s_root))
    m1_le = winglet_height * math.tan(math.radians(le_s_tip))
    x_le_tip = 0.5 * (m0_le + m1_le)

    c0 = tip_chord * root_chord_scale
    c1 = tip_chord * tip_chord_scale
    k0_te = winglet_height * math.tan(math.radians(te_s_root))
    k1_te = winglet_height * math.tan(math.radians(te_s_tip))
    x_te_tip = x_le_tip + c1

    # Structured airfoil sample count
    n_upper, n_lower, n_wall = 28, 28, 7
    global_x_upper = [0.5 * (1.0 + math.cos(math.pi * i / (n_upper - 1))) for i in range(n_upper)]
    global_x_lower = [0.5 * (1.0 - math.cos(math.pi * i / (n_lower - 1))) for i in range(n_lower)]

    sections: list[Section] = []

    for idx, u in enumerate(u_vals):
        # Cubic Hermite basis functions
        h00 = 2.0 * u**3 - 3.0 * u**2 + 1.0
        h10 = u**3 - 2.0 * u**2 + u
        h01 = -2.0 * u**3 + 3.0 * u**2
        h11 = u**3 - u**2
        # C2 bow bell curve with zero derivatives at endpoints
        bow = 16.0 * (u**2) * ((1.0 - u) ** 2)

        # Leading edge X position
        x_le_u = x_le_tip * h01 + m0_le * h10 + m1_le * h11 + le_curv_val * bow
        # Trailing edge X position
        x_te_u = c0 * h00 + x_te_tip * h01 + k0_te * h10 + k1_te * h11 + te_curv_val * bow

        chord_wl = max(x_te_u - x_le_u, 0.05 * c1)

        ds_y = y_offsets[idx]
        ds_z = z_offsets[idx]

        cant_rad = cant_angles_rad[idx]
        cos_cant = math.cos(cant_rad)
        sin_cant = math.sin(cant_rad)

        # Washout / Toe angle
        toe_deg = t_root + (t_tip - t_root) * u
        toe_rad = math.radians(toe_deg)
        cos_toe = math.cos(toe_rad)
        sin_toe = math.sin(toe_rad)

        # Thickness scale (taper from root to tip)
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
            # Cant roll rotation (perpendicular to cant curve)
            dy_sec = -z_toe * sin_cant * span_dir
            dz_sec = z_toe * cos_cant
            p_local = (x_toe, ds_y + dy_sec, ds_z + dz_sec)
            return transform_point(matrix, p_local)

        pts: list[Point3D] = []

        # Upper surface (TE -> LE)
        for i in range(n_upper):
            x_rel = global_x_upper[i]
            z_val = _interp_branch_z(upper_b, x_rel)
            pts.append(_calc_pt(x_rel, z_val))

        # LE point
        z_le = _interp_branch_z(upper_b, 0.0)
        pts.append(_calc_pt(0.0, z_le))

        # Lower surface (LE -> TE)
        for i in range(n_lower):
            x_rel = global_x_lower[i]
            z_val = _interp_branch_z(lower_b, x_rel)
            pts.append(_calc_pt(x_rel, z_val))

        # TE closure (7 wall pts, upper -> lower)
        z_te_u = _interp_branch_z(upper_b, 1.0)
        z_te_l = _interp_branch_z(lower_b, 1.0)
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


def _winglet_sweep_angles(
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


def _winglet_cant_angles(
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
