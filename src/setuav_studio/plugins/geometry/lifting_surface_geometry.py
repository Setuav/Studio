"""Geometry builder for lifting surfaces and deflected 3D control surfaces."""

from __future__ import annotations

import math
from typing import Any

from .data import LoftGeometry, Point3D, Section
from .transforms import section_transform, transform_point
from setuav_studio.plugins.geometry.airfoil import apply_airfoil_shaping, sample_airfoil_points
from setuav_studio.plugins.geometry.palettes import control_surface_color, wing_color

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
    te_thickness = float(shaping.get("te_thickness", 0.0))      # fraction of chord, e.g. 0.004
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
            if (section := _build_profile_section(
                value,
                twist_location=twist_location,
                te_thickness=te_thickness,
                thickness_scale=thickness_scale,
                camber_scale=camber_scale,
                section_align=section_align,
            )) is not None
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
        y0 = float(profiles[0].get("position", {}).get("y", 0.0)) if isinstance(profiles[0].get("position"), dict) else 0.0
        y1 = float(profiles[-1].get("position", {}).get("y", 0.0)) if isinstance(profiles[-1].get("position"), dict) else 0.0
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
            dx_te = (float(tip_pos.get("x", 0.0)) + _number(p_tip.get("chord"))) - \
                    (float(prev_pos.get("x", 0.0)) + _number(p_prev.get("chord")))
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
        y0 = float(profiles[0].get("position", {}).get("y", 0.0)) if isinstance(profiles[0].get("position"), dict) else 0.0
        y1 = float(profiles[-1].get("position", {}).get("y", 0.0)) if isinstance(profiles[-1].get("position"), dict) else 0.0
        span_dir = 1.0 if y1 >= y0 else -1.0

        p_prev = profiles[-2] if len(profiles) >= 2 else profiles[-1]
        p_tip = profiles[-1]
        prev_pos = p_prev.get("position", {}) if isinstance(p_prev.get("position"), dict) else {}
        tip_pos = p_tip.get("position", {}) if isinstance(p_tip.get("position"), dict) else {}
        dy = float(tip_pos.get("y", 0.0)) - float(prev_pos.get("y", 0.0))
        if abs(dy) > 1e-4:
            dx_le = float(tip_pos.get("x", 0.0)) - float(prev_pos.get("x", 0.0))
            dx_te = (float(tip_pos.get("x", 0.0)) + _number(p_tip.get("chord"))) - \
                    (float(prev_pos.get("x", 0.0)) + _number(p_prev.get("chord")))
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
        blend_radius = float(tip_treatment.get("blend_radius", 45.0 if "blend_radius" in tip_treatment else 0.0))

        # Sweep & Curvatures
        sweep_default = float(tip_treatment.get("winglet_sweep", 20.0))
        le_sweep_root = tip_treatment.get("le_sweep_root", tip_treatment.get("sweep_root"))
        le_sweep_tip = tip_treatment.get("le_sweep_tip", tip_treatment.get("sweep_tip", 48.0))
        le_curvature = float(tip_treatment.get("le_curvature", tip_treatment.get("scimitar_offset", 0.0)))

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
    return apply_airfoil_shaping(coords, te_thickness=te_thickness, thickness_scale=thickness_scale, camber_scale=camber_scale)


def _section_with_align(
    matrix: object,
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
        from .transforms import transform_point as _tp
        return Section(tuple(_tp(matrix, p) for p in corrected), is_station=is_station)
    return Section(
        tuple(
            transform_point(matrix, (x * chord, 0.0, z * chord))
            for x, z in main_2d
        ),
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
    rot = profile.get("rotation") if isinstance(profile.get("rotation"), dict) else {}
    dihedral_rad = math.radians(_number(rot.get("x", rot.get("roll", 0.0))))
    matrix = section_transform(profile, chord=chord, twist_location=twist_location)
    main_2d, _ = _sample_structured_airfoil_round(coords, x_h=1.0, is_flap=False)
    return _section_with_align(matrix, chord, main_2d, dihedral_rad, section_align)


def _build_lifting_surface_with_control_surfaces(
    comp_id: str,
    profiles: list[dict[str, Any]],
    control_surfaces: list[dict[str, Any]],
    interpolation: str,
    twist_location: float = 0.25,
    te_thickness: float = 0.0,
    thickness_scale: float = 1.0,
    camber_scale: float = 1.0,
    section_align: str = "xz",
) -> tuple[LoftGeometry, ...]:
    """Segment the wing cleanly along span so that each segment is straight/smooth without spline oscillations."""
    # 1. Collect all span Y coordinates
    span_values: list[float] = []
    for p in profiles:
        pos = p.get("position") if isinstance(p.get("position"), dict) else {}
        span_values.append(float(pos.get("y", 0.0)))

    min_span = min(span_values)
    max_span = max(span_values)
    y_root = span_values[0]
    y_tip = span_values[-1]
    semi_span = max(abs(y_tip - y_root), 1.0)
    span_dir = 1.0 if y_tip >= y_root else -1.0

    # 2. Collect valid control surfaces and clip their spans
    valid_cs: list[dict[str, Any]] = []
    for idx, cs in enumerate(control_surfaces):
        if not isinstance(cs, dict):
            continue
        span_mode = str(cs.get("span_mode", "ratio")).lower()
        if span_mode == "dimension" and ("span_start" in cs or "span_end" in cs):
            s_start = float(cs.get("span_start", 0.0))
            s_end = float(cs.get("span_end", 0.0))
        elif span_mode == "ratio" and ("eta_start" in cs or "eta_end" in cs):
            s_start = float(cs.get("eta_start", 0.0)) * semi_span
            s_end = float(cs.get("eta_end", 0.0)) * semi_span
        elif "span_start" in cs or "span_end" in cs:
            s_start = float(cs.get("span_start", 0.0))
            s_end = float(cs.get("span_end", 0.0))
        elif "eta_start" in cs or "eta_end" in cs:
            s_start = float(cs.get("eta_start", 0.0)) * semi_span
            s_end = float(cs.get("eta_end", 0.0)) * semi_span
        else:
            s_start = 0.0
            s_end = 0.0

        if s_end <= s_start:
            continue
        y_start = y_root + span_dir * min(s_start, s_end)
        y_end = y_root + span_dir * max(s_start, s_end)
        y_min_seg = min(y_start, y_end)
        y_max_seg = max(y_start, y_end)

        # Clip to wing span
        y_min_seg = max(min_span, y_min_seg)
        y_max_seg = min(max_span, y_max_seg)
        if y_max_seg <= y_min_seg + 1e-3:
            continue

        chord_mode = str(cs.get("chord_mode", "ratio")).lower()
        if chord_mode == "dimension":
            chord_frac = None
        else:
            chord_frac = cs.get("chord_fraction")
            if chord_frac is not None:
                try:
                    chord_frac = float(chord_frac)
                except (ValueError, TypeError):
                    chord_frac = None

        valid_cs.append({
            "tag": str(cs.get("tag") or f"CS_{idx + 1}"),
            "type": str(cs.get("type") or "aileron"),
            "y_min": y_min_seg,
            "y_max": y_max_seg,
            "s_start": min(s_start, s_end),
            "s_end": max(s_start, s_end),
            "eta_start": round(min(s_start, s_end) / semi_span, 4),
            "eta_end": round(max(s_start, s_end) / semi_span, 4),
            "chord_fraction": chord_frac,
            "chord": max(float(cs.get("chord", 40.0)), 1.0),
            "hinge_sweep": float(cs.get("hinge_sweep")) if cs.get("hinge_sweep") is not None else None,
            "deflection": float(cs.get("deflection", 0.0)),
        })

    if not valid_cs:
        sections = tuple(
            section
            for value in profiles
            if (section := _build_profile_section(
                value,
                te_thickness=te_thickness,
                thickness_scale=thickness_scale,
                camber_scale=camber_scale,
                section_align=section_align,
            )) is not None
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

    # 3. Create macro span partition boundaries
    all_cuts = {min_span, max_span}
    for cs in valid_cs:
        all_cuts.add(cs["y_min"])
        all_cuts.add(cs["y_max"])
    sorted_cuts = sorted(all_cuts)

    lofts: list[LoftGeometry] = []

    # 4. Generate lofts for each span interval [y_a, y_b]
    for i in range(len(sorted_cuts) - 1):
        y_a, y_b = sorted_cuts[i], sorted_cuts[i + 1]
        if abs(y_b - y_a) < 1e-4:
            continue
        y_mid = (y_a + y_b) * 0.5

        # Check if covered by a control surface
        covering_cs = next((cs for cs in valid_cs if cs["y_min"] <= y_mid <= cs["y_max"]), None)

        # Collect all stations in [y_a, y_b] (start, intermediate original profiles, end)
        interval_stations = [y_a]
        for y_p in sorted(span_values):
            if y_a + 1e-3 < y_p < y_b - 1e-3:
                interval_stations.append(y_p)
        interval_stations.append(y_b)

        if span_dir < 0:
            interval_stations = sorted(interval_stations, reverse=True)

        if covering_cs is None:
            # Uncut Full Wing Segment (x_h = 1.0)
            seg_sections: list[Section] = []
            for y_s in interval_stations:
                chord, prof, coords = _interpolate_station_props(y_s, profiles)
                coords = _apply_shaping(coords, te_thickness, thickness_scale, camber_scale)
                rot = prof.get("rotation") if isinstance(prof.get("rotation"), dict) else {}
                dihedral_rad = math.radians(_number(rot.get("x", rot.get("roll", 0.0))))
                matrix = section_transform(prof, chord=chord, twist_location=twist_location)
                main_2d, _ = _sample_structured_airfoil_round(coords, x_h=1.0, is_flap=False)
                is_orig_station = any(abs(y_s - y_p) < 1e-3 for y_p in span_values)
                seg_sections.append(_section_with_align(matrix, chord, main_2d, dihedral_rad, section_align, is_station=is_orig_station))

            lofts.append(
                LoftGeometry(
                    component_id=comp_id,
                    sections=tuple(seg_sections),
                    color=wing_color(),
                    interpolation=interpolation,
                    station_spacing=15.0,
                    closed_ends=True,
                )
            )
        else:
            # Control Surface Bay: Main Wing (with concave round hinge socket) + Flap (with convex round nose)
            cs_chord = covering_cs["chord"]
            deflection_deg = covering_cs["deflection"]
            cs_tag = covering_cs["tag"]
            hinge_sweep = covering_cs["hinge_sweep"]
            s_0 = covering_cs["s_start"]

            # Interpolate reference station properties at s_0
            y_s0 = y_root + span_dir * s_0
            chord_0, prof_0, _ = _interpolate_station_props(y_s0, profiles)
            x_le_0 = float(prof_0.get("position", {}).get("x", 0.0)) if isinstance(prof_0.get("position"), dict) else 0.0
            X_h0 = (x_le_0 + chord_0) - cs_chord

            main_sections: list[Section] = []
            flap_sections: list[Section] = []
            hinge_pts_3d: list[Point3D] = []

            for y_s in interval_stations:
                chord, prof, coords = _interpolate_station_props(y_s, profiles)
                coords = _apply_shaping(coords, te_thickness, thickness_scale, camber_scale)
                rot = prof.get("rotation") if isinstance(prof.get("rotation"), dict) else {}
                dihedral_rad = math.radians(_number(rot.get("x", rot.get("roll", 0.0))))
                matrix = section_transform(prof, chord=chord, twist_location=twist_location)
                pos = prof.get("position") if isinstance(prof.get("position"), dict) else {}
                x_le_s = float(pos.get("x", 0.0))

                s_curr = abs(y_s - y_root)
                chord_frac = covering_cs.get("chord_fraction")
                if hinge_sweep is not None:
                    # Global swept hinge line
                    X_h_curr = X_h0 + (s_curr - s_0) * math.tan(math.radians(hinge_sweep))
                    x_rel = (X_h_curr - x_le_s) / max(chord, 1.0)
                    x_h = min(max(x_rel, 0.05), 0.95)
                elif chord_frac is not None and chord_frac > 0.0:
                    # Constant chord fraction from trailing edge (e.g. 0.25 -> x_h = 0.75)
                    x_h = 1.0 - min(max(chord_frac, 0.05), 0.95)
                else:
                    # Constant absolute chord depth from trailing edge
                    x_h = 1.0 - min(max(cs_chord / max(chord, 1.0), 0.05), 0.95)

                main_2d, h_pt = _sample_structured_airfoil_round(coords, x_h=x_h, is_flap=False)
                flap_2d, _ = _sample_structured_airfoil_round(coords, x_h=x_h, is_flap=True)

                is_orig_station = any(abs(y_s - y_p) < 1e-3 for y_p in span_values)
                main_sections.append(_section_with_align(matrix, chord, main_2d, dihedral_rad, section_align, is_station=is_orig_station))
                flap_sections.append(_section_with_align(matrix, chord, flap_2d, dihedral_rad, section_align, is_station=False))
                hinge_pts_3d.append(transform_point(matrix, (h_pt[0] * chord, 0.0, h_pt[1] * chord)))

            # Main wing bay
            lofts.append(
                LoftGeometry(
                    component_id=comp_id,
                    sections=tuple(main_sections),
                    color=wing_color(),
                    interpolation=interpolation,
                    station_spacing=15.0,
                    closed_ends=True,
                )
            )

            # Deflect flap if deflection != 0
            if abs(deflection_deg) > 1e-4 and len(hinge_pts_3d) >= 2:
                axis_p0 = hinge_pts_3d[0]
                axis_p1 = hinge_pts_3d[-1]
                axis_dir = (
                    axis_p1[0] - axis_p0[0],
                    axis_p1[1] - axis_p0[1],
                    axis_p1[2] - axis_p0[2],
                )
                rotated_sections: list[Section] = []
                for sec in flap_sections:
                    rotated_sections.append(_rotate_section_around_axis(sec, axis_p0, axis_dir, deflection_deg))
                flap_sections = rotated_sections

            lofts.append(
                LoftGeometry(
                    component_id=f"{comp_id}:{cs_tag}",
                    sections=tuple(flap_sections),
                    color=control_surface_color(),
                    interpolation=interpolation,
                    station_spacing=15.0,
                    closed_ends=True,
                )
            )

    return tuple(lofts)


def _interpolate_station_props(
    y: float,
    profiles: list[dict[str, Any]],
) -> tuple[float, dict[str, Any], tuple[tuple[float, float], ...]]:
    """Interpolate chord, section dict (for transform), and airfoil coords at span y."""
    sorted_profs = sorted(
        profiles,
        key=lambda p: float(p.get("position", {}).get("y", 0.0))
        if isinstance(p.get("position"), dict) else 0.0,
    )
    y_coords = [
        float(p.get("position", {}).get("y", 0.0))
        if isinstance(p.get("position"), dict) else 0.0
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
        "x": float(pos0.get("x", 0.0)) + (float(pos1.get("x", 0.0)) - float(pos0.get("x", 0.0))) * t,
        "y": y,
        "z": float(pos0.get("z", 0.0)) + (float(pos1.get("z", 0.0)) - float(pos0.get("z", 0.0))) * t,
    }
    rot_interp = {
        "x": float(rot0.get("x", 0.0)) + (float(rot1.get("x", 0.0)) - float(rot0.get("x", 0.0))) * t,
        "y": float(rot0.get("y", 0.0)) + (float(rot1.get("y", 0.0)) - float(rot0.get("y", 0.0))) * t,
        "z": float(rot0.get("z", 0.0)) + (float(rot1.get("z", 0.0)) - float(rot0.get("z", 0.0))) * t,
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

    path1 = ordered[:te_idx + 1]
    path2 = [ordered[0]] + list(reversed(ordered[te_idx:]))

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

        return tuple(upper_pts + [le_pt] + lower_pts + socket_pts), (x_h, z_h)
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
    length = math.sqrt(axis_dir[0]**2 + axis_dir[1]**2 + axis_dir[2]**2)
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


def _number(value: object) -> float:
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
    max_h = max((_interp_branch_z(upper_b, x) - _interp_branch_z(lower_b, x)) * 0.5 for x in x_stations)
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

    u_vals = [
        0.5 * (1.0 - math.cos(math.pi * i / (n_pts - 1)))
        for i in range(n_pts)
    ]
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

    # Resolve LE sweep
    if le_sweep_tip_deg is not None:
        le_s_tip = le_sweep_tip_deg
    elif sweep_tip_deg is not None:
        le_s_tip = sweep_tip_deg
    else:
        le_s_tip = sweep_deg

    if le_sweep_root_deg is not None:
        le_s_root = le_sweep_root_deg
    elif match_wing_tangent:
        le_s_root = incoming_le_sweep_deg
    elif sweep_root_deg is not None:
        le_s_root = sweep_root_deg
    else:
        le_s_root = sweep_deg

    # Resolve TE sweep
    if te_sweep_root_deg is not None:
        te_s_root = te_sweep_root_deg
    elif match_wing_tangent:
        te_s_root = incoming_te_sweep_deg
    else:
        te_s_root = le_s_root * 0.7

    if te_sweep_tip_deg is not None:
        te_s_tip = te_sweep_tip_deg
    else:
        te_s_tip = le_s_tip * 0.5

    # Curvature parameters
    le_curv_val = le_curvature + scimitar_offset
    te_curv_val = te_curvature + (scimitar_offset * 0.4)

    # Toe parameters
    t_root = toe_root_deg if toe_root_deg is not None else toe_angle_deg
    t_tip = toe_tip_deg if toe_tip_deg is not None else toe_angle_deg

    # Cosine-spaced stations along height u in [0, 1]
    n_pts = max(n_stations, 20)
    u_vals = [
        0.5 * (1.0 - math.cos(math.pi * i / (n_pts - 1)))
        for i in range(n_pts)
    ]

    # Pre-calculate cant angle Gamma(u) at each station
    u_blend = min(1.0, max(0.01, blend_radius / winglet_height)) if blend_radius > 0.0 else 0.0

    cant_angles_rad: list[float] = []
    for u in u_vals:
        if blend_radius > 0.0:
            if u <= u_blend:
                t = u / u_blend
                w = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)  # quintic smoothstep
                angle = c_root + (c_tip - c_root) * w
            else:
                angle = c_tip
        else:
            angle = c_root + (c_tip - c_root) * u
        cant_angles_rad.append(math.radians(angle))

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
        bow = 16.0 * (u**2) * ((1.0 - u)**2)

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

        def _calc_pt(x_rel: float, z_rel: float) -> Point3D:
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
