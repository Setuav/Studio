"""Geometry-derived physical envelope computation for CAD components.

Implements station-by-station trapezoidal (frustum / yamuk) slice integration
for fuselages and lifting surfaces, deriving exact volumetric centroids,
slice breakdowns, 3D inertia tensors, total volume, and cross-section bboxes.
"""

from __future__ import annotations

import math
from typing import Any

_LIFTING_SURFACE_TYPE = "org.setuav.core:lifting-surface"
_FUSELAGE_TYPE = "org.setuav.core:fuselage"
_CONTROL_SURFACE_TYPE = "org.setuav.core:control-surface"

GEOMETRY_COMPONENT_TYPES = frozenset(
    {
        _LIFTING_SURFACE_TYPE,
        _FUSELAGE_TYPE,
        _CONTROL_SURFACE_TYPE,
    }
)


def compute_geometry_envelope(
    component: dict[str, Any],
    parent: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compute local 3D physical envelope (with trapezoidal slices) from CAD geometry."""
    ctype = str(component.get("type") or "")
    if ctype == _LIFTING_SURFACE_TYPE:
        return _compute_lifting_surface_envelope(component)
    if ctype == _FUSELAGE_TYPE:
        return _compute_fuselage_envelope(component)
    if ctype == _CONTROL_SURFACE_TYPE:
        return _compute_control_surface_envelope(component, parent)
    return None


def sync_component_envelope(
    component: dict[str, Any],
    parent: dict[str, Any] | None = None,
) -> bool:
    """Compute and update the envelope on the component if applicable.

    Returns True if the component envelope was changed.
    """
    env = compute_geometry_envelope(component, parent)
    if env is None:
        return False
    if component.get("envelope") == env:
        return False
    component["envelope"] = env
    return True


def sync_project_geometry_envelopes(project: Any) -> int:
    """Ensure all geometry components in the project document have up-to-date envelopes.

    Returns the count of components whose envelope was updated.
    """
    if project is None:
        return 0
    data = getattr(project, "data", project) if not isinstance(project, dict) else project
    if not isinstance(data, dict):
        return 0
    components = data.get("components")
    if not isinstance(components, list):
        return 0

    all_components = list(components)
    for cfg in data.get("configurations", []):
        if isinstance(cfg, dict):
            for added in cfg.get("added_components", []):
                if isinstance(added, dict):
                    all_components.append(added)

    by_id: dict[str, dict[str, Any]] = {
        str(c.get("id")): c
        for c in all_components
        if isinstance(c, dict) and c.get("id")
    }

    updated = 0
    for comp in all_components:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "")
        if ctype not in GEOMETRY_COMPONENT_TYPES:
            continue
        parent_id = comp.get("attach_to") or comp.get("parent")
        parent = by_id.get(str(parent_id)) if parent_id else None
        if sync_component_envelope(comp, parent):
            updated += 1

    return updated


# =============================================================================
# Mathematical Helpers
# =============================================================================


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _polygon_area_and_centroid(
    vertices: list[tuple[float, float]] | tuple[tuple[float, float], ...],
) -> tuple[float, float, float]:
    """Compute (area, cx, cz) of a 2D closed polygon using the Shoelace formula."""
    n = len(vertices)
    if n < 3:
        return 0.0, 0.0, 0.0
    area_acc = 0.0
    cx_acc = 0.0
    cz_acc = 0.0
    for i in range(n):
        x1, z1 = vertices[i]
        x2, z2 = vertices[(i + 1) % n]
        cross = x1 * z2 - x2 * z1
        area_acc += cross
        cx_acc += (x1 + x2) * cross
        cz_acc += (z1 + z2) * cross
    signed_area = area_acc * 0.5
    area = abs(signed_area)
    if area < 1e-9 or abs(signed_area) < 1e-9:
        return 0.0, 0.0, 0.0
    cx = cx_acc / (6.0 * signed_area)
    cz = cz_acc / (6.0 * signed_area)
    return area, cx, cz


def _compute_section_properties(profile: dict[str, Any]) -> tuple[float, float, float, float, float]:
    """Compute (area, width, height, cy_rel, cz_rel) for a fuselage profile."""
    profile_type = str(profile.get("type") or "").lower()

    if profile_type == "circle":
        d = _number(profile.get("diameter"))
        r = d * 0.5
        return math.pi * r * r, d, d, 0.0, 0.0
    if profile_type == "ellipse":
        w = _number(profile.get("width"))
        h = _number(profile.get("height"))
        return math.pi * 0.25 * w * h, w, h, 0.0, 0.0
    if profile_type == "rectangle":
        w = _number(profile.get("width"))
        h = _number(profile.get("height"))
        cr = _number(profile.get("corner_radius"))
        area = w * h - (4.0 - math.pi) * (cr**2)
        return max(area, 0.0), w, h, 0.0, 0.0
    if profile_type == "trapezoid":
        top = _number(profile.get("top_width"))
        bot = _number(profile.get("bottom_width"))
        h = _number(profile.get("height"))
        area = 0.5 * (top + bot) * h
        w = max(top, bot)
        cz = (h / 6.0) * (top - bot) / ((top + bot) * 0.5) if (top + bot) > 0.0 else 0.0
        return max(area, 0.0), w, h, 0.0, cz
    if profile_type == "triangle":
        bw = _number(profile.get("base_width"))
        h = _number(profile.get("height"))
        area = 0.5 * bw * h
        cz = -h / 6.0 if profile.get("orientation") == "down" else h / 6.0
        return max(area, 0.0), bw, h, 0.0, cz

    # Fallback to polygon / sample_profile
    try:
        from .fuselage_geometry import sample_profile

        pts = sample_profile(profile)
        if len(pts) >= 3:
            area, cy, cz = _polygon_area_and_centroid(pts)
            w = max(p[0] for p in pts) - min(p[0] for p in pts)
            h = max(p[1] for p in pts) - min(p[1] for p in pts)
            return area, w, h, cy, cz
    except Exception:
        pass

    w = _number(profile.get("width", profile.get("diameter", 10.0)))
    h = _number(profile.get("height", profile.get("diameter", 10.0)))
    return w * h, w, h, 0.0, 0.0


def _compute_fuselage_section_bbox(
    section: dict[str, Any],
    index: int = 0,
    segment_tag: str = "main",
) -> dict[str, Any]:
    """Compute the 2D/3D bounding quadrilateral cross-section for a fuselage section."""
    prof = section.get("profile") if isinstance(section.get("profile"), dict) else {}
    ptype = str(prof.get("type") or "").lower()

    if ptype == "circle":
        d = _number(prof.get("diameter"), 10.0)
        w, h = d, d
        top_w, bot_w = d, d
        shape = "rectangle"
        area = d * d
    elif ptype == "ellipse":
        w = _number(prof.get("width"), 10.0)
        h = _number(prof.get("height"), 10.0)
        top_w, bot_w = w, w
        shape = "rectangle"
        area = w * h
    elif ptype == "trapezoid":
        top_w = _number(prof.get("top_width"), 10.0)
        bot_w = _number(prof.get("bottom_width"), 10.0)
        h = _number(prof.get("height"), 10.0)
        w = max(top_w, bot_w)
        shape = "trapezoid"
        area = 0.5 * (top_w + bot_w) * h
    elif ptype == "triangle":
        bw = _number(prof.get("base_width"), 10.0)
        h = _number(prof.get("height"), 10.0)
        shape = "triangle"
        top_w = 0.0 if prof.get("orientation") != "down" else bw
        bot_w = bw if prof.get("orientation") != "down" else 0.0
        w = bw
        area = 0.5 * bw * h
    else:
        w = _number(prof.get("width", prof.get("diameter", 10.0)))
        h = _number(prof.get("height", prof.get("diameter", 10.0)))
        top_w, bot_w = w, w
        shape = "rectangle"
        area = w * h

    local_corners = (
        (0.0, -top_w * 0.5, h * 0.5),  # top-left
        (0.0, top_w * 0.5, h * 0.5),   # top-right
        (0.0, bot_w * 0.5, -h * 0.5),  # bottom-right
        (0.0, -bot_w * 0.5, -h * 0.5), # bottom-left
    )
    from .transforms import section_transform, transform_point

    matrix = section_transform(section)
    world_corners = [transform_point(matrix, p) for p in local_corners]
    world_center = transform_point(matrix, (0.0, 0.0, 0.0))

    ys = [p[1] for p in world_corners]
    zs = [p[2] for p in world_corners]

    return {
        "index": index,
        "segment": segment_tag,
        "station_x_mm": round(world_center[0], 2),
        "position": {
            "x": round(world_center[0], 2),
            "y": round(world_center[1], 2),
            "z": round(world_center[2], 2),
        },
        "width_mm": round(max(ys) - min(ys), 2),
        "height_mm": round(max(zs) - min(zs), 2),
        "shape": shape,
        "top_width_mm": round(top_w, 2),
        "bottom_width_mm": round(bot_w, 2),
        "y_bounds_mm": [round(min(ys), 2), round(max(ys), 2)],
        "z_bounds_mm": [round(min(zs), 2), round(max(zs), 2)],
        "area_mm2": round(area, 2),
        "corners_3d": [
            {"x": round(p[0], 2), "y": round(p[1], 2), "z": round(p[2], 2)}
            for p in world_corners
        ],
    }


def _compute_airfoil_properties(airfoil: Any) -> tuple[float, float, float]:
    """Compute normalized (area, cx, cz) for an airfoil in [0, 1] coordinates."""
    pts: tuple[tuple[float, float], ...] | list[tuple[float, float]] = ()
    if isinstance(airfoil, dict):
        raw_pts = airfoil.get("points")
        if isinstance(raw_pts, list) and len(raw_pts) >= 3:
            pts = [(float(p[0]), float(p[1])) for p in raw_pts if len(p) >= 2]
        elif isinstance(airfoil.get("name"), str):
            try:
                from .airfoil import sample_airfoil_points

                pts = sample_airfoil_points(str(airfoil["name"]))
            except Exception:
                pts = ()
    elif isinstance(airfoil, str) and airfoil.strip():
        try:
            from .airfoil import sample_airfoil_points

            pts = sample_airfoil_points(airfoil.strip())
        except Exception:
            pts = ()

    if len(pts) >= 3:
        area, cx, cz = _polygon_area_and_centroid(pts)
        if area > 1e-6:
            return area, cx, cz

    # Standard 12% symmetric profile baseline (NACA 0012)
    return 0.082, 0.40, 0.0


# =============================================================================
# Fuselage Slice & Section Integration
# =============================================================================


def _compute_fuselage_trapezoidal_slices(
    segments: list[Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    float,
    tuple[float, float, float],
    dict[str, float],
]:
    """Integrate station-by-station frustum slices and section bboxes for a fuselage.

    Returns:
        (sections_list, slices_list, total_volume_mm3, (cg_x, cg_y, cg_z), unit_inertia_m2)
    """
    sections: list[dict[str, Any]] = []
    slices: list[dict[str, Any]] = []
    total_vol = 0.0
    weighted_x = 0.0
    weighted_y = 0.0
    weighted_z = 0.0

    slice_data: list[
        tuple[float, tuple[float, float, float], tuple[float, float, float]]
    ] = []  # (V_i, cg_i, (Ixx_i, Iyy_i, Izz_i))

    slice_idx = 0
    sec_global_idx = 0
    for seg_idx, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        seg_tag = str(segment.get("tag") or f"seg_{seg_idx}")
        raw_sections = segment.get("sections")
        if not isinstance(raw_sections, list) or len(raw_sections) < 2:
            continue

        valid_sections: list[dict[str, Any]] = [
            s for s in raw_sections if isinstance(s, dict)
        ]
        # Sort along X
        valid_sections.sort(
            key=lambda s: _number((s.get("position") or {}).get("x"))
        )

        # Compute BBox cross-sections for all sections in this segment
        seg_section_bboxes = [
            _compute_fuselage_section_bbox(s, sec_global_idx + s_i, seg_tag)
            for s_i, s in enumerate(valid_sections)
        ]
        sections.extend(seg_section_bboxes)
        sec_global_idx += len(valid_sections)

        for i in range(len(valid_sections) - 1):
            s1 = valid_sections[i]
            s2 = valid_sections[i + 1]
            bbox1 = seg_section_bboxes[i]
            bbox2 = seg_section_bboxes[i + 1]

            pos1 = s1.get("position") if isinstance(s1.get("position"), dict) else {}
            pos2 = s2.get("position") if isinstance(s2.get("position"), dict) else {}
            prof1 = s1.get("profile") if isinstance(s1.get("profile"), dict) else {}

            x1 = _number(pos1.get("x"))
            y1 = _number(pos1.get("y"))
            z1 = _number(pos1.get("z"))
            x2 = _number(pos2.get("x"))
            y2 = _number(pos2.get("y"))
            z2 = _number(pos2.get("z"))

            # Section properties
            a1, w1, h1, cy1, cz1 = _compute_section_properties(prof1)
            prof2 = s2.get("profile") if isinstance(s2.get("profile"), dict) else {}
            a2, w2, h2, cy2, cz2 = _compute_section_properties(prof2)

            dx = x2 - x1
            length = dx if dx > 0.0 else math.sqrt(dx**2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)
            if length < 1e-4:
                continue

            # Frustum volume formula: V = (L / 3) * (A1 + A2 + sqrt(A1 * A2))
            geom_mean = math.sqrt(max(a1 * a2, 0.0))
            vol = (length / 3.0) * (a1 + a2 + geom_mean)
            if vol <= 0.0:
                continue

            denom = 4.0 * (a1 + a2 + geom_mean)
            t = (a1 + 2.0 * geom_mean + 3.0 * a2) / denom if denom > 1e-9 else 0.5

            c1 = (x1, y1 + cy1, z1 + cz1)
            c2 = (x2, y2 + cy2, z2 + cz2)
            cg_slice = (
                c1[0] + t * (c2[0] - c1[0]),
                c1[1] + t * (c2[1] - c1[1]),
                c1[2] + t * (c2[2] - c1[2]),
            )

            # Longitudinal moment distribution along the slice
            factor = (
                (a1 + 3.0 * geom_mean + 6.0 * a2) / (10.0 * (a1 + a2 + geom_mean)) - t**2
                if denom > 1e-9
                else 1.0 / 12.0
            )
            jl = vol * (length**2) * max(factor, 0.0)

            # Transverse cross-section distribution
            w_avg = (w1 + w2) * 0.5
            h_avg = (h1 + h2) * 0.5
            p_type = str(prof1.get("type") or "").lower()
            div = 16.0 if p_type in ("circle", "ellipse") else 12.0
            jy = vol * (h_avg**2) / div
            jz = vol * (w_avg**2) / div

            ixx_slice = jy + jz
            iyy_slice = jl + jy
            izz_slice = jl + jz

            total_vol += vol
            weighted_x += vol * cg_slice[0]
            weighted_y += vol * cg_slice[1]
            weighted_z += vol * cg_slice[2]

            slice_data.append((vol, cg_slice, (ixx_slice, iyy_slice, izz_slice)))
            slices.append(
                {
                    "index": slice_idx,
                    "segment": seg_tag,
                    "start_section_index": bbox1["index"],
                    "end_section_index": bbox2["index"],
                    "station_start_mm": round(x1, 2),
                    "station_end_mm": round(x2, 2),
                    "length_mm": round(length, 2),
                    "start_dimensions_mm": {"width": round(w1, 2), "height": round(h1, 2)},
                    "end_dimensions_mm": {"width": round(w2, 2), "height": round(h2, 2)},
                    "volume_mm3": round(vol, 2),
                    "centroid_mm": {
                        "x": round(cg_slice[0], 2),
                        "y": round(cg_slice[1], 2),
                        "z": round(cg_slice[2], 2),
                    },
                }
            )
            slice_idx += 1

    if total_vol <= 0.0:
        return (
            sections,
            [],
            0.0,
            (0.0, 0.0, 0.0),
            {"ixx": 0.0, "iyy": 0.0, "izz": 0.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0},
        )

    cg_total = (
        weighted_x / total_vol,
        weighted_y / total_vol,
        weighted_z / total_vol,
    )

    # Parallel Axis Theorem (Steiner's theorem) to fuselage total centroid
    ixx_total = 0.0
    iyy_total = 0.0
    izz_total = 0.0
    ixy_total = 0.0
    ixz_total = 0.0
    iyz_total = 0.0

    for vol, (cx, cy, cz), (ixx_s, iyy_s, izz_s) in slice_data:
        dx = cx - cg_total[0]
        dy = cy - cg_total[1]
        dz = cz - cg_total[2]

        ixx_total += ixx_s + vol * (dy**2 + dz**2)
        iyy_total += iyy_s + vol * (dx**2 + dz**2)
        izz_total += izz_s + vol * (dx**2 + dy**2)
        ixy_total -= vol * dx * dy
        ixz_total -= vol * dx * dz
        iyz_total -= vol * dy * dz

    # Convert mm^5 / mm^3 (mm^2) to unit inertia in m^2 (divide by 1e6)
    scale = total_vol * 1e6
    unit_inertia = {
        "ixx": round(ixx_total / scale, 8),
        "iyy": round(iyy_total / scale, 8),
        "izz": round(izz_total / scale, 8),
        "ixy": round(ixy_total / scale, 8),
        "ixz": round(ixz_total / scale, 8),
        "iyz": round(iyz_total / scale, 8),
    }

    return sections, slices, total_vol, cg_total, unit_inertia


# =============================================================================
# Lifting Surface Slice Integration
# =============================================================================


def _compute_lifting_surface_trapezoidal_slices(
    geometry: dict[str, Any],
    profiles: list[Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    float,
    tuple[float, float, float],
    dict[str, float],
]:
    """Integrate station-by-station trapezoidal panel slices for a lifting surface.

    Handles taper, sweep, dihedral, airfoil thickness, and mirror symmetry.
    Returns:
        (sections_list, slices_list, total_volume_mm3, (cg_x, cg_y, cg_z), unit_inertia_m2)
    """
    valid_profiles: list[dict[str, Any]] = [p for p in profiles if isinstance(p, dict)]
    if len(valid_profiles) < 2:
        return (
            [],
            [],
            0.0,
            (0.0, 0.0, 0.0),
            {"ixx": 0.0, "iyy": 0.0, "izz": 0.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0},
        )

    valid_profiles.sort(
        key=lambda p: abs(_number((p.get("position") or {}).get("y")))
    )

    mirror = bool(geometry.get("mirror", geometry.get("symmetric", False)))

    sections: list[dict[str, Any]] = []
    slices: list[dict[str, Any]] = []
    semi_vol = 0.0
    weighted_x = 0.0
    weighted_y = 0.0
    weighted_z = 0.0

    panel_data: list[
        tuple[float, tuple[float, float, float], tuple[float, float, float]]
    ] = []

    # Compute section bboxes for all profiles
    for i, prof in enumerate(valid_profiles):
        pos = prof.get("position") if isinstance(prof.get("position"), dict) else {}
        px = _number(pos.get("x"))
        py = _number(pos.get("y"))
        pz = _number(pos.get("z"))
        chord = max(_number(prof.get("chord")), 1.0)
        thick = round(chord * 0.12, 2)
        a_norm, _, _ = _compute_airfoil_properties(prof.get("airfoil"))
        sections.append(
            {
                "index": i,
                "span_y_mm": round(py, 2),
                "position": {"x": round(px, 2), "y": round(py, 2), "z": round(pz, 2)},
                "chord_mm": round(chord, 2),
                "thickness_mm": thick,
                "x_bounds_mm": [round(px, 2), round(px + chord, 2)],
                "z_bounds_mm": [round(pz - thick * 0.5, 2), round(pz + thick * 0.5, 2)],
                "area_mm2": round(a_norm * (chord**2), 2),
                "shape": "airfoil",
            }
        )

    for i in range(len(valid_profiles) - 1):
        p1 = valid_profiles[i]
        p2 = valid_profiles[i + 1]

        pos1 = p1.get("position") if isinstance(p1.get("position"), dict) else {}
        pos2 = p2.get("position") if isinstance(p2.get("position"), dict) else {}

        x1 = _number(pos1.get("x"))
        y1 = _number(pos1.get("y"))
        z1 = _number(pos1.get("z"))
        x2 = _number(pos2.get("x"))
        y2 = _number(pos2.get("y"))
        z2 = _number(pos2.get("z"))

        c1 = max(_number(p1.get("chord")), 1.0)
        c2 = max(_number(p2.get("chord")), 1.0)

        a_norm1, cx_norm1, cz_norm1 = _compute_airfoil_properties(p1.get("airfoil"))
        a_norm2, cx_norm2, cz_norm2 = _compute_airfoil_properties(p2.get("airfoil"))

        a1 = a_norm1 * (c1**2)
        a2 = a_norm2 * (c2**2)

        span_len = abs(y2 - y1)
        if span_len < 1e-4:
            span_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)
        if span_len < 1e-4:
            continue

        geom_mean = math.sqrt(max(a1 * a2, 0.0))
        vol = (span_len / 3.0) * (a1 + a2 + geom_mean)
        if vol <= 0.0:
            continue

        denom = 4.0 * (a1 + a2 + geom_mean)
        t = (a1 + 2.0 * geom_mean + 3.0 * a2) / denom if denom > 1e-9 else 0.5

        sec1_cg = (x1 + c1 * cx_norm1, y1, z1 + c1 * cz_norm1)
        sec2_cg = (x2 + c2 * cx_norm2, y2, z2 + c2 * cz_norm2)

        cg_panel = (
            sec1_cg[0] + t * (sec2_cg[0] - sec1_cg[0]),
            sec1_cg[1] + t * (sec2_cg[1] - sec1_cg[1]),
            sec1_cg[2] + t * (sec2_cg[2] - sec1_cg[2]),
        )

        factor = (
            (a1 + 3.0 * geom_mean + 6.0 * a2) / (10.0 * (a1 + a2 + geom_mean)) - t**2
            if denom > 1e-9
            else 1.0 / 12.0
        )
        j_span = vol * (span_len**2) * max(factor, 0.0)

        c_avg = (c1 + c2) * 0.5
        t_avg = c_avg * 0.12
        j_chord = vol * (c_avg**2) / 16.0
        j_thick = vol * (t_avg**2) / 12.0

        ixx_panel = j_span + j_thick
        iyy_panel = j_chord + j_thick
        izz_panel = j_span + j_chord

        semi_vol += vol
        weighted_x += vol * cg_panel[0]
        weighted_y += vol * cg_panel[1]
        weighted_z += vol * cg_panel[2]

        panel_data.append((vol, cg_panel, (ixx_panel, iyy_panel, izz_panel)))
        slices.append(
            {
                "index": i,
                "start_section_index": i,
                "end_section_index": i + 1,
                "span_start_mm": round(y1, 2),
                "span_end_mm": round(y2, 2),
                "length_mm": round(span_len, 2),
                "chord_start_mm": round(c1, 2),
                "chord_end_mm": round(c2, 2),
                "volume_mm3": round(vol, 2),
                "centroid_mm": {
                    "x": round(cg_panel[0], 2),
                    "y": round(cg_panel[1], 2),
                    "z": round(cg_panel[2], 2),
                },
            }
        )

    if semi_vol <= 0.0:
        return (
            sections,
            [],
            0.0,
            (0.0, 0.0, 0.0),
            {"ixx": 0.0, "iyy": 0.0, "izz": 0.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0},
        )

    cg_x = weighted_x / semi_vol
    cg_z = weighted_z / semi_vol
    cg_y = 0.0 if mirror else (weighted_y / semi_vol)
    cg_total = (cg_x, cg_y, cg_z)

    total_vol = semi_vol * (2.0 if mirror else 1.0)

    # Parallel Axis Theorem
    ixx_total = 0.0
    iyy_total = 0.0
    izz_total = 0.0
    ixy_total = 0.0
    ixz_total = 0.0
    iyz_total = 0.0

    for vol, (cx, cy, cz), (ixx_p, iyy_p, izz_p) in panel_data:
        dx = cx - cg_x
        dz = cz - cg_z

        if mirror:
            dy = cy
            ixx_total += 2.0 * (ixx_p + vol * (dy**2 + dz**2))
            iyy_total += 2.0 * (iyy_p + vol * (dx**2 + dz**2))
            izz_total += 2.0 * (izz_p + vol * (dx**2 + dy**2))
            ixz_total -= 2.0 * (vol * dx * dz)
        else:
            dy = cy - cg_y
            ixx_total += ixx_p + vol * (dy**2 + dz**2)
            iyy_total += iyy_p + vol * (dx**2 + dz**2)
            izz_total += izz_p + vol * (dx**2 + dy**2)
            ixy_total -= vol * dx * dy
            ixz_total -= vol * dx * dz
            iyz_total -= vol * dy * dz

    scale = total_vol * 1e6
    unit_inertia = {
        "ixx": round(ixx_total / scale, 8),
        "iyy": round(iyy_total / scale, 8),
        "izz": round(izz_total / scale, 8),
        "ixy": round(ixy_total / scale, 8),
        "ixz": round(ixz_total / scale, 8),
        "iyz": round(iyz_total / scale, 8),
    }

    return sections, slices, total_vol, cg_total, unit_inertia


# =============================================================================
# Component Envelope Builders
# =============================================================================


def _compute_lifting_surface_envelope(component: dict[str, Any]) -> dict[str, Any] | None:
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    profiles = geometry.get("profiles")

    if not isinstance(profiles, list) or len(profiles) < 2:
        span = _number(geometry.get("wingspan", parameters.get("wingspan")))
        chord = _number(geometry.get("root_chord", parameters.get("root_chord")))
        if span > 0.0 and chord > 0.0:
            thickness = max(chord * 0.12, 5.0)
            vol = span * chord * thickness * 0.68
            return {
                "shape": "box",
                "size_mm": {
                    "x": round(chord, 1),
                    "y": round(span, 1),
                    "z": round(thickness, 1),
                },
                "offset_mm": {"x": round(chord * 0.40, 1), "y": 0.0, "z": 0.0},
                "volume_mm3": round(vol, 1),
                "unit_inertia": {
                    "ixx": round((span / 1000.0) ** 2 / 12.0, 8),
                    "iyy": round((chord / 1000.0) ** 2 / 16.0, 8),
                    "izz": round(((span / 1000.0) ** 2 + (chord / 1000.0) ** 2) / 12.0, 8),
                    "ixy": 0.0,
                    "ixz": 0.0,
                    "iyz": 0.0,
                },
                "sections": [],
                "slices": [],
            }
        return None

    # Compute exact trapezoidal panel slices and centroid
    sections, slices, total_vol, cg, unit_inertia = _compute_lifting_surface_trapezoidal_slices(
        geometry, profiles
    )

    # Compute outer bounding dimensions from 3D loft mesh if available
    try:
        from .lifting_surface_geometry import build_lifting_surface_geometry

        lofts = build_lifting_surface_geometry(component)
    except Exception:
        lofts = ()

    pts = [p for loft in lofts for sec in loft.sections for p in sec.points]
    mirror = bool(geometry.get("mirror", geometry.get("symmetric", False)))

    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        if mirror:
            max_semi = max(abs(y) for y in ys)
            size_y = round(max(max_semi * 2.0, 1.0), 1)
        else:
            size_y = round(max(max(ys) - min(ys), 1.0), 1)

        size_x = round(max(max(xs) - min(xs), 1.0), 1)
        size_z = round(max(max(zs) - min(zs), 1.0), 1)
    else:
        fb = _lifting_surface_fallback(geometry)
        if fb is None:
            return None
        size_x = fb["size_mm"]["x"]
        size_y = fb["size_mm"]["y"]
        size_z = fb["size_mm"]["z"]

    offset_x = round(cg[0], 1) if total_vol > 0.0 else round(size_x * 0.40, 1)
    offset_y = round(cg[1], 1) if total_vol > 0.0 else (0.0 if mirror else round(size_y / 2.0, 1))
    offset_z = round(cg[2], 1) if total_vol > 0.0 else 0.0

    return {
        "shape": "box",
        "size_mm": {"x": size_x, "y": size_y, "z": size_z},
        "offset_mm": {"x": offset_x, "y": offset_y, "z": offset_z},
        "volume_mm3": round(total_vol, 1),
        "unit_inertia": unit_inertia,
        "sections": sections,
        "slices": slices,
    }


def _lifting_surface_fallback(geometry: dict[str, Any]) -> dict[str, Any] | None:
    profiles = geometry.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return None
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for prof in profiles:
        if not isinstance(prof, dict):
            continue
        pos = prof.get("position")
        pos = pos if isinstance(pos, dict) else {}
        px = _number(pos.get("x"))
        py = _number(pos.get("y"))
        pz = _number(pos.get("z"))
        chord = _number(prof.get("chord"))
        xs.extend([px, px + chord])
        ys.append(py)
        thickness = chord * 0.12
        zs.extend([pz - thickness / 2.0, pz + thickness / 2.0])

    if not xs or not ys or not zs:
        return None

    mirror = bool(geometry.get("mirror", geometry.get("symmetric", False)))
    if mirror:
        max_semi = max(abs(y) for y in ys)
        size_y = round(max(max_semi * 2.0, 1.0), 1)
        offset_y = 0.0
    else:
        size_y = round(max(max(ys) - min(ys), 1.0), 1)
        offset_y = round((max(ys) + min(ys)) / 2.0, 1)

    return {
        "shape": "box",
        "size_mm": {
            "x": round(max(max(xs) - min(xs), 1.0), 1),
            "y": size_y,
            "z": round(max(max(zs) - min(zs), 1.0), 1),
        },
        "offset_mm": {
            "x": round((max(xs) + min(xs)) / 2.0, 1),
            "y": offset_y,
            "z": round((max(zs) + min(zs)) / 2.0, 1),
        },
    }


def _compute_fuselage_envelope(component: dict[str, Any]) -> dict[str, Any] | None:
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    segments = geometry.get("segments")

    if not isinstance(segments, list) or not segments:
        length = _number(parameters.get("length"))
        width = _number(parameters.get("width"))
        height = _number(parameters.get("height"))
        if length > 0.0:
            w = max(width, 10.0)
            h = max(height, 10.0)
            vol = length * math.pi * 0.25 * w * h
            return {
                "shape": "cylinder",
                "size_mm": {
                    "x": round(length, 1),
                    "y": round(w, 1),
                    "z": round(h, 1),
                },
                "offset_mm": {"x": round(length / 2.0, 1), "y": 0.0, "z": 0.0},
                "volume_mm3": round(vol, 1),
                "unit_inertia": {
                    "ixx": round(((w / 1000.0) ** 2 + (h / 1000.0) ** 2) / 16.0, 8),
                    "iyy": round((length / 1000.0) ** 2 / 12.0 + (h / 1000.0) ** 2 / 16.0, 8),
                    "izz": round((length / 1000.0) ** 2 / 12.0 + (w / 1000.0) ** 2 / 16.0, 8),
                    "ixy": 0.0,
                    "ixz": 0.0,
                    "iyz": 0.0,
                },
                "sections": [],
                "slices": [],
            }
        return None

    # Compute exact frustum slices, section bboxes, volume, centroid, and inertia
    sections, slices, total_vol, cg, unit_inertia = _compute_fuselage_trapezoidal_slices(segments)

    # Compute outer bounding dimensions from 3D loft mesh if available
    try:
        from .fuselage_geometry import build_fuselage_geometry

        lofts = build_fuselage_geometry(component)
    except Exception:
        lofts = ()

    pts = [p for loft in lofts for sec in loft.sections for p in sec.points]
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        size_x = round(max(max(xs) - min(xs), 1.0), 1)
        size_y = round(max(max(ys) - min(ys), 1.0), 1)
        size_z = round(max(max(zs) - min(zs), 1.0), 1)
    else:
        fb = _fuselage_fallback(segments)
        if fb is None:
            return None
        size_x = fb["size_mm"]["x"]
        size_y = fb["size_mm"]["y"]
        size_z = fb["size_mm"]["z"]

    offset_x = round(cg[0], 1) if total_vol > 0.0 else round(size_x / 2.0, 1)
    offset_y = round(cg[1], 1) if total_vol > 0.0 else 0.0
    offset_z = round(cg[2], 1) if total_vol > 0.0 else 0.0

    return {
        "shape": "trapezoid",
        "size_mm": {"x": size_x, "y": size_y, "z": size_z},
        "offset_mm": {"x": offset_x, "y": offset_y, "z": offset_z},
        "volume_mm3": round(total_vol, 1),
        "unit_inertia": unit_inertia,
        "sections": sections,
        "slices": slices,
    }


def _fuselage_fallback(segments: list[Any]) -> dict[str, Any] | None:
    points: list[tuple[float, float, float, float, float]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        for section in segment.get("sections", []):
            if not isinstance(section, dict):
                continue
            pos = section.get("position")
            pos = pos if isinstance(pos, dict) else {}
            prof = section.get("profile")
            prof = prof if isinstance(prof, dict) else {}
            w = _number(prof.get("width", prof.get("diameter")))
            h = _number(prof.get("height", prof.get("diameter")))
            points.append(
                (
                    _number(pos.get("x")),
                    _number(pos.get("y")),
                    _number(pos.get("z")),
                    w,
                    h,
                )
            )

    if not points:
        return None

    xs = [p[0] for p in points]
    min_y = min(y - w * 0.5 for _, y, _, w, _ in points)
    max_y = max(y + w * 0.5 for _, y, _, w, _ in points)
    min_z = min(z - h * 0.5 for _, _, z, _, h in points)
    max_z = max(z + h * 0.5 for _, _, z, _, h in points)

    size_x = round(max(max(xs) - min(xs), 1.0), 1)
    size_y = round(max(max_y - min_y, 1.0), 1)
    size_z = round(max(max_z - min_z, 1.0), 1)

    return {
        "shape": "trapezoid",
        "size_mm": {"x": size_x, "y": size_y, "z": size_z},
        "offset_mm": {
            "x": round((max(xs) + min(xs)) / 2.0, 1),
            "y": round((max_y + min_y) / 2.0, 1),
            "z": round((max_z + min_z) / 2.0, 1),
        },
    }


def _compute_control_surface_envelope(
    component: dict[str, Any],
    parent: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}

    span_start = geometry.get("span_start")
    span_end = geometry.get("span_end")
    chord = geometry.get("chord")
    chord_fraction = _number(geometry.get("chord_fraction", 0.25))

    parent_root_chord = 200.0
    parent_semi_span = 500.0
    if parent is not None:
        p_params = parent.get("parameters")
        p_params = p_params if isinstance(p_params, dict) else {}
        p_geom = p_params.get("geometry")
        p_geom = p_geom if isinstance(p_geom, dict) else {}
        p_profs = p_geom.get("profiles")
        if isinstance(p_profs, list) and p_profs:
            p_first = p_profs[0]
            if isinstance(p_first, dict):
                parent_root_chord = _number(p_first.get("chord", parent_root_chord))
            p_last = p_profs[-1]
            if isinstance(p_last, dict) and isinstance(p_last.get("position"), dict):
                parent_semi_span = abs(_number(p_last["position"].get("y", parent_semi_span)))

    if span_start is not None and span_end is not None:
        s_start = _number(span_start)
        s_end = _number(span_end)
        width = abs(s_end - s_start)
        offset_y = (s_start + s_end) / 2.0
    else:
        eta_s = _number(geometry.get("eta_start", 0.0))
        eta_e = _number(geometry.get("eta_end", 1.0))
        s_start = parent_semi_span * eta_s
        s_end = parent_semi_span * eta_e
        width = max(parent_semi_span * abs(eta_e - eta_s), 20.0)
        offset_y = (s_start + s_end) / 2.0

    c_val = _number(chord) if chord is not None else max(parent_root_chord * chord_fraction, 10.0)
    size_x = round(max(c_val, 5.0), 1)
    offset_x = round(parent_root_chord * (1.0 - chord_fraction / 3.0), 1)
    size_y = round(max(width, 10.0), 1)
    offset_y = round(offset_y, 1)
    thickness = round(max(size_x * 0.10, 5.0), 1)
    size_z = thickness
    offset_z = 0.0

    # Triangular wedge volume: V = span * 0.5 * chord * thickness
    vol = size_y * 0.5 * size_x * size_z
    scale = vol * 1e6
    j_span = vol * (size_y**2) / 12.0
    j_chord = vol * (size_x**2) / 18.0
    j_thick = vol * (size_z**2) / 18.0

    unit_inertia = {
        "ixx": round((j_span + j_thick) / scale, 8),
        "iyy": round((j_chord + j_thick) / scale, 8),
        "izz": round((j_span + j_chord) / scale, 8),
        "ixy": 0.0,
        "ixz": 0.0,
        "iyz": 0.0,
    }

    sections = [
        {
            "index": 0,
            "span_start_mm": round(s_start, 2),
            "span_end_mm": round(s_end, 2),
            "chord_mm": round(size_x, 2),
            "thickness_mm": round(thickness, 2),
            "shape": "wedge",
        }
    ]

    slices = [
        {
            "index": 0,
            "start_section_index": 0,
            "end_section_index": 0,
            "span_start_mm": round(s_start, 2),
            "span_end_mm": round(s_end, 2),
            "length_mm": round(size_y, 2),
            "chord_start_mm": round(size_x, 2),
            "chord_end_mm": round(size_x, 2),
            "volume_mm3": round(vol, 2),
            "centroid_mm": {"x": offset_x, "y": offset_y, "z": offset_z},
        }
    ]

    return {
        "shape": "box",
        "size_mm": {"x": size_x, "y": size_y, "z": size_z},
        "offset_mm": {"x": offset_x, "y": offset_y, "z": offset_z},
        "volume_mm3": round(vol, 1),
        "unit_inertia": unit_inertia,
        "sections": sections,
        "slices": slices,
    }


__all__ = [
    "GEOMETRY_COMPONENT_TYPES",
    "compute_geometry_envelope",
    "sync_component_envelope",
    "sync_project_geometry_envelopes",
]
